"""End-to-end Sprint 1: scapy packets -> pcap -> iter_pcap -> assembler -> parquet."""

from pathlib import Path

import pytest

from tiresias.capture.agent import iter_pcap
from tiresias.config import FlowConfig
from tiresias.flows.assembler import FlowAssembler
from tiresias.flows.io import read_flows_parquet, write_flows_parquet
from tiresias.synth.tls_bytes import client_hello

scapy_all = pytest.importorskip("scapy.all")


def _build_pcap(path: Path) -> None:
    from scapy.all import IP, TCP, UDP, Raw, wrpcap

    pkts = []
    ch = client_hello("www.youtube.com")
    # TCP flow: SYN, client hello, a few data segments both directions.
    base = 1000.0
    exchange = [
        (IP(src="10.0.0.5", dst="93.1.2.3") / TCP(sport=5001, dport=443, flags="S"), 0.0, None),
        (IP(src="10.0.0.5", dst="93.1.2.3") / TCP(sport=5001, dport=443) / Raw(ch), 0.1, None),
        (IP(src="93.1.2.3", dst="10.0.0.5") / TCP(sport=443, dport=5001) / Raw(b"x" * 200), 0.2, None),
        (IP(src="10.0.0.5", dst="93.1.2.3") / TCP(sport=5001, dport=443) / Raw(b"y" * 50), 0.3, None),
        (IP(src="93.1.2.3", dst="10.0.0.5") / TCP(sport=443, dport=5001) / Raw(b"z" * 300), 0.4, None),
    ]
    # UDP flow (e.g. a DNS-ish exchange).
    exchange += [
        (IP(src="10.0.0.5", dst="1.1.1.1") / UDP(sport=6000, dport=53) / Raw(b"q" * 40), 0.5, None),
        (IP(src="1.1.1.1", dst="10.0.0.5") / UDP(sport=53, dport=6000) / Raw(b"a" * 90), 0.6, None),
        (IP(src="10.0.0.5", dst="1.1.1.1") / UDP(sport=6000, dport=53) / Raw(b"q" * 42), 0.7, None),
        (IP(src="1.1.1.1", dst="10.0.0.5") / UDP(sport=53, dport=6000) / Raw(b"a" * 80), 0.8, None),
    ]
    for pkt, dt, _ in exchange:
        pkt.time = base + dt
        pkts.append(pkt)
    wrpcap(str(path), pkts)


def test_pcap_roundtrip(tmp_path):
    pcap = tmp_path / "session.pcap"
    _build_pcap(pcap)

    flows = []
    asm = FlowAssembler(on_flush=flows.append, config=FlowConfig(min_packets=1, packet_cap=100))
    for pkt in iter_pcap(pcap):
        asm.add_packet(pkt)
    asm.flush_all()

    # Two flows: one TCP (youtube) and one UDP (dns).
    assert len(flows) == 2
    tcp = next(f for f in flows if f.key.protocol == "TCP")
    udp = next(f for f in flows if f.key.protocol == "UDP")

    assert tcp.n_packets == 5
    assert tcp.client_hello is not None  # ClientHello captured off the TCP payload
    assert tcp.client_hello[0] == 0x16
    assert tcp.n_forward >= 1 and tcp.n_backward >= 1
    assert udp.n_packets == 4
    assert udp.client_hello is None

    # Parquet round-trip preserves the essentials.
    out = tmp_path / "flows.parquet"
    n = write_flows_parquet(flows, out)
    assert n == 2
    loaded = read_flows_parquet(out)
    loaded_tcp = next(f for f in loaded if f.key.protocol == "TCP")
    assert loaded_tcp.n_packets == 5
    assert loaded_tcp.client_hello == tcp.client_hello
    assert loaded_tcp.sizes == tcp.sizes
