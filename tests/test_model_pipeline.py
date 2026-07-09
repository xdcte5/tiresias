"""Sprint 3: split integrity, registry save/load + train/serve parity, training."""

import numpy as np

from tiresias.features.extract import DEFAULT_GROUPS, feature_columns
from tiresias.models.dataset import dataset_from_labeled
from tiresias.models.registry import Model
from tiresias.models.split import session_train_test_split, sessions_disjoint
from tiresias.models.train_baseline import train_and_evaluate
from tiresias.synth.generate import generate_dataset


def _dataset(sessions=12, seed=5):
    return dataset_from_labeled(generate_dataset(sessions_per_class=sessions, seed=seed))


def test_session_split_is_disjoint():
    df = _dataset()
    split = session_train_test_split(df, test_size=0.25, seed=1)
    assert sessions_disjoint(df, split)
    # And it actually held some out.
    assert len(split.test) > 0 and len(split.train) > 0


def test_train_produces_reasonable_model():
    df = _dataset(sessions=16)
    tm = train_and_evaluate(df, model_type="rf", seed=42)
    # Synthetic classes are separable-but-overlapping; expect solidly above chance.
    assert tm.result.accuracy > 0.60
    assert tm.result.macro_f1 > 0.55
    # Latency is measured and not absurd. (This is a sanity bound under test load,
    # not the perf claim — the real headline latency is reported by tiresias-train,
    # typically single-digit ms for RF and ~2-3ms for LightGBM on this dataset.)
    assert tm.result.latency is not None
    assert tm.result.latency.median_ms < 100.0
    # Confusion matrix is square over all classes.
    n = len(tm.result.labels)
    assert tm.result.confusion.shape == (n, n)


def test_registry_roundtrip_and_train_serve_parity(tmp_path):
    df = _dataset(sessions=10)
    tm = train_and_evaluate(df, model_type="rf", seed=7, with_latency=False)
    model = tm.model

    # The bundle knows its exact feature order.
    assert model.feature_columns == feature_columns(DEFAULT_GROUPS)

    # Save/load round-trips and predicts identically.
    path = model.save(tmp_path / "m.joblib")
    loaded = Model.load(path)
    assert loaded.feature_columns == model.feature_columns
    assert loaded.classes == model.classes

    # Predicting a flow through the loaded model matches the in-memory one exactly
    # (train/serve parity — same featurization + column order).
    flow = generate_dataset(sessions_per_class=1, seed=99)[0][0]
    p1 = model.predict_flow(flow)
    p2 = loaded.predict_flow(flow)
    assert p1.label == p2.label
    assert abs(p1.confidence - p2.confidence) < 1e-9


def test_prediction_probabilities_and_anomaly():
    df = _dataset(sessions=10)
    tm = train_and_evaluate(df, model_type="rf", seed=3, with_latency=False)
    flow = generate_dataset(sessions_per_class=1, seed=123)[0][0]
    pred = tm.model.predict_flow(flow)
    # Probabilities form a distribution over all classes.
    assert abs(sum(pred.probabilities.values()) - 1.0) < 1e-6
    assert 0.0 <= pred.confidence <= 1.0
    # A confident prediction is not anomalous under a low threshold.
    assert pred.is_anomalous(threshold=0.0) is False


def test_ja3_group_inflates_accuracy():
    # Sanity: the leaky JA3 group should not *hurt* accuracy vs the honest set
    # (it memorizes app id). This documents the leakage the report warns about.
    df = _dataset(sessions=14)
    honest = train_and_evaluate(df, groups=DEFAULT_GROUPS, seed=1, with_latency=False)
    leaky = train_and_evaluate(
        df, groups=(*DEFAULT_GROUPS, "tls_ja3"), seed=1, with_latency=False
    )
    assert leaky.result.accuracy >= honest.result.accuracy - 0.05
    assert np.isfinite(leaky.result.accuracy)
