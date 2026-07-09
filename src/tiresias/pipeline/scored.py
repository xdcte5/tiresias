"""Wire types shared by the scorer, the stats aggregator, and the API.

These are pydantic models so FastAPI can serialise them directly and the dashboard
gets a stable JSON contract.
"""

from __future__ import annotations

from pydantic import BaseModel


class ScoredFlow(BaseModel):
    """One classified flow, as broadcast to the dashboard."""

    flow_id: str
    protocol: str
    src: str  # initiator ip:port (the local endpoint)
    dst: str  # peer ip:port
    label: str
    confidence: float
    anomalous: bool
    n_packets: int
    bytes_total: int
    duration: float
    sni: str | None = None
    start_ts: float
    scored_ts: float
    top_probs: dict[str, float]  # top-k class -> probability, for the UI


class BandwidthBucket(BaseModel):
    t: float  # epoch seconds (bucket start)
    bytes_by_class: dict[str, int]


class Summary(BaseModel):
    total_flows: int
    anomalous_flows: int
    per_class_flows: dict[str, int]
    per_class_bytes: dict[str, int]
    bandwidth_series: list[BandwidthBucket]
    classes: list[str]
    bucket_s: float
