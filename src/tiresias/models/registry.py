"""The shared model interface used by BOTH offline training and live scoring.

A :class:`Model` bundles the fitted estimator with the exact feature-column order,
the class list, and the feature config it was trained with. Training and the live
scorer both featurize a flow the same way and vectorize through this bundle, so the
online and offline feature order can never silently drift — a classic source of
train/serve skew.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np

from ..config import CONFIG, FeatureConfig
from ..features.extract import DEFAULT_GROUPS, extract_features, feature_columns
from ..flows.record import FlowRecord


@dataclass
class Prediction:
    label: str
    confidence: float  # max class probability
    probabilities: dict[str, float]

    def is_anomalous(self, threshold: float | None = None) -> bool:
        thr = CONFIG.inference.anomaly_confidence_threshold if threshold is None else threshold
        return self.confidence < thr


@dataclass
class Model:
    estimator: object  # fitted sklearn-compatible classifier with predict_proba
    feature_columns: list[str]
    classes: list[str]
    feature_groups: tuple[str, ...] = DEFAULT_GROUPS
    feature_config: FeatureConfig = field(default_factory=lambda: CONFIG.features)
    metadata: dict = field(default_factory=dict)

    # --- construction -----------------------------------------------------------
    @classmethod
    def from_estimator(
        cls,
        estimator,
        groups: tuple[str, ...] = DEFAULT_GROUPS,
        feature_config: FeatureConfig | None = None,
        metadata: dict | None = None,
    ) -> Model:
        cfg = feature_config or CONFIG.features
        cols = feature_columns(groups, cfg)
        classes = [str(c) for c in estimator.classes_]
        return cls(
            estimator=estimator,
            feature_columns=cols,
            classes=classes,
            feature_groups=tuple(groups),
            feature_config=cfg,
            metadata=metadata or {},
        )

    # --- vectorization ----------------------------------------------------------
    def vectorize(self, feature_dict: dict) -> np.ndarray:
        """Order a feature dict into the model's expected column vector (1, n)."""
        return np.array([[float(feature_dict.get(c, 0.0)) for c in self.feature_columns]])

    def vectorize_many(self, feature_dicts: list[dict]) -> np.ndarray:
        return np.array(
            [[float(fd.get(c, 0.0)) for c in self.feature_columns] for fd in feature_dicts]
        )

    # --- prediction -------------------------------------------------------------
    def _to_prediction(self, proba_row: np.ndarray) -> Prediction:
        probs = {self.classes[i]: float(p) for i, p in enumerate(proba_row)}
        best_i = int(np.argmax(proba_row))
        return Prediction(
            label=self.classes[best_i],
            confidence=float(proba_row[best_i]),
            probabilities=probs,
        )

    def predict_features(self, feature_dict: dict) -> Prediction:
        proba = self.estimator.predict_proba(self.vectorize(feature_dict))[0]
        return self._to_prediction(proba)

    def predict_flow(self, flow: FlowRecord) -> Prediction:
        fr = extract_features(flow, self.feature_config)
        return self.predict_features(fr.features)

    # --- persistence ------------------------------------------------------------
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata.setdefault("saved_at", datetime.now(UTC).isoformat())
        joblib.dump(
            {
                "estimator": self.estimator,
                "feature_columns": self.feature_columns,
                "classes": self.classes,
                "feature_groups": list(self.feature_groups),
                "feature_config": self.feature_config,
                "metadata": self.metadata,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> Model:
        d = joblib.load(path)
        return cls(
            estimator=d["estimator"],
            feature_columns=d["feature_columns"],
            classes=d["classes"],
            feature_groups=tuple(d["feature_groups"]),
            feature_config=d["feature_config"],
            metadata=d.get("metadata", {}),
        )
