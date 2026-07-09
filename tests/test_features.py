"""Feature extraction correctness + the SNI/JA3 leakage boundary."""

import numpy as np

from tiresias.config import FeatureConfig
from tiresias.features.extract import (
    DEFAULT_GROUPS,
    META_COLUMNS,
    extract_features,
    feature_columns,
)
from tiresias.flows.key import FlowKey
from tiresias.flows.record import BACKWARD, FORWARD, FlowRecord
from tiresias.synth.tls_bytes import client_hello


def _flow_with(sizes, dirs, ts, ch=None):
    key, _ = FlowKey.normalize("10.0.0.1", 5000, "9.9.9.9", 443, "TCP")
    return FlowRecord(
        key=key,
        initiator=("10.0.0.1", 5000),
        start_ts=ts[0],
        last_ts=ts[-1],
        sizes=[s * d for s, d in zip(sizes, dirs, strict=True)],
        timestamps=list(ts),
        directions=list(dirs),
        client_hello=ch,
    )


def test_basic_size_and_direction_stats():
    flow = _flow_with(
        sizes=[100, 200, 300, 400],
        dirs=[FORWARD, BACKWARD, FORWARD, BACKWARD],
        ts=[0.0, 1.0, 2.0, 3.0],
    )
    f = extract_features(flow).features
    assert f["n_packets"] == 4
    assert f["n_fwd"] == 2 and f["n_bwd"] == 2
    assert f["bytes_fwd"] == 400 and f["bytes_bwd"] == 600
    assert f["bytes_total"] == 1000
    assert f["fwd_size_mean"] == 200  # (100+300)/2
    assert f["bwd_size_mean"] == 300  # (200+400)/2
    assert abs(f["iat_mean"] - 1.0) < 1e-9
    assert abs(f["duration"] - 3.0) < 1e-9


def test_sequence_padding_and_truncation():
    cfg = FeatureConfig(sequence_len=5)
    # 3 packets -> seq padded to length 5 with zeros beyond index 2.
    flow = _flow_with([100, 100, 100], [FORWARD, BACKWARD, FORWARD], [0.0, 0.5, 1.0])
    f = extract_features(flow, cfg).features
    assert f["seq_size_0"] == 100 and f["seq_size_1"] == -100  # signed by direction
    assert f["seq_size_3"] == 0.0 and f["seq_size_4"] == 0.0  # padded
    assert f["seq_iat_0"] == 0.0 and abs(f["seq_iat_1"] - 0.5) < 1e-9


def test_tls_features_and_metadata_split():
    ch = client_hello("www.youtube.com")
    flow = _flow_with([100, 200], [FORWARD, BACKWARD], [0.0, 1.0], ch=ch)
    fr = extract_features(flow)
    # Structural TLS features present in the numeric feature dict.
    assert fr.features["has_tls"] == 1.0
    assert fr.features["tls_n_ciphers"] > 0
    # SNI + raw JA3 hash live in metadata, NOT features.
    assert fr.meta["sni"] == "www.youtube.com"
    assert fr.meta["ja3_hash"] is not None
    assert "sni" not in fr.features
    assert "ja3_hash" not in fr.features


def test_leakage_guard_default_feature_set_excludes_sni_and_ja3():
    cols = feature_columns(DEFAULT_GROUPS)
    # No metadata column may appear in the default training feature set.
    for meta in META_COLUMNS:
        assert meta not in cols
    # JA3 numeric id is its own opt-in group, excluded by default.
    assert "ja3_id" not in cols
    # But structural TLS shape IS allowed.
    assert "has_tls" in cols and "tls_n_ciphers" in cols


def test_no_tls_flow_defaults():
    flow = _flow_with([100, 200], [FORWARD, BACKWARD], [0.0, 1.0], ch=None)
    fr = extract_features(flow)
    assert fr.features["has_tls"] == 0.0
    assert fr.features["ja3_id"] == 0.0
    assert fr.meta["sni"] is None


def test_all_feature_values_finite():
    # Single-packet-ish edge case must not produce NaN/inf.
    flow = _flow_with([100], [FORWARD], [5.0])
    f = extract_features(flow).features
    assert all(np.isfinite(v) for v in f.values())
