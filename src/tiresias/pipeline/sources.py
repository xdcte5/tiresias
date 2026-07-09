"""Flow sources: async producers that push FlowRecords onto a queue.

Three kinds, all interchangeable behind the same queue contract:
  * ``synthetic`` — continuously generate class-characteristic flows (default; lets
    the dashboard demo live without any capture or pcap).
  * ``pcap``      — replay a captured file through the assembler.
  * ``live``      — real capture via scapy (needs privileges).

The scorer/consumer downstream never knows or cares which source produced a flow.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import numpy as np

from ..capture.agent import iter_pcap, sniff_live
from ..config import CONFIG, CaptureConfig
from ..flows.assembler import FlowAssembler
from ..flows.record import FlowRecord
from ..logging_setup import get_logger
from ..synth.generate import PROFILES, SessionStyle, generate_flow

log = get_logger("tiresias.source")


@dataclass
class SourceSpec:
    kind: str = "synthetic"  # synthetic | pcap | live | none
    pcap_path: str | None = None
    iface: str | None = None
    flows_per_sec: float = 4.0
    seed: int | None = None


async def run_source(spec: SourceSpec, queue: asyncio.Queue[FlowRecord], stop: asyncio.Event):
    if spec.kind == "synthetic":
        await _synthetic(spec, queue, stop)
    elif spec.kind == "pcap":
        await _pcap(spec, queue, stop)
    elif spec.kind == "live":
        await _live(spec, queue, stop)
    elif spec.kind == "none":
        await stop.wait()
    else:
        raise ValueError(f"unknown source kind: {spec.kind}")


async def _synthetic(spec: SourceSpec, queue, stop: asyncio.Event) -> None:
    rng = np.random.default_rng(spec.seed)
    log.info("Synthetic flow source at ~%.1f flows/s", spec.flows_per_sec)
    while not stop.is_set():
        profile = PROFILES[int(rng.integers(0, len(PROFILES)))]
        style = SessionStyle(
            size_scale=float(rng.lognormal(0.0, 0.2)),
            iat_scale=float(rng.lognormal(0.0, 0.28)),
            download_ratio=profile.download_ratio,
        )
        server_ip = f"93.{int(rng.integers(0,256))}.{int(rng.integers(0,256))}.{int(rng.integers(1,255))}"
        flow = generate_flow(profile, rng, start_ts=time.time(), server_ip=server_ip, style=style)
        await queue.put(flow)
        # Poisson-ish spacing around the target rate.
        delay = float(rng.exponential(1.0 / max(spec.flows_per_sec, 0.1)))
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            pass


async def _drain_via_assembler(packets_iter, queue, stop: asyncio.Event, pace: bool) -> None:
    """Feed a packet iterator through the assembler in a worker thread, pushing
    flushed flows to the queue on the event loop."""
    loop = asyncio.get_running_loop()

    def on_flush(flow: FlowRecord) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, flow)

    assembler = FlowAssembler(on_flush=on_flush)

    def work() -> None:
        last = 0.0
        for pkt in packets_iter:
            if stop.is_set():
                break
            assembler.add_packet(pkt)
            assembler.reap(pkt.ts)
            if pace and last:
                dt = min(0.05, max(0.0, pkt.ts - last))
                if dt:
                    time.sleep(dt)
            last = pkt.ts
        assembler.flush_all()

    await asyncio.to_thread(work)


async def _pcap(spec: SourceSpec, queue, stop: asyncio.Event) -> None:
    if not spec.pcap_path:
        raise ValueError("pcap source requires pcap_path")
    log.info("Replaying pcap %s", spec.pcap_path)
    await _drain_via_assembler(iter_pcap(spec.pcap_path), queue, stop, pace=True)


async def _live(spec: SourceSpec, queue, stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    cfg = CaptureConfig(interface=spec.iface or CONFIG.capture.interface)
    log.info("Live capture source on %s", cfg.interface)

    def on_flush(flow: FlowRecord) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, flow)

    assembler = FlowAssembler(on_flush=on_flush)
    state = {"last_reap": time.time()}

    def on_packet(pkt) -> None:
        assembler.add_packet(pkt)
        now = time.time()
        if now - state["last_reap"] >= CONFIG.flow.reap_interval_s:
            assembler.reap(now)
            state["last_reap"] = now

    def work() -> None:
        while not stop.is_set():
            sniff_live(on_packet, config=cfg, seconds=1.0)
            assembler.reap(time.time())

    await asyncio.to_thread(work)
