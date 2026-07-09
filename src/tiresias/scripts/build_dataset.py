"""CLI: build an SNI-labeled dataset from captured flow parquet files.

Each ``*.parquet`` flow dump under ``--flows-dir`` is treated as one **session**
(its filename, minus extension, is the ``session_id``) so the session-based train/
test split never leaks flows across the split. Labels come from each flow's TLS SNI;
flows with no mappable SNI are dropped unless ``--keep-unknown``.

    tiresias-build-dataset --flows-dir data/flows --out data/datasets/captured.parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..flows.io import iter_flow_files, read_flows_parquet
from ..logging_setup import get_logger
from ..models.dataset import LABEL_COL, SESSION_COL, dataset_from_captures, save_dataset

log = get_logger("tiresias.build_dataset")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build an SNI-labeled dataset from flow dumps.")
    ap.add_argument("--flows-dir", default="data/flows", help="Dir of *.parquet flow dumps.")
    ap.add_argument("--out", default="data/datasets/captured.parquet")
    ap.add_argument("--keep-unknown", action="store_true", help="Keep SNI-unmatched flows.")
    args = ap.parse_args(argv)

    labeled: list[tuple] = []
    n_files = 0
    for fpath in iter_flow_files(args.flows_dir):
        n_files += 1
        session_id = Path(fpath).stem
        for flow in read_flows_parquet(fpath):
            labeled.append((flow, session_id))

    if not labeled:
        log.error("No flows found under %s — capture some first.", args.flows_dir)
        return 1

    df = dataset_from_captures(labeled, keep_unknown=args.keep_unknown)
    if df.empty:
        log.error("All flows were SNI-unmatched (unknown). Nothing to write.")
        return 1

    path = save_dataset(df, args.out)
    log.info(
        "Built dataset from %d files: %d labeled flows, %d classes, %d sessions -> %s",
        n_files,
        len(df),
        df[LABEL_COL].nunique(),
        df[SESSION_COL].nunique(),
        path,
    )
    log.info("Per-class flow counts:\n%s", df[LABEL_COL].value_counts().to_string())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
