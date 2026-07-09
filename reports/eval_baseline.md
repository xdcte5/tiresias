# Evaluation — rf baseline

_1773 flows, 8 classes, 320 sessions — session-based 75/25 split_

## Headline (session-based test split)

- **Accuracy**: 95.8%
- **Macro F1**: 0.953
- **Weighted F1**: 0.959
- **Inference latency / flow**: 27.829 ms median, 30.478 ms p95 (n=600)
- **Features**: 99 columns from groups `flow_stats, tls_shape, raw_seq` — SNI and JA3 identity excluded (no leakage).

## Per-class precision / recall / F1

| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| dns_background | 1.000 | 1.000 | 1.000 | 50 |
| file_transfer | 1.000 | 1.000 | 1.000 | 67 |
| gaming | 1.000 | 1.000 | 1.000 | 57 |
| music_streaming | 0.708 | 0.895 | 0.791 | 38 |
| video_conferencing | 1.000 | 1.000 | 1.000 | 59 |
| video_streaming | 1.000 | 0.969 | 0.984 | 65 |
| vpn | 1.000 | 1.000 | 1.000 | 38 |
| web_browsing | 0.920 | 0.793 | 0.852 | 58 |

## Feature-group ablation

| Feature set | Accuracy |
|-------------|----------|
| flow size/timing only | 92.8% |
| + raw sequence | 91.9% |
| + TLS structure (headline) | 95.8% |
| + JA3 identity (leaky) | 96.1% |

> **SNI** is always excluded from features: it is the *label source*, so using it as a feature too would be circular leakage.
>
> **JA3** is excluded by default as a precaution. JA3 fingerprints the client TLS stack (browser/library), not the application — a browser tab streaming video and one browsing share a JA3 — so here it adds little over the honest feature set. But in a dataset where each class is collected through a *distinct native app*, one class would map to one JA3 and it would strongly leak the label. Keeping it opt-in lets us measure that effect rather than silently benefit from it.
>
> The headline uses flow size/timing + TLS structure + raw sequence only.

## Confusion matrix

![confusion matrix](confusion_rf.png)
