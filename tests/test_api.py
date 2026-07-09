"""FastAPI backend: REST endpoints and the live WebSocket stream."""

import pytest
from fastapi.testclient import TestClient

from tiresias.api.server import create_app
from tiresias.pipeline.sources import SourceSpec


def test_rest_endpoints_with_no_source(trained_model):
    app = create_app(trained_model, SourceSpec(kind="none"))
    with TestClient(app) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        classes = client.get("/classes").json()
        assert set(classes) == set(trained_model.classes)
        summary = client.get("/stats/summary").json()
        assert summary["total_flows"] == 0
        assert summary["classes"] == trained_model.classes


def test_websocket_snapshot_and_live_stream(trained_model):
    # Fast synthetic source so a flow arrives quickly.
    app = create_app(trained_model, SourceSpec(kind="synthetic", flows_per_sec=60.0, seed=1))
    with TestClient(app) as client:
        with client.websocket_connect("/ws/flows") as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "snapshot"
            assert "summary" in snapshot and "flows" in snapshot

            # Then a live scored flow should arrive.
            msg = ws.receive_json()
            assert msg["type"] == "flow"
            flow = msg["flow"]
            assert flow["label"] in (*trained_model.classes, "unclassified")
            assert flow["bytes_total"] > 0
            assert 0.0 <= flow["confidence"] <= 1.0


def test_summary_reflects_streamed_flows(trained_model):
    app = create_app(trained_model, SourceSpec(kind="synthetic", flows_per_sec=80.0, seed=2))
    with TestClient(app) as client:
        with client.websocket_connect("/ws/flows") as ws:
            ws.receive_json()  # snapshot
            for _ in range(5):
                ws.receive_json()  # drain a few live flows
        summary = client.get("/stats/summary").json()
        assert summary["total_flows"] >= 1
        assert summary["bandwidth_series"]  # at least one bucket recorded


def test_pcap_source_smoke(trained_model, tmp_path):
    # Build a tiny pcap and confirm the pcap source drives at least one scored flow.
    pytest.importorskip("scapy.all")
    from scapy.all import IP, TCP, Raw, wrpcap

    from tiresias.synth.tls_bytes import client_hello

    pkts = []
    ch = client_hello("www.youtube.com")
    seq = [
        (IP(src="10.0.0.5", dst="93.1.2.3") / TCP(sport=5001, dport=443) / Raw(ch), 0.0),
        (IP(src="93.1.2.3", dst="10.0.0.5") / TCP(sport=443, dport=5001) / Raw(b"x" * 400), 0.1),
        (IP(src="10.0.0.5", dst="93.1.2.3") / TCP(sport=5001, dport=443) / Raw(b"y" * 80), 0.2),
        (IP(src="93.1.2.3", dst="10.0.0.5") / TCP(sport=443, dport=5001) / Raw(b"z" * 500), 0.3),
        (IP(src="10.0.0.5", dst="93.1.2.3") / TCP(sport=5001, dport=443) / Raw(b"y" * 80), 0.4),
    ]
    for pkt, dt in seq:
        pkt.time = 1000.0 + dt
        pkts.append(pkt)
    path = tmp_path / "s.pcap"
    wrpcap(str(path), pkts)

    app = create_app(trained_model, SourceSpec(kind="pcap", pcap_path=str(path)))
    with TestClient(app) as client:
        with client.websocket_connect("/ws/flows") as ws:
            ws.receive_json()  # snapshot
            msg = ws.receive_json()  # scored flow from the replayed pcap
            assert msg["type"] == "flow"
            assert msg["flow"]["protocol"] == "TCP"
