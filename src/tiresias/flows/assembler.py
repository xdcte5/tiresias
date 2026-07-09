"""Flow assembler: groups packets into flows and flushes them.

A flow is flushed (emitted downstream and evicted) when **any** of:
  * it reaches the packet cap (classify early — this is what makes it real-time);
  * it has been idle longer than ``idle_timeout_s``;
  * its total lifetime exceeds ``active_timeout_s`` (a permanently-busy flow still
    yields a record periodically).

Flushed flows are delivered to an ``on_flush`` callback. ``add_packet`` may itself
flush (on cap); ``reap`` flushes aged flows and should be called periodically with
the current wall-clock time (the streaming pipeline drives this; batch/pcap callers
call ``flush_all`` at the end).
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import CONFIG, FlowConfig
from ..logging_setup import get_logger
from .key import FlowKey
from .record import BACKWARD, FORWARD, FlowRecord, ParsedPacket

log = get_logger(__name__)

FlushCallback = Callable[[FlowRecord], None]


class FlowAssembler:
    """Stateful, single-threaded flow table.

    Not thread-safe by design — drive it from one capture/consumer loop. The
    streaming pipeline (Sprint 4) owns the reaper cadence.
    """

    def __init__(
        self,
        on_flush: FlushCallback,
        config: FlowConfig | None = None,
    ) -> None:
        self.cfg = config or CONFIG.flow
        self._on_flush = on_flush
        self._flows: dict[FlowKey, FlowRecord] = {}
        # Counters for observability / smoke-testing.
        self.n_packets_seen = 0
        self.n_flows_flushed = 0
        self.n_flows_dropped_short = 0

    @property
    def active_flows(self) -> int:
        return len(self._flows)

    def add_packet(self, pkt: ParsedPacket) -> None:
        self.n_packets_seen += 1
        key, src_is_a = FlowKey.normalize(
            pkt.src_ip, pkt.src_port, pkt.dst_ip, pkt.dst_port, pkt.protocol
        )
        flow = self._flows.get(key)
        if flow is None:
            flow = FlowRecord(
                key=key,
                initiator=(pkt.src_ip, pkt.src_port),
                start_ts=pkt.ts,
                last_ts=pkt.ts,
            )
            self._flows[key] = flow

        direction = FORWARD if (pkt.src_ip, pkt.src_port) == flow.initiator else BACKWARD
        flow.add(pkt, direction)

        if flow.n_packets >= self.cfg.packet_cap:
            flow.flushed_on_cap = True
            self._flush(key, flow)

    def reap(self, now: float) -> int:
        """Flush idle/expired flows. Returns how many were flushed."""
        to_flush = [
            (k, f)
            for k, f in self._flows.items()
            if f.is_idle(now, self.cfg.idle_timeout_s)
            or f.is_expired(now, self.cfg.active_timeout_s)
        ]
        for k, f in to_flush:
            self._flush(k, f)
        return len(to_flush)

    def flush_all(self) -> int:
        """Flush every remaining flow (end of a pcap/batch). Returns count flushed."""
        count = 0
        for k, f in list(self._flows.items()):
            self._flush(k, f)
            count += 1
        return count

    def _flush(self, key: FlowKey, flow: FlowRecord) -> None:
        # Evict first so a re-arriving 5-tuple starts a fresh flow.
        self._flows.pop(key, None)
        if flow.n_packets < self.cfg.min_packets:
            self.n_flows_dropped_short += 1
            return
        self.n_flows_flushed += 1
        self._on_flush(flow)
