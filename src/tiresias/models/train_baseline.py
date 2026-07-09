"""Train + evaluate the baseline classifiers (RandomForest, optional LightGBM).

Both are trained on the same session-based split so the comparison is fair, and the
returned :class:`Model` bundle carries the exact feature order for live scoring.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from ..config import CONFIG, FeatureConfig
from ..features.extract import DEFAULT_GROUPS, feature_columns
from ..logging_setup import get_logger
from .dataset import LABEL_COL
from .evaluate import EvalResult, evaluate_predictions, measure_latency
from .registry import Model
from .split import SplitIndices, session_train_test_split

log = get_logger("tiresias.train")


def build_estimator(model_type: str, seed: int) -> Pipeline:
    """Return an imputer+classifier pipeline. LightGBM optional; falls back to RF."""
    if model_type == "lightgbm":
        try:
            from lightgbm import LGBMClassifier

            clf = LGBMClassifier(
                n_estimators=300, num_leaves=48, learning_rate=0.06,
                subsample=0.9, colsample_bytree=0.9, random_state=seed, n_jobs=-1, verbose=-1,
            )
        except ImportError:
            log.warning("lightgbm not installed; falling back to RandomForest.")
            model_type = "rf"
    if model_type != "lightgbm":
        clf = RandomForestClassifier(
            n_estimators=200, max_depth=24, min_samples_leaf=2,
            n_jobs=-1, random_state=seed, class_weight="balanced_subsample",
        )
    # Impute defensively even though extraction yields finite values.
    return Pipeline([("impute", SimpleImputer(strategy="constant", fill_value=0.0)), ("clf", clf)])


def _set_predict_serial(estimator: Pipeline) -> None:
    """Force single-threaded prediction (fast for per-flow single-row inference)."""
    clf = estimator.named_steps.get("clf")
    if clf is not None and hasattr(clf, "n_jobs"):
        clf.n_jobs = 1


@dataclass
class TrainedModel:
    model: Model
    result: EvalResult
    y_true: np.ndarray
    y_pred: np.ndarray
    split: SplitIndices


def train_and_evaluate(
    df: pd.DataFrame,
    model_type: str = "rf",
    groups: tuple[str, ...] = DEFAULT_GROUPS,
    feature_config: FeatureConfig | None = None,
    test_size: float = 0.25,
    seed: int = 42,
    with_latency: bool = True,
) -> TrainedModel:
    cfg = feature_config or CONFIG.features
    cols = feature_columns(groups, cfg)
    labels = sorted(df[LABEL_COL].unique())

    split = session_train_test_split(df, test_size=test_size, seed=seed)
    train_df = df.iloc[split.train]
    test_df = df.iloc[split.test]

    X_train = train_df[cols].to_numpy()
    y_train = train_df[LABEL_COL].to_numpy()
    X_test = test_df[cols].to_numpy()
    y_test = test_df[LABEL_COL].to_numpy()

    estimator = build_estimator(model_type, seed)
    estimator.fit(X_train, y_train)
    # Predict serially: single-row (per-flow) inference is dominated by parallel
    # dispatch overhead when n_jobs=-1. Fit parallel, serve serial.
    _set_predict_serial(estimator)

    model = Model.from_estimator(
        estimator, groups=groups, feature_config=cfg,
        metadata={"model_type": model_type, "n_train": int(len(train_df)),
                  "n_test": int(len(test_df)), "seed": seed},
    )

    y_pred = estimator.predict(X_test)
    result = evaluate_predictions(y_test, y_pred, labels)

    if with_latency:
        # Feature dicts for the test rows, to time the real per-flow predict path.
        sample = test_df[cols].to_dict(orient="records")[:200]
        result.latency = measure_latency(model, sample)

    log.info(
        "%s: acc=%.3f macroF1=%.3f (train=%d test=%d, %d features)",
        model_type, result.accuracy, result.macro_f1, len(train_df), len(test_df), len(cols),
    )
    return TrainedModel(model=model, result=result, y_true=y_test, y_pred=y_pred, split=split)


def ablation_accuracy(
    df: pd.DataFrame, group_sets: dict[str, tuple[str, ...]], model_type: str = "rf", seed: int = 42
) -> dict[str, float]:
    """Accuracy per feature-group set (same split) — used to expose JA3 leakage."""
    out: dict[str, float] = {}
    for name, groups in group_sets.items():
        tm = train_and_evaluate(df, model_type=model_type, groups=groups, seed=seed,
                                 with_latency=False)
        out[name] = tm.result.accuracy
    return out
