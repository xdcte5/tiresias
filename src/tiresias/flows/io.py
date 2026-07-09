"""Persist / load flow records as parquet.

Flow dumps contain real traffic metadata and are gitignored — this is only for the
local training-data workflow. Sequences are stored as list columns; ``client_hello``
is stored as an optional binary column.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import pandas as pd

from .key import FlowKey
from .record import FlowRecord


def flows_to_frame(flows: Iterable[FlowRecord]) -> pd.DataFrame:
    return pd.DataFrame([f.to_row() for f in flows])


def write_flows_parquet(flows: Iterable[FlowRecord], path: str | Path) -> int:
    """Write flows to a parquet file. Returns the number of rows written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = flows_to_frame(flows)
    df.to_parquet(path, index=False)
    return len(df)


def _row_to_record(row: dict) -> FlowRecord:
    key = FlowKey(
        ip_a=row["ip_a"],
        port_a=int(row["port_a"]),
        ip_b=row["ip_b"],
        port_b=int(row["port_b"]),
        protocol=row["protocol"],
    )
    ch = row.get("client_hello")
    rec = FlowRecord(
        key=key,
        initiator=(row["initiator_ip"], int(row["initiator_port"])),
        start_ts=float(row["start_ts"]),
        last_ts=float(row["last_ts"]),
        sizes=list(row["sizes"]),
        timestamps=list(row["timestamps"]),
        directions=list(row["directions"]),
        client_hello=bytes(ch) if ch is not None else None,
    )
    return rec


def read_flows_parquet(path: str | Path) -> list[FlowRecord]:
    df = pd.read_parquet(path)
    return [_row_to_record(r) for r in df.to_dict(orient="records")]


def iter_flow_files(root: str | Path) -> Iterator[Path]:
    """Yield every ``*.parquet`` under ``root`` (recursively), sorted."""
    yield from sorted(Path(root).rglob("*.parquet"))
