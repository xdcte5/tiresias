"""Central configuration for the whole pipeline.

Every tunable that affects flow assembly, feature extraction, and inference lives
here so the offline (training) and online (live scoring) paths stay consistent.
Values can be overridden via environment variables prefixed ``TIRESIAS_``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields


def _env(name: str, default: str) -> str:
    return os.environ.get(f"TIRESIAS_{name}", default)


@dataclass(frozen=True)
class FlowConfig:
    """Flow-assembly lifecycle parameters."""

    # A flow is flushed when idle for this many seconds (spec: ~15s).
    idle_timeout_s: float = 15.0
    # Hard cap on total flow lifetime so a permanently-active flow still flushes.
    active_timeout_s: float = 120.0
    # Classify early: buffer at most this many packets per flow, then flush.
    packet_cap: int = 100
    # Ignore flows shorter than this many packets (noise / stray SYNs).
    min_packets: int = 4
    # How often the reaper scans for idle flows.
    reap_interval_s: float = 1.0


@dataclass(frozen=True)
class FeatureConfig:
    """Feature-extraction parameters. K governs the fixed-length raw sequences."""

    # Length of the raw packet-size / inter-arrival sequences (padded/truncated).
    sequence_len: int = 32
    # Number of sub-windows used for burstiness variance.
    burst_windows: int = 8
    # Whether SNI-derived columns may enter the *training feature set*.
    # Default False to structurally prevent label leakage (SNI is the label source).
    allow_sni_features: bool = False


@dataclass(frozen=True)
class CaptureConfig:
    """Live-capture parameters."""

    interface: str = field(default_factory=lambda: _env("IFACE", "any"))
    # BPF filter applied at capture time. IP traffic only by default.
    bpf_filter: str = "ip or ip6"
    # Snap length: we only need headers + TLS ClientHello, not full payloads.
    snaplen: int = 600


@dataclass(frozen=True)
class InferenceConfig:
    """Streaming-inference / anomaly parameters."""

    # Max-class confidence below this => flagged "unclassified/anomalous".
    anomaly_confidence_threshold: float = 0.45
    model_path: str = field(default_factory=lambda: _env("MODEL_PATH", "artifacts/baseline_rf.joblib"))


@dataclass(frozen=True)
class Config:
    flow: FlowConfig = field(default_factory=FlowConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    inference: InferenceConfig = field(default_factory=InferenceConfig)

    def describe(self) -> dict[str, dict[str, object]]:
        """Flat-ish dict for logging/serialisation."""
        out: dict[str, dict[str, object]] = {}
        for f in fields(self):
            section = getattr(self, f.name)
            out[f.name] = {sf.name: getattr(section, sf.name) for sf in fields(section)}
        return out


#: Import-and-use singleton. Construct a fresh ``Config()`` in tests to override.
CONFIG = Config()
