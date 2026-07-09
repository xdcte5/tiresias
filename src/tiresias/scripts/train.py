"""CLI: train the baseline, save the model artifact + evaluation report.

    tiresias-train --dataset data/datasets/synth.parquet

Trains RandomForest (and LightGBM if installed), evaluates on a session-based split,
writes the confusion matrix + per-class report, runs a feature-group ablation that
exposes why JA3 is excluded, and saves the headline model to
``artifacts/baseline_rf.joblib`` for the live scorer to load.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..config import CONFIG
from ..features.extract import DEFAULT_GROUPS, feature_columns
from ..logging_setup import get_logger
from ..models.dataset import LABEL_COL, SESSION_COL, load_dataset
from ..models.evaluate import plot_confusion_matrix, render_report_md
from ..models.train_baseline import ablation_accuracy, train_and_evaluate

log = get_logger("tiresias.train")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train + evaluate the baseline classifier.")
    ap.add_argument("--dataset", default="data/datasets/synth.parquet")
    ap.add_argument("--model-out", default=CONFIG.inference.model_path)
    ap.add_argument("--report-dir", default="reports")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--models", nargs="+", default=["rf", "lightgbm"],
                    help="Which model types to train.")
    args = ap.parse_args(argv)

    if not Path(args.dataset).exists():
        log.error("Dataset %s not found. Generate one: tiresias-synth --out %s",
                  args.dataset, args.dataset)
        return 1

    df = load_dataset(args.dataset)
    dataset_desc = (
        f"{len(df)} flows, {df[LABEL_COL].nunique()} classes, "
        f"{df[SESSION_COL].nunique()} sessions — session-based 75/25 split"
    )
    log.info("Loaded %s", dataset_desc)

    report_dir = Path(args.report_dir)
    trained: dict[str, object] = {}
    for mt in args.models:
        tm = train_and_evaluate(df, model_type=mt, seed=args.seed)
        trained[mt] = tm
        png = report_dir / f"confusion_{mt}.png"
        plot_confusion_matrix(tm.result, png, title=f"Confusion matrix — {mt} (recall-normalized)")

    # Headline = RF if present, else the first trained model.
    headline_type = "rf" if "rf" in trained else args.models[0]
    headline = trained[headline_type]

    # Feature-group ablation on the headline model: flow-only vs +TLS vs +JA3.
    ablation = ablation_accuracy(
        df,
        {
            "flow size/timing only": ("flow_stats",),
            "+ raw sequence": ("flow_stats", "raw_seq"),
            "+ TLS structure (headline)": DEFAULT_GROUPS,
            "+ JA3 identity (leaky)": (*DEFAULT_GROUPS, "tls_ja3"),
        },
        model_type="rf",
        seed=args.seed,
    )

    report = render_report_md(
        headline.result,
        model_name=f"{headline_type} baseline",
        dataset_desc=dataset_desc,
        feature_groups=DEFAULT_GROUPS,
        n_features=len(feature_columns(DEFAULT_GROUPS)),
        confusion_png=f"confusion_{headline_type}.png",
        ablation=ablation,
    )
    report_path = report_dir / "eval_baseline.md"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    log.info("Wrote report -> %s", report_path)

    # Save the headline model for the live scorer.
    saved = headline.model.save(args.model_out)
    log.info("Saved headline model (%s) -> %s", headline_type, saved)

    # Console summary.
    r = headline.result
    log.info("HEADLINE %s: acc=%.1f%% macroF1=%.3f latency(med)=%.3fms",
             headline_type, r.accuracy * 100, r.macro_f1,
             r.latency.median_ms if r.latency else float("nan"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
