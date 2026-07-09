"""CLI: generate a synthetic labeled dataset (no capture needed).

    tiresias-synth --sessions 40 --out data/datasets/synth.parquet

Use this to exercise/train the whole pipeline before real captures exist. The
resulting parquet has the exact same schema a real-capture dataset would.
"""

from __future__ import annotations

import argparse

from ..logging_setup import get_logger
from ..models.dataset import LABEL_COL, SESSION_COL, dataset_from_labeled, save_dataset
from ..synth.generate import generate_dataset

log = get_logger("tiresias.synth")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a synthetic labeled dataset.")
    ap.add_argument("--sessions", type=int, default=30, help="Sessions per class.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/datasets/synth.parquet")
    args = ap.parse_args(argv)

    triples = generate_dataset(sessions_per_class=args.sessions, seed=args.seed)
    df = dataset_from_labeled(triples)
    path = save_dataset(df, args.out)
    log.info(
        "Generated %d flows across %d classes / %d sessions -> %s",
        len(df),
        df[LABEL_COL].nunique(),
        df[SESSION_COL].nunique(),
        path,
    )
    log.info("Per-class flow counts:\n%s", df[LABEL_COL].value_counts().to_string())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
