"""The flow key: a direction-normalized 5-tuple.

Both directions of a TCP/UDP conversation must map to a single flow. We canonicalise
by ordering the two ``(ip, port)`` endpoints, so ``A->B`` and ``B->A`` produce the
same :class:`FlowKey`. The *initiator* (source of the first packet seen) is tracked
separately on the flow record to define forward/backward direction.
"""

from __future__ import annotations

from dataclasses import dataclass

Endpoint = tuple[str, int]


@dataclass(frozen=True, slots=True)
class FlowKey:
    """Canonical, hashable 5-tuple. ``a`` is always the lexicographically smaller endpoint."""

    ip_a: str
    port_a: int
    ip_b: str
    port_b: int
    protocol: str  # "TCP" | "UDP"

    @classmethod
    def normalize(
        cls,
        src_ip: str,
        src_port: int,
        dst_ip: str,
        dst_port: int,
        protocol: str,
    ) -> tuple[FlowKey, bool]:
        """Return ``(key, src_is_endpoint_a)``.

        ``src_is_endpoint_a`` tells the caller whether the packet's source maps to
        endpoint ``a`` of the canonical key — used to establish the initiator once.
        """
        src: Endpoint = (src_ip, src_port)
        dst: Endpoint = (dst_ip, dst_port)
        if src <= dst:
            return cls(src_ip, src_port, dst_ip, dst_port, protocol), True
        return cls(dst_ip, dst_port, src_ip, src_port, protocol), False

    @property
    def endpoint_a(self) -> Endpoint:
        return (self.ip_a, self.port_a)

    @property
    def endpoint_b(self) -> Endpoint:
        return (self.ip_b, self.port_b)

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.ip_a}:{self.port_a} <-> {self.ip_b}:{self.port_b} [{self.protocol}]"
