"""FastAPI backend: live scored-flow WebSocket + REST summary.

    tiresias-serve                       # synthetic source (no capture needed)
    tiresias-serve --source pcap --pcap data/pcaps/x.pcap
    sudo tiresias-serve --source live --iface wlan0

Endpoints:
  * ``GET  /healthz``        — liveness + model/source info
  * ``GET  /classes``        — the model's class list
  * ``GET  /stats/summary``  — rolling bandwidth-by-class + per-class counts (REST)
  * ``WS   /ws/flows``       — snapshot then a live stream of scored flows
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ..config import CONFIG
from ..logging_setup import get_logger
from ..models.registry import Model
from ..pipeline.scored import ScoredFlow, Summary
from ..pipeline.scorer import StreamingScorer
from ..pipeline.sources import SourceSpec, run_source
from ..pipeline.stats import RollingStats

log = get_logger("tiresias.api")


class ConnectionManager:
    """Tracks WebSocket clients + a ring buffer of recent flows for connect snapshots."""

    def __init__(self, recent_size: int = 100) -> None:
        self.active: set[WebSocket] = set()
        self.recent: deque[ScoredFlow] = deque(maxlen=recent_size)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, scored: ScoredFlow) -> None:
        self.recent.append(scored)
        payload = {"type": "flow", "flow": scored.model_dump()}
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001 - drop broken sockets
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


def create_app(model: Model, source: SourceSpec | None = None) -> FastAPI:
    source = source or SourceSpec()
    manager = ConnectionManager()
    scorer = StreamingScorer(model)
    stats = RollingStats()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        queue: asyncio.Queue[object] = asyncio.Queue(maxsize=1000)
        stop = asyncio.Event()

        async def consume() -> None:
            while not stop.is_set():
                try:
                    flow = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                scored = scorer.score(flow)
                stats.add(scored)
                await manager.broadcast(scored)

        producer = asyncio.create_task(run_source(source, queue, stop))
        consumer = asyncio.create_task(consume())
        log.info("Serving: source=%s, %d classes", source.kind, len(model.classes))
        try:
            yield
        finally:
            stop.set()
            for task in (producer, consumer):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Tiresias", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # dev: allow the Vite dashboard origin
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok", "source": source.kind, "n_classes": len(model.classes)}

    @app.get("/classes")
    async def classes() -> list[str]:
        return model.classes

    @app.get("/stats/summary", response_model=Summary)
    async def summary() -> Summary:
        return stats.summary(model.classes)

    @app.websocket("/ws/flows")
    async def ws_flows(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "flows": [f.model_dump() for f in manager.recent],
                    "summary": stats.summary(model.classes).model_dump(),
                }
            )
            while True:
                # Park; broadcasts are pushed from the consumer task. A client may
                # send pings/filters here in future.
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception:  # noqa: BLE001
            manager.disconnect(websocket)

    return app


def _load_model(path: str) -> Model:
    if not Path(path).exists():
        raise SystemExit(
            f"Model not found at {path}. Train one first: tiresias-train "
            f"(after tiresias-synth to create a dataset)."
        )
    return Model.load(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the Tiresias live backend.")
    ap.add_argument("--model", default=CONFIG.inference.model_path)
    ap.add_argument("--source", default="synthetic", choices=["synthetic", "pcap", "live", "none"])
    ap.add_argument("--pcap", default=None)
    ap.add_argument("--iface", default=None)
    ap.add_argument("--flows-per-sec", type=float, default=4.0)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    import uvicorn

    model = _load_model(args.model)
    spec = SourceSpec(
        kind=args.source, pcap_path=args.pcap, iface=args.iface, flows_per_sec=args.flows_per_sec
    )
    app = create_app(model, spec)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
