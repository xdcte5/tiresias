"""Streaming scorer: FlowRecord -> ScoredFlow via the shared model registry.

Featurization + prediction go through :class:`Model` so the live path uses the exact
same feature order as training (no train/serve skew). The scorer is a pure, fast,
synchronous function; the async plumbing lives in the API server.
"""

from __future__ import annotations

import time

from ..config import CONFIG
from ..models.registry import Model
from .scored import ScoredFlow


def _flow_id(flow) -> str:
    return f"{abs(hash((str(flow.key), round(flow.start_ts, 3)))) & 0xFFFFFFFF:08x}"


def _endpoints(flow) -> tuple[str, str]:
    """(src, dst) display strings — src is the initiator (local endpoint)."""
    a = flow.key.endpoint_a
    b = flow.key.endpoint_b
    src = flow.initiator
    dst = b if src == a else a
    return f"{src[0]}:{src[1]}", f"{dst[0]}:{dst[1]}"


def _top_k(probs: dict[str, float], k: int = 3) -> dict[str, float]:
    return dict(sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:k])


class StreamingScorer:
    def __init__(self, model: Model, anomaly_threshold: float | None = None) -> None:
        self.model = model
        self.anomaly_threshold = (
            CONFIG.inference.anomaly_confidence_threshold
            if anomaly_threshold is None
            else anomaly_threshold
        )

    def score(self, flow) -> ScoredFlow:
        fr = self.model_features(flow)
        pred = self.model.predict_features(fr.features)
        anomalous = pred.confidence < self.anomaly_threshold
        src, dst = _endpoints(flow)
        return ScoredFlow(
            flow_id=_flow_id(flow),
            protocol=flow.key.protocol,
            src=src,
            dst=dst,
            label="unclassified" if anomalous else pred.label,
            confidence=round(pred.confidence, 4),
            anomalous=anomalous,
            n_packets=flow.n_packets,
            bytes_total=int(sum(abs(s) for s in flow.sizes)),
            duration=round(flow.duration, 3),
            sni=fr.meta.get("sni"),
            start_ts=flow.start_ts,
            scored_ts=time.time(),
            top_probs={k: round(v, 4) for k, v in _top_k(pred.probabilities).items()},
        )

    def model_features(self, flow):
        from ..features.extract import extract_features

        return extract_features(flow, self.model.feature_config)
