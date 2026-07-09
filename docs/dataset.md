# Building the Tiresias dataset

Raw captures are **never committed** (privacy + size). This doc is how you (or anyone
verifying the project) regenerate the labeled dataset locally.

## Two dataset sources

### 1. Synthetic (works with zero captures)

```bash
tiresias-synth --sessions 40 --out data/datasets/synth.parquet
```

Generates flows whose size/timing/direction *shape* is characteristic of each class,
with class-appropriate TLS handshakes. Same schema as a real dataset — enough to
train, wire up streaming, and demo the dashboard end-to-end. Labels are known
directly (no SNI needed). Use this to develop; use real captures for the headline
numbers.

### 2. Real captures (the honest numbers)

**Scope reminder:** capture only your own traffic on your own network.

1. Collect several sessions per app, across different times, one app at a time:
   ```bash
   sudo ./scripts/collect_session.sh wlan0 video_streaming 300   # then use YouTube
   sudo ./scripts/collect_session.sh wlan0 video_conferencing 300 # then a Zoom call
   sudo ./scripts/collect_session.sh wlan0 web_browsing 300       # then browse
   # ... gaming, file_transfer, music_streaming, vpn, dns_background
   ```
   Each run writes `data/flows/<class>__<timestamp>.parquet` — one file per session.

2. Build the SNI-labeled dataset:
   ```bash
   tiresias-build-dataset --flows-dir data/flows --out data/datasets/captured.parquet
   ```
   Labels come from each flow's TLS **SNI** (visible in the ClientHello even though
   the payload is encrypted). Flows with no mappable SNI are dropped.

## The leakage rules baked into the pipeline

- **SNI is the label source, never a feature.** SNI (and the raw JA3 hash) are stored
  as *metadata* columns; the default training feature set (`DEFAULT_GROUPS`) excludes
  them. Using SNI as both label and feature would be textbook leakage.
- **JA3 is excluded by default too.** In a self-generated dataset, one app ⇒ one JA3,
  so JA3 would act as an app-id shortcut. It lives in an opt-in `tls_ja3` group so you
  can *measure* its (inflated) contribution separately rather than silently benefit.
- **Split by session, not by flow.** Flows from one session are correlated; the
  session id (one capture file = one session) is what the Sprint-3 split groups on.

## Extending the label map

Add SNI suffix → class rules in `src/tiresias/features/labeling.py`
(`SNI_LABEL_RULES`). Matching is longest-suffix-wins.
