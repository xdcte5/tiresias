"""Rolling aggregation for the dashboard: bandwidth-by-class over time + totals.

Bytes are bucketed into fixed time windows keyed by wall-clock second so the
dashboard can render a rolling stacked-area "bandwidth by class" chart, plus running
per-class flow/byte counts and an anomaly count for the summary endpoint.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from .scored import BandwidthBucket, ScoredFlow, Summary


class RollingStats:
    def __init__(self, bucket_s: float = 2.0, horizon_s: float = 120.0) -> None:
        self.bucket_s = bucket_s
        self.max_buckets = max(1, int(horizon_s / bucket_s))
        # bucket_start -> {class: bytes}
        self._buckets: deque[tuple[float, dict[str, int]]] = deque()
        self.total_flows = 0
        self.anomalous_flows = 0
        self.per_class_flows: dict[str, int] = defaultdict(int)
        self.per_class_bytes: dict[str, int] = defaultdict(int)

    def _bucket_start(self, t: float) -> float:
        return (t // self.bucket_s) * self.bucket_s

    def add(self, scored: ScoredFlow, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.total_flows += 1
        if scored.anomalous:
            self.anomalous_flows += 1
        self.per_class_flows[scored.label] += 1
        self.per_class_bytes[scored.label] += scored.bytes_total

        bstart = self._bucket_start(now)
        if not self._buckets or self._buckets[-1][0] != bstart:
            # New bucket (fill only the newest; gaps are implicitly zero).
            self._buckets.append((bstart, defaultdict(int)))
            while len(self._buckets) > self.max_buckets:
                self._buckets.popleft()
        self._buckets[-1][1][scored.label] += scored.bytes_total

    def summary(self, classes: list[str]) -> Summary:
        series = [
            BandwidthBucket(t=bstart, bytes_by_class=dict(by_class))
            for bstart, by_class in self._buckets
        ]
        return Summary(
            total_flows=self.total_flows,
            anomalous_flows=self.anomalous_flows,
            per_class_flows=dict(self.per_class_flows),
            per_class_bytes=dict(self.per_class_bytes),
            bandwidth_series=series,
            classes=classes,
            bucket_s=self.bucket_s,
        )
