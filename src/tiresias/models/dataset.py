"""Build a labeled feature table (DataFrame/parquet) from flows.

Two entry points, sharing one featurizer so the feature schema is identical:

  * :func:`dataset_from_labeled` — ``(flow, label, session_id)`` triples with known
    labels (the synthetic generator, or any externally-labeled source).
  * :func:`dataset_from_captures` — real captured flows, labeled by TLS **SNI**, with
    session ids supplied by the collection workflow (e.g. one capture file = one
    session). Flows whose SNI doesn't map to a class are dropped as ``unknown``.

The resulting frame always has: every feature column, the metadata columns
(``sni``/``ja3``/``ja3_hash``), plus ``label`` and ``session_id``. Downstream training
selects which feature *groups* to use — SNI/JA3 stay out of the model by default.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from ..config import CONFIG, FeatureConfig
from ..features.extract import (
    META_COLUMNS,
    extract_features,
    feature_group_columns,
)
from ..features.labeling import UNKNOWN_LABEL, label_for_sni
from ..flows.record import FlowRecord

LABEL_COL = "label"
SESSION_COL = "session_id"


def all_feature_columns(cfg: FeatureConfig | None = None) -> list[str]:
    groups = feature_group_columns(cfg)
    cols: list[str] = []
    for g in ("flow_stats", "tls_shape", "raw_seq", "tls_ja3"):
        cols.extend(groups[g])
    return cols


def _row(flow: FlowRecord, label: str, session_id: str, cfg: FeatureConfig) -> dict:
    fr = extract_features(flow, cfg)
    row: dict[str, object] = dict(fr.features)
    row.update({k: fr.meta.get(k) for k in META_COLUMNS})
    row[LABEL_COL] = label
    row[SESSION_COL] = session_id
    return row


def dataset_from_labeled(
    triples: Iterable[tuple[FlowRecord, str, str]],
    cfg: FeatureConfig | None = None,
) -> pd.DataFrame:
    cfg = cfg or CONFIG.features
    rows = [_row(flow, label, sid, cfg) for flow, label, sid in triples]
    return pd.DataFrame(rows)


def dataset_from_captures(
    flows: Iterable[tuple[FlowRecord, str]],
    cfg: FeatureConfig | None = None,
    keep_unknown: bool = False,
) -> pd.DataFrame:
    """``flows`` is ``(flow, session_id)``; label is derived from each flow's SNI."""
    cfg = cfg or CONFIG.features
    rows = []
    for flow, sid in flows:
        fr = extract_features(flow, cfg)
        label = label_for_sni(fr.meta.get("sni"))  # type: ignore[arg-type]
        if label == UNKNOWN_LABEL and not keep_unknown:
            continue
        row: dict[str, object] = dict(fr.features)
        row.update({k: fr.meta.get(k) for k in META_COLUMNS})
        row[LABEL_COL] = label
        row[SESSION_COL] = sid
        rows.append(row)
    return pd.DataFrame(rows)


def save_dataset(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def load_dataset(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)
