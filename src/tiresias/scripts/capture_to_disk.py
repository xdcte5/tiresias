"""CLI: capture flows (live iface or replay a pcap) and dump them to parquet.

Examples
--------
Offline (no privileges), replay a capture::

    tiresias-capture --pcap data/pcaps/session.pcap --out data/flows/session.parquet

Live capture for 60s on an interface (needs raw-socket privileges)::

    sudo tiresias-capture --iface wlan0 --seconds 60 --out data/flows/live.parquet
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from ..capture.agent import iter_pcap, sniff_live
from ..config import CONFIG
from ..flows.assembler import FlowAssembler
from ..flows.io import write_flows_parquet
from ..flows.record import FlowRecord
from ..logging_setup import get_logger

log = get_logger("tiresias.capture")


def _run_pcap(path: str, assembler: FlowAssembler) -> None:
    last_ts = 0.0
    for pkt in iter_pcap(path):
        assembler.add_packet(pkt)
        last_ts = pkt.ts
        # Age out idle flows using the capture's own clock (deterministic replay).
        assembler.reap(last_ts)
    assembler.flush_all()


def _run_live(iface: str | None, seconds: float | None, max_packets: int | None,
              assembler: FlowAssembler) -> None:
    cfg = CONFIG.capture
    if iface:
        cfg = type(cfg)(interface=iface, bpf_filter=cfg.bpf_filter, snaplen=cfg.snaplen)
    # Reap on wall-clock as packets arrive; sniff_live blocks until timeout/count.
    state = {"last_reap": time.time()}

    def on_packet(pkt) -> None:
        assembler.add_packet(pkt)
        now = time.time()
        if now - state["last_reap"] >= CONFIG.flow.reap_interval_s:
            assembler.reap(now)
            state["last_reap"] = now

    sniff_live(on_packet, config=cfg, seconds=seconds, max_packets=max_packets)
    assembler.reap(time.time())
    assembler.flush_all()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capture/replay flows to parquet.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pcap", help="Replay a pcap/pcapng file (no privileges needed).")
    src.add_argument("--iface", help="Live capture interface (needs privileges).")
    ap.add_argument("--seconds", type=float, default=None, help="Live capture duration.")
    ap.add_argument("--max-packets", type=int, default=None, help="Live capture packet cap.")
    ap.add_argument("--out", required=True, help="Output parquet path.")
    args = ap.parse_args(argv)

    flows: list[FlowRecord] = []
    assembler = FlowAssembler(on_flush=flows.append)

    if args.pcap:
        log.info("Replaying %s", args.pcap)
        _run_pcap(args.pcap, assembler)
    else:
        log.info("Live capturing on %s", args.iface)
        _run_live(args.iface, args.seconds, args.max_packets, assembler)

    n = write_flows_parquet(flows, args.out)
    log.info(
        "packets=%d flushed=%d dropped_short=%d -> wrote %d flows to %s",
        assembler.n_packets_seen,
        assembler.n_flows_flushed,
        assembler.n_flows_dropped_short,
        n,
        Path(args.out),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
