"""FlowKey direction normalization: both directions collapse to one key."""

from tiresias.flows.key import FlowKey


def test_both_directions_same_key():
    fwd, src_is_a_fwd = FlowKey.normalize("10.0.0.1", 5000, "93.1.2.3", 443, "TCP")
    bwd, src_is_a_bwd = FlowKey.normalize("93.1.2.3", 443, "10.0.0.1", 5000, "TCP")
    assert fwd == bwd
    # Exactly one direction is "source == endpoint a".
    assert src_is_a_fwd != src_is_a_bwd


def test_protocol_separates_flows():
    tcp, _ = FlowKey.normalize("10.0.0.1", 5000, "93.1.2.3", 443, "TCP")
    udp, _ = FlowKey.normalize("10.0.0.1", 5000, "93.1.2.3", 443, "UDP")
    assert tcp != udp


def test_key_is_hashable_and_endpoints():
    k, _ = FlowKey.normalize("10.0.0.2", 1111, "10.0.0.1", 2222, "UDP")
    assert {k: 1}[k] == 1  # hashable
    # endpoint_a is the smaller endpoint tuple.
    assert k.endpoint_a < k.endpoint_b
