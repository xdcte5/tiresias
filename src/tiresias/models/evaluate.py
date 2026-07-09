"""Evaluation: per-class metrics, confusion matrix (numbers + plot), latency, report.

Overall accuracy hides poor performance on minority classes, so we always report
per-class precision/recall/F1 and a confusion matrix, plus a real per-flow inference
latency measurement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)


@dataclass
class ClassMetric:
    label: str
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class LatencyStats:
    mean_ms: float
    median_ms: float
    p95_ms: float
    n: int


@dataclass
class EvalResult:
    accuracy: float
    macro_f1: float
    weighted_f1: float
    per_class: list[ClassMetric]
    labels: list[str]
    confusion: np.ndarray  # rows = true, cols = pred
    latency: LatencyStats | None = None
    extra: dict = field(default_factory=dict)


def evaluate_predictions(y_true, y_pred, labels: list[str]) -> EvalResult:
    p, r, f1, sup = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    per_class = [
        ClassMetric(labels[i], float(p[i]), float(r[i]), float(f1[i]), int(sup[i]))
        for i in range(len(labels))
    ]
    return EvalResult(
        accuracy=float(accuracy_score(y_true, y_pred)),
        macro_f1=float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        weighted_f1=float(
            f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
        ),
        per_class=per_class,
        labels=labels,
        confusion=confusion_matrix(y_true, y_pred, labels=labels),
    )


def measure_latency(model, feature_dicts: list[dict], repeats: int = 3) -> LatencyStats:
    """Per-flow inference latency: time single-row predictions (real-time path)."""
    times_ms: list[float] = []
    for _ in range(repeats):
        for fd in feature_dicts:
            t0 = time.perf_counter()
            model.predict_features(fd)
            times_ms.append((time.perf_counter() - t0) * 1000.0)
    arr = np.array(times_ms)
    return LatencyStats(
        mean_ms=float(arr.mean()),
        median_ms=float(np.median(arr)),
        p95_ms=float(np.percentile(arr, 95)),
        n=len(arr),
    )


def plot_confusion_matrix(result: EvalResult, path: str | Path, title: str) -> Path:
    """Row-normalized (recall) sequential heatmap, annotated with raw counts."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = result.labels
    cm = result.confusion.astype(float)
    row_sums = cm.sum(axis=1, keepdims=True)
    norm = np.divide(cm, row_sums, out=np.zeros_like(cm), where=row_sums > 0)

    fig, ax = plt.subplots(figsize=(1.15 * len(labels) + 2, 1.15 * len(labels) + 1.5))
    # Sequential, single hue light->dark (magnitude = fraction of true class).
    im = ax.imshow(norm, cmap="Blues", vmin=0.0, vmax=1.0, aspect="equal")

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Predicted class", fontsize=10)
    ax.set_ylabel("True class", fontsize=10)
    ax.set_title(title, fontsize=12, pad=12)

    # Recessive frame.
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)

    # Direct labels: raw count, ink color chosen for contrast on the cell.
    for i in range(len(labels)):
        for j in range(len(labels)):
            count = int(result.confusion[i, j])
            if count == 0:
                continue
            ax.text(
                j, i, str(count),
                ha="center", va="center", fontsize=9,
                color="white" if norm[i, j] > 0.55 else "#1f2937",
            )

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Recall (fraction of true class)", fontsize=9)
    cbar.outline.set_visible(False)

    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def render_report_md(
    result: EvalResult,
    model_name: str,
    dataset_desc: str,
    feature_groups: tuple[str, ...],
    n_features: int,
    confusion_png: str | None = None,
    ablation: dict[str, float] | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Evaluation — {model_name}\n")
    lines.append(f"_{dataset_desc}_\n")
    lines.append("## Headline (session-based test split)\n")
    lat = result.latency
    lines.append(f"- **Accuracy**: {result.accuracy * 100:.1f}%")
    lines.append(f"- **Macro F1**: {result.macro_f1:.3f}")
    lines.append(f"- **Weighted F1**: {result.weighted_f1:.3f}")
    if lat:
        lines.append(
            f"- **Inference latency / flow**: {lat.median_ms:.3f} ms median, "
            f"{lat.p95_ms:.3f} ms p95 (n={lat.n})"
        )
    lines.append(
        f"- **Features**: {n_features} columns from groups "
        f"`{', '.join(feature_groups)}` — SNI and JA3 identity excluded (no leakage).\n"
    )

    lines.append("## Per-class precision / recall / F1\n")
    lines.append("| Class | Precision | Recall | F1 | Support |")
    lines.append("|-------|-----------|--------|----|---------|")
    for m in result.per_class:
        lines.append(
            f"| {m.label} | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} | {m.support} |"
        )
    lines.append("")

    if ablation:
        lines.append("## Feature-group ablation\n")
        lines.append("| Feature set | Accuracy |")
        lines.append("|-------------|----------|")
        for name, acc in ablation.items():
            lines.append(f"| {name} | {acc * 100:.1f}% |")
        lines.append(
            "\n> **SNI** is always excluded from features: it is the *label source*, so "
            "using it as a feature too would be circular leakage.\n>\n"
            "> **JA3** is excluded by default as a precaution. JA3 fingerprints the "
            "client TLS stack (browser/library), not the application — a browser tab "
            "streaming video and one browsing share a JA3 — so here it adds little over "
            "the honest feature set. But in a dataset where each class is collected "
            "through a *distinct native app*, one class would map to one JA3 and it would "
            "strongly leak the label. Keeping it opt-in lets us measure that effect "
            "rather than silently benefit from it.\n>\n"
            "> The headline uses flow size/timing + TLS structure + raw sequence only.\n"
        )

    if confusion_png:
        lines.append("## Confusion matrix\n")
        lines.append(f"![confusion matrix]({confusion_png})\n")

    return "\n".join(lines)
