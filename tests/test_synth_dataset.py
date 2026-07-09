"""Synthetic dataset: schema, session integrity, SNI-path agreement, separability."""

import numpy as np

from tiresias.features.labeling import label_for_sni
from tiresias.models.dataset import (
    LABEL_COL,
    SESSION_COL,
    all_feature_columns,
    dataset_from_captures,
    dataset_from_labeled,
)
from tiresias.synth.generate import PROFILES, generate_dataset


def test_dataset_schema_and_sessions():
    triples = generate_dataset(sessions_per_class=5, seed=1)
    df = dataset_from_labeled(triples)
    # Every class present.
    assert df[LABEL_COL].nunique() == len(PROFILES)
    # Feature columns all present, plus label + session.
    for c in all_feature_columns():
        assert c in df.columns
    assert {LABEL_COL, SESSION_COL}.issubset(df.columns)
    # A session belongs to exactly one class (no leakage across the split later).
    per_session_labels = df.groupby(SESSION_COL)[LABEL_COL].nunique()
    assert (per_session_labels == 1).all()


def test_sni_labeling_agrees_with_generator_for_tls_classes():
    # For TLS classes, the SNI-derived label must match the generated ground truth.
    triples = generate_dataset(sessions_per_class=3, seed=2)
    labeled_flows = [(flow, sid) for flow, _label, sid in triples if flow.client_hello]
    df = dataset_from_captures(labeled_flows)
    assert not df.empty
    # Cross-check a sample directly.
    for flow, label, _sid in triples:
        if flow.client_hello:
            from tiresias.features.tls import parse_client_hello

            sni = parse_client_hello(flow.client_hello).sni
            assert label_for_sni(sni) == label


def test_classes_are_separable_above_chance():
    # A quick, cheap sanity check that features carry class signal: a nearest-centroid
    # style split on a couple of hand-picked features beats random (1/8 = 12.5%).
    triples = generate_dataset(sessions_per_class=15, seed=3)
    df = dataset_from_labeled(triples)
    labels = df[LABEL_COL].to_numpy()
    # Use mean packet size + iat_mean: streaming/file-transfer big, gaming/dns small.
    x = df[["size_mean", "iat_mean", "up_down_byte_ratio"]].to_numpy()
    # Assign each row to the class whose per-class centroid is nearest.
    classes = np.unique(labels)
    centroids = {c: x[labels == c].mean(axis=0) for c in classes}
    xn = (x - x.mean(0)) / (x.std(0) + 1e-9)
    cn = {c: (centroids[c] - x.mean(0)) / (x.std(0) + 1e-9) for c in classes}
    preds = []
    for row in xn:
        preds.append(min(classes, key=lambda c: np.linalg.norm(row - cn[c])))
    acc = (np.array(preds) == labels).mean()
    assert acc > 0.30  # comfortably above 1/8 chance -> features carry signal
