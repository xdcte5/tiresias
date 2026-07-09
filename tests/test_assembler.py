"""Flow assembler lifecycle: grouping, direction, and all three flush paths."""

from tiresias.config import FlowConfig
from tiresias.flows.assembler import FlowAssembler
from tiresias.flows.record import BACKWARD, FORWARD, ParsedPacket


def mkpkt(ts, sport=5000, dport=443, src="10.0.0.1", dst="93.1.2.3", size=100, proto="TCP", ch=None):
    return ParsedPacket(ts, src, dst, sport, dport, proto, size, ch)


def collect_assembler(cfg=None):
    flushed = []
    return FlowAssembler(on_flush=flushed.append, config=cfg), flushed


def test_bidirectional_grouping_and_direction():
    asm, flushed = collect_assembler(FlowConfig(min_packets=1, packet_cap=100))
    # client -> server, then server -> client: one flow, opposite directions.
    asm.add_packet(mkpkt(1.0, src="10.0.0.1", sport=5000, dst="93.1.2.3", dport=443))
    asm.add_packet(mkpkt(1.1, src="93.1.2.3", sport=443, dst="10.0.0.1", dport=5000))
    assert asm.active_flows == 1
    asm.flush_all()
    (flow,) = flushed
    assert flow.n_packets == 2
    assert flow.directions == [FORWARD, BACKWARD]
    assert flow.n_forward == 1 and flow.n_backward == 1
    # initiator is the first packet's source.
    assert flow.initiator == ("10.0.0.1", 5000)


def test_packet_cap_flush():
    asm, flushed = collect_assembler(FlowConfig(min_packets=1, packet_cap=5))
    for i in range(5):
        asm.add_packet(mkpkt(1.0 + i * 0.01))
    # Hitting the cap flushes immediately (real-time early classification).
    assert len(flushed) == 1
    assert flushed[0].flushed_on_cap is True
    assert asm.active_flows == 0


def test_idle_timeout_flush():
    asm, flushed = collect_assembler(FlowConfig(min_packets=1, packet_cap=100, idle_timeout_s=15))
    asm.add_packet(mkpkt(1.0))
    asm.add_packet(mkpkt(2.0))
    asm.reap(now=10.0)  # only 8s idle -> no flush
    assert not flushed
    asm.reap(now=20.0)  # 18s idle -> flush
    assert len(flushed) == 1
    assert flushed[0].flushed_on_cap is False


def test_active_timeout_flush():
    asm, flushed = collect_assembler(
        FlowConfig(min_packets=1, packet_cap=1000, idle_timeout_s=15, active_timeout_s=30)
    )
    for i in range(10):
        asm.add_packet(mkpkt(1.0 + i))  # steady 1s cadence, never idle
    asm.reap(now=32.0)  # lifetime 31s > active_timeout
    assert len(flushed) == 1


def test_min_packets_drop():
    asm, flushed = collect_assembler(FlowConfig(min_packets=4, packet_cap=100))
    asm.add_packet(mkpkt(1.0))
    asm.add_packet(mkpkt(1.1))
    asm.flush_all()
    assert not flushed  # too short -> dropped, not emitted
    assert asm.n_flows_dropped_short == 1


def test_rearrival_after_flush_starts_new_flow():
    asm, flushed = collect_assembler(FlowConfig(min_packets=1, packet_cap=2))
    asm.add_packet(mkpkt(1.0))
    asm.add_packet(mkpkt(1.1))  # cap=2 -> flush
    assert len(flushed) == 1 and asm.active_flows == 0
    asm.add_packet(mkpkt(2.0))  # same 5-tuple re-arrives -> brand new flow
    assert asm.active_flows == 1


def test_client_hello_captured_on_flow():
    asm, flushed = collect_assembler(FlowConfig(min_packets=1, packet_cap=100))
    asm.add_packet(mkpkt(1.0, ch=b"\x16\x03\x01hello"))
    asm.add_packet(mkpkt(1.1))
    asm.flush_all()
    assert flushed[0].client_hello == b"\x16\x03\x01hello"
