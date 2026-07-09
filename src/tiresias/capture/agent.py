"""Capture agent: turn scapy packets (live iface or pcap file) into ``ParsedPacket``.

scapy is imported lazily so the pure helpers here and the rest of the pipeline can be
imported/tested without paying scapy's import cost or requiring capture privileges.

Two entry points:
  * :func:`iter_pcap` — offline, no privileges, fully deterministic (used by tests
    and by the "replay a capture" demo path).
  * :func:`sniff_live` — live capture; needs raw-socket privileges (see README).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import CONFIG, CaptureConfig
from ..logging_setup import get_logger
from .tls_detect import extract_client_hello

if TYPE_CHECKING:
    from ..flows.record import ParsedPacket

log = get_logger(__name__)


def _parse(pkt) -> ParsedPacket | None:
    """Convert a scapy packet to a ParsedPacket, or None if not IP+TCP/UDP."""
    # Import via scapy.all so every layer + link-layer (DLT) binding is registered
    # — otherwise raw-IP pcaps (DLT 228) and some capture formats decode as Raw.
    import scapy.all  # noqa: F401
    from scapy.layers.inet import IP, TCP, UDP
    from scapy.layers.inet6 import IPv6

    from ..flows.record import ParsedPacket

    if IP in pkt:
        ip = pkt[IP]
        src_ip, dst_ip = ip.src, ip.dst
    elif IPv6 in pkt:
        ip = pkt[IPv6]
        src_ip, dst_ip = ip.src, ip.dst
    else:
        return None

    if TCP in pkt:
        l4 = pkt[TCP]
        proto = "TCP"
    elif UDP in pkt:
        l4 = pkt[UDP]
        proto = "UDP"
    else:
        return None

    size = len(bytes(ip))  # L3 bytes on the wire (header + payload)

    client_hello = None
    if proto == "TCP":
        payload = bytes(l4.payload)
        if payload:
            client_hello = extract_client_hello(payload)

    return ParsedPacket(
        ts=float(pkt.time),
        src_ip=str(src_ip),
        dst_ip=str(dst_ip),
        src_port=int(l4.sport),
        dst_port=int(l4.dport),
        protocol=proto,
        size=size,
        tls_client_hello=client_hello,
    )


def iter_pcap(path: str | Path) -> Iterator[ParsedPacket]:
    """Yield ParsedPackets from a pcap/pcapng file, in capture order."""
    import scapy.all  # noqa: F401 - ensure DLT/layer bindings registered before reading
    from scapy.utils import PcapReader

    with PcapReader(str(path)) as reader:
        for pkt in reader:
            parsed = _parse(pkt)
            if parsed is not None:
                yield parsed


def sniff_live(
    on_packet: Callable[[ParsedPacket], None],
    config: CaptureConfig | None = None,
    seconds: float | None = None,
    max_packets: int | None = None,
) -> None:
    """Live-capture on an interface, invoking ``on_packet`` per parsed IP packet.

    Blocks until ``seconds``/``max_packets`` reached (or Ctrl-C). Needs raw-socket
    privileges. Only headers are needed, so a short snaplen is requested.
    """
    from scapy.sendrecv import sniff

    cfg = config or CONFIG.capture
    log.info(
        "Live capture on iface=%s filter=%r snaplen=%d", cfg.interface, cfg.bpf_filter, cfg.snaplen
    )

    def _handle(pkt) -> None:
        parsed = _parse(pkt)
        if parsed is not None:
            on_packet(parsed)

    sniff(
        iface=None if cfg.interface == "any" else cfg.interface,
        filter=cfg.bpf_filter,
        prn=_handle,
        store=False,
        timeout=seconds,
        count=max_packets or 0,
    )
