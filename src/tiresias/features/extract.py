"""Per-flow feature extraction — the core ML feature engineering.

Features are organised into named **groups** so the training/inference matrix can be
assembled deterministically and so the leakage boundary is explicit:

  * ``flow_stats`` — packet-size stats, timing, byte/packet ratios, burstiness,
    duration/rate. The honest core: size + timing only, works even with no TLS.
  * ``tls_shape``  — structural TLS handshake features (has_tls, version, counts of
    ciphers/extensions/curves). Describes the client's TLS *shape*, not its identity.
  * ``raw_seq``    — the first-K signed packet sizes and inter-arrival times, padded
    to a fixed length. Directly consumed by the Sprint-6 sequence model; also usable
    by the tree baseline.
  * ``tls_ja3``    — the JA3 fingerprint as a numeric id. **Off by default.** In a
    self-generated dataset one app maps to one JA3, so JA3 can act as an app label —
    excluded to keep the headline number honest, toggleable for comparison.

**SNI and the raw JA3 hash are never features** — they are returned as metadata. SNI
is the *label source* (see ``features.labeling``); using it as both label and feature
is leakage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import CONFIG, FeatureConfig
from ..flows.record import BACKWARD, FORWARD, FlowRecord
from .tls import parse_client_hello

_EPS = 1e-9


def _stats(values: np.ndarray) -> tuple[float, float, float, float]:
    """(mean, std, min, max); zeros for an empty array."""
    if values.size == 0:
        return 0.0, 0.0, 0.0, 0.0
    return float(values.mean()), float(values.std()), float(values.min()), float(values.max())


def _burstiness(abs_sizes: np.ndarray, n_windows: int) -> float:
    """Coefficient of variation of per-window byte volume — high for bursty traffic."""
    if abs_sizes.size == 0:
        return 0.0
    windows = np.array_split(abs_sizes, min(n_windows, abs_sizes.size))
    sums = np.array([w.sum() for w in windows], dtype=float)
    return float(sums.std() / (sums.mean() + _EPS))


# --- Deterministic column names per group (order is the contract with the model) ---

_FLOW_STATS = [
    "duration", "n_packets", "n_fwd", "n_bwd", "fwd_bwd_pkt_ratio",
    "bytes_fwd", "bytes_bwd", "bytes_total", "up_down_byte_ratio",
    "size_mean", "size_std", "size_min", "size_max",
    "fwd_size_mean", "fwd_size_std", "fwd_size_min", "fwd_size_max",
    "bwd_size_mean", "bwd_size_std", "bwd_size_min", "bwd_size_max",
    "iat_mean", "iat_std", "fwd_iat_mean", "fwd_iat_std", "bwd_iat_mean", "bwd_iat_std",
    "burstiness", "pkts_per_sec", "bytes_per_sec",
]
_TLS_SHAPE = ["has_tls", "tls_version", "tls_n_ciphers", "tls_n_extensions", "tls_n_curves"]
_TLS_JA3 = ["ja3_id"]


def _seq_columns(k: int) -> list[str]:
    return [f"seq_size_{i}" for i in range(k)] + [f"seq_iat_{i}" for i in range(k)]


def feature_group_columns(cfg: FeatureConfig | None = None) -> dict[str, list[str]]:
    cfg = cfg or CONFIG.features
    return {
        "flow_stats": list(_FLOW_STATS),
        "tls_shape": list(_TLS_SHAPE),
        "raw_seq": _seq_columns(cfg.sequence_len),
        "tls_ja3": list(_TLS_JA3),
    }


#: Groups used for training/inference unless overridden. Honest headline set:
#: size + timing + TLS structure + raw sequence; no SNI, no JA3 identity.
DEFAULT_GROUPS = ("flow_stats", "tls_shape", "raw_seq")

#: Columns that are metadata, never fed to the model.
META_COLUMNS = ("sni", "ja3", "ja3_hash")


def feature_columns(groups=DEFAULT_GROUPS, cfg: FeatureConfig | None = None) -> list[str]:
    """Ordered feature-column list for the given groups."""
    allcols = feature_group_columns(cfg)
    out: list[str] = []
    for g in groups:
        out.extend(allcols[g])
    return out


@dataclass
class FeatureRow:
    features: dict[str, float] = field(default_factory=dict)  # all groups, numeric
    meta: dict[str, object] = field(default_factory=dict)  # sni, ja3, ja3_hash


def extract_features(flow: FlowRecord, cfg: FeatureConfig | None = None) -> FeatureRow:
    cfg = cfg or CONFIG.features
    k = cfg.sequence_len

    signed = np.array(flow.sizes, dtype=float)
    directions = np.array(flow.directions, dtype=float)
    ts = np.array(flow.timestamps, dtype=float)
    abs_sizes = np.abs(signed)

    fwd_mask = directions == FORWARD
    bwd_mask = directions == BACKWARD
    fwd_sizes = abs_sizes[fwd_mask]
    bwd_sizes = abs_sizes[bwd_mask]

    duration = flow.duration
    n = float(flow.n_packets)
    n_fwd = float(fwd_mask.sum())
    n_bwd = float(bwd_mask.sum())
    bytes_fwd = float(fwd_sizes.sum())
    bytes_bwd = float(bwd_sizes.sum())
    bytes_total = float(abs_sizes.sum())

    # Inter-arrival times (overall and per direction).
    iats = np.diff(ts) if ts.size >= 2 else np.array([])
    fwd_ts = ts[fwd_mask]
    bwd_ts = ts[bwd_mask]
    fwd_iats = np.diff(fwd_ts) if fwd_ts.size >= 2 else np.array([])
    bwd_iats = np.diff(bwd_ts) if bwd_ts.size >= 2 else np.array([])

    s_mean, s_std, s_min, s_max = _stats(abs_sizes)
    fs_mean, fs_std, fs_min, fs_max = _stats(fwd_sizes)
    bs_mean, bs_std, bs_min, bs_max = _stats(bwd_sizes)
    ia_mean, ia_std, _, _ = _stats(iats)
    fia_mean, fia_std, _, _ = _stats(fwd_iats)
    bia_mean, bia_std, _, _ = _stats(bwd_iats)

    feats: dict[str, float] = {
        "duration": duration,
        "n_packets": n,
        "n_fwd": n_fwd,
        "n_bwd": n_bwd,
        "fwd_bwd_pkt_ratio": n_fwd / (n_bwd + 1.0),
        "bytes_fwd": bytes_fwd,
        "bytes_bwd": bytes_bwd,
        "bytes_total": bytes_total,
        "up_down_byte_ratio": bytes_fwd / (bytes_bwd + 1.0),
        "size_mean": s_mean, "size_std": s_std, "size_min": s_min, "size_max": s_max,
        "fwd_size_mean": fs_mean, "fwd_size_std": fs_std,
        "fwd_size_min": fs_min, "fwd_size_max": fs_max,
        "bwd_size_mean": bs_mean, "bwd_size_std": bs_std,
        "bwd_size_min": bs_min, "bwd_size_max": bs_max,
        "iat_mean": ia_mean, "iat_std": ia_std,
        "fwd_iat_mean": fia_mean, "fwd_iat_std": fia_std,
        "bwd_iat_mean": bia_mean, "bwd_iat_std": bia_std,
        "burstiness": _burstiness(abs_sizes, cfg.burst_windows),
        "pkts_per_sec": n / (duration + _EPS),
        "bytes_per_sec": bytes_total / (duration + _EPS),
    }

    # TLS features + metadata.
    tls = parse_client_hello(flow.client_hello)
    if tls is not None:
        feats["has_tls"] = 1.0
        feats["tls_version"] = float(tls.version)
        feats["tls_n_ciphers"] = float(tls.n_ciphers)
        feats["tls_n_extensions"] = float(tls.n_extensions)
        feats["tls_n_curves"] = float(tls.n_curves)
        feats["ja3_id"] = float(int(tls.ja3_hash[:8], 16))
        meta = {"sni": tls.sni, "ja3": tls.ja3, "ja3_hash": tls.ja3_hash}
    else:
        feats.update(
            {"has_tls": 0.0, "tls_version": 0.0, "tls_n_ciphers": 0.0,
             "tls_n_extensions": 0.0, "tls_n_curves": 0.0, "ja3_id": 0.0}
        )
        meta = {"sni": None, "ja3": None, "ja3_hash": None}

    # Raw sequences: first-K signed sizes and per-packet inter-arrival, padded to K.
    seq_sizes = signed[:k]
    per_pkt_iat = np.concatenate([[0.0], iats])[:k] if signed.size else np.array([])
    for i in range(k):
        feats[f"seq_size_{i}"] = float(seq_sizes[i]) if i < seq_sizes.size else 0.0
        feats[f"seq_iat_{i}"] = float(per_pkt_iat[i]) if i < per_pkt_iat.size else 0.0

    return FeatureRow(features=feats, meta=meta)
