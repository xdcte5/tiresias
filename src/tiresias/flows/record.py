"""In-memory representation of a flow as it accumulates, plus the parsed packet
the assembler consumes.

``ParsedPacket`` deliberately decouples the assembler from scapy: capture parses
scapy packets into this plain struct, and every downstream stage (assembler,
features, tests) works on ``ParsedPacket`` / ``FlowRecord`` only. That means the
whole pipeline is testable without live capture or even scapy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .key import FlowKey

FORWARD = 1  # from the flow initiator (first packet's source)
BACKWARD = -1


@dataclass(slots=True)
class ParsedPacket:
    """A single captured packet, normalized and payload-stripped."""

    ts: float
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str  # "TCP" | "UDP"
    size: int  # bytes on the wire (IP total length), NOT payload content
    # Raw TLS ClientHello record bytes if this packet carried one, else None.
    # Only the handshake bytes are kept; no application payload is ever stored.
    tls_client_hello: bytes | None = None


@dataclass(slots=True)
class FlowRecord:
    """Accumulated per-flow state. One per canonical 5-tuple."""

    key: FlowKey
    initiator: tuple[str, int]  # (ip, port) that sent the first packet
    start_ts: float
    last_ts: float
    sizes: list[int] = field(default_factory=list)  # signed by direction
    timestamps: list[float] = field(default_factory=list)
    directions: list[int] = field(default_factory=list)  # +1 fwd / -1 bwd
    client_hello: bytes | None = None
    # Set True when flushed because it hit the packet cap (vs. aged out).
    flushed_on_cap: bool = False

    @property
    def n_packets(self) -> int:
        return len(self.sizes)

    @property
    def duration(self) -> float:
        return max(0.0, self.last_ts - self.start_ts)

    @property
    def n_forward(self) -> int:
        return sum(1 for d in self.directions if d == FORWARD)

    @property
    def n_backward(self) -> int:
        return sum(1 for d in self.directions if d == BACKWARD)

    def add(self, pkt: ParsedPacket, direction: int) -> None:
        self.sizes.append(pkt.size * direction)
        self.timestamps.append(pkt.ts)
        self.directions.append(direction)
        self.last_ts = pkt.ts
        if self.client_hello is None and pkt.tls_client_hello is not None:
            self.client_hello = pkt.tls_client_hello

    def is_idle(self, now: float, timeout: float) -> bool:
        return (now - self.last_ts) >= timeout

    def is_expired(self, now: float, active_timeout: float) -> bool:
        return (now - self.start_ts) >= active_timeout

    def to_row(self) -> dict:
        """Flat, serialisable dict for parquet/JSON persistence."""
        return {
            "ip_a": self.key.ip_a,
            "port_a": self.key.port_a,
            "ip_b": self.key.ip_b,
            "port_b": self.key.port_b,
            "protocol": self.key.protocol,
            "initiator_ip": self.initiator[0],
            "initiator_port": self.initiator[1],
            "start_ts": self.start_ts,
            "last_ts": self.last_ts,
            "duration": self.duration,
            "n_packets": self.n_packets,
            # Sequences stored as lists; pyarrow persists these as list columns.
            "sizes": list(self.sizes),
            "timestamps": list(self.timestamps),
            "directions": list(self.directions),
            "client_hello": self.client_hello,  # bytes | None
        }
