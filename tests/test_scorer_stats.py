"""Streaming scorer + rolling stats aggregation."""

import numpy as np

from tiresias.pipeline.scorer import StreamingScorer
from tiresias.pipeline.stats import RollingStats
from tiresias.synth.generate import PROFILE_BY_LABEL, generate_flow


def _flow(label, seed=0):
    rng = np.random.default_rng(seed)
    return generate_flow(PROFILE_BY_LABEL[label], rng, start_ts=1000.0, server_ip="93.1.2.3")


def test_scorer_produces_valid_scored_flow(trained_model):
    scorer = StreamingScorer(trained_model)
    scored = scorer.score(_flow("video_streaming", seed=3))
    assert scored.protocol in ("TCP", "UDP")
    assert ":" in scored.src and ":" in scored.dst
    assert 0.0 <= scored.confidence <= 1.0
    assert scored.n_packets > 0 and scored.bytes_total > 0
    assert scored.label in (*trained_model.classes, "unclassified")
    assert scored.top_probs  # non-empty top-k


def test_anomaly_flag_on_high_threshold(trained_model):
    # With a threshold of 1.01, nothing can clear it -> everything is anomalous.
    scorer = StreamingScorer(trained_model, anomaly_threshold=1.01)
    scored = scorer.score(_flow("gaming", seed=1))
    assert scored.anomalous is True
    assert scored.label == "unclassified"


def test_no_anomaly_on_zero_threshold(trained_model):
    scorer = StreamingScorer(trained_model, anomaly_threshold=0.0)
    scored = scorer.score(_flow("dns_background", seed=2))
    assert scored.anomalous is False
    assert scored.label != "unclassified"


def test_rolling_stats_aggregates(trained_model):
    scorer = StreamingScorer(trained_model, anomaly_threshold=0.0)
    stats = RollingStats(bucket_s=2.0, horizon_s=60)
    labels_seen = []
    for i, label in enumerate(["gaming", "gaming", "video_streaming"]):
        scored = scorer.score(_flow(label, seed=i))
        labels_seen.append(scored.label)
        stats.add(scored, now=1000.0 + i)  # deterministic bucket clock
    summary = stats.summary(trained_model.classes)
    assert summary.total_flows == 3
    assert sum(summary.per_class_flows.values()) == 3
    assert sum(summary.per_class_bytes.values()) > 0
    # 3 events across ~2 seconds -> at most 2 buckets of 2s.
    assert 1 <= len(summary.bandwidth_series) <= 2


def test_stats_horizon_evicts_old_buckets(trained_model):
    scorer = StreamingScorer(trained_model, anomaly_threshold=0.0)
    stats = RollingStats(bucket_s=1.0, horizon_s=3)  # keep 3 buckets
    for i in range(10):
        stats.add(scorer.score(_flow("web_browsing", seed=i)), now=2000.0 + i)
    summary = stats.summary(trained_model.classes)
    assert len(summary.bandwidth_series) <= 3  # old buckets evicted
    assert summary.total_flows == 10  # totals still cumulative
