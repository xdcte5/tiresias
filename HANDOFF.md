# Handoff — Tiresias

Picking this back up later? Start here. Sprints 0–5 (the core project) are **built,
tested, and pushed to `main`**. What remains is (1) producing headline numbers from
**your own captured traffic**, (2) **visual/live QA of the dashboard** in a browser,
and (3) the optional **extension tracks**. Details below.

Full plan: [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md). This file is the "what to do next".

---

## Current state (as of 2026-07-09)

| Sprint | Status | Commit |
|--------|--------|--------|
| 0 — scaffolding, scope, tooling | ✅ done | `875f4b4` |
| 1 — capture agent + flow assembler | ✅ done | `de5fb20` |
| 2 — features (TLS/JA3) + labeling + dataset | ✅ done | `2a274cf` |
| 3 — RF/LightGBM baseline + eval report + registry | ✅ done | `1d85fbd` |
| 4 — streaming scorer + FastAPI WS/REST backend | ✅ done | `ebbadfa` |
| 5 — React/Vite dashboard | ✅ done | `92d471b` |
| 6 — 1D-CNN sequence-model comparison | ⏳ not started | — |
| 7 — methodology writeup + plots | ⏳ not started | — |
| 8 — Raspberry Pi inline tap | ⏳ not started (hardware) | — |

**Verified working:** 51 Python tests green, ruff clean; real `tiresias-serve`
streams live scored flows over WebSocket; dashboard builds under strict TypeScript
and serves; backend↔dashboard wiring confirmed (CORS, assets 200).

**Important caveat:** the committed model + plots are trained on the **synthetic**
demo dataset, not real traffic. Numbers below (RF ~95.8%, LightGBM ~96.1%) are
synthetic and clearly labeled as such in the README. **Replace them with real
captures before putting anything on a resume.**

---

## Next step 1 — Real dataset → real numbers (highest priority) 🧑‍💻

This is the load-bearing part. Everything to do it is already built.

**Scope reminder:** only capture your own traffic on your own network.

```bash
# One session per app, a few minutes each, ideally several sessions per app
# across different times. The class hint only names the file; the real label
# comes from each flow's TLS SNI.
sudo ./scripts/collect_session.sh wlan0 video_streaming 300     # then use YouTube/Netflix
sudo ./scripts/collect_session.sh wlan0 video_conferencing 300  # then a Zoom/Meet call
sudo ./scripts/collect_session.sh wlan0 web_browsing 300        # then browse
sudo ./scripts/collect_session.sh wlan0 file_transfer 300       # then download something big
sudo ./scripts/collect_session.sh wlan0 music_streaming 300     # then Spotify
sudo ./scripts/collect_session.sh wlan0 gaming 300              # then play something
# vpn / dns_background as available
```

Then build the dataset and retrain:

```bash
tiresias-build-dataset --flows-dir data/flows --out data/datasets/captured.parquet
tiresias-train --dataset data/datasets/captured.parquet
```

This regenerates `artifacts/baseline_rf.joblib`, `reports/eval_baseline.md`, and the
confusion PNGs from **real** data. Commit those.

**Watch for / expect to iterate on:**
- **Label coverage.** Labels come from SNI suffix rules in
  `src/tiresias/features/labeling.py` (`SNI_LABEL_RULES`). Real traffic will hit
  domains not in the map → those flows are dropped as `unknown`. Run
  `tiresias-build-dataset --keep-unknown` once to see what's getting dropped, then add
  the domains you care about to the map (matching is longest-suffix-wins).
- **UDP / QUIC / no-TLS flows** (gaming, some video, DNS) have no SNI, so SNI-labeling
  can't tag them. For those classes you'll either rely on session context (you know
  what you ran) or extend labeling to use destination IP/port heuristics. Simplest
  path: label those sessions by filename/hint instead of SNI — a small change to
  `build_dataset.py` to fall back to the filename's class hint when SNI is unknown.
- **Class balance.** Collect roughly comparable amounts per class; check the per-class
  counts `tiresias-build-dataset` prints.
- **Real accuracy will be lower than the synthetic 96%** — that's good and honest.
  Whatever you get (with per-class F1 + confusion matrix) is the real story.

---

## Next step 2 — Dashboard visual / live QA (needs a browser) 🧑‍💻

The dashboard **builds and serves**, but it hasn't been eyeballed running live — that
needs an actual browser (couldn't be automated here).

```bash
# terminal 1 — backend (synthetic is fine for a first look; or --source live --iface wlan0)
tiresias-serve --source synthetic --flows-per-sec 6

# terminal 2 — dashboard
cd dashboard && npm install && npm run dev
# open http://localhost:5173
```

**Check:**
- Flow table updates live (new rows appear over WebSocket), "Live" dot is green.
- Bandwidth-by-class stacked-area chart renders and refreshes (~every 2s), hover
  crosshair + tooltip work, legend colors match table chips, light **and** dark mode
  both look right (toggle your OS theme).
- Low-confidence flows show the "⚠ Unclassified" flag.

**Then capture a screenshot or short screen recording** and add it to the README
Results section (there's already a confusion-matrix image there; add the dashboard).
This is the single most compelling visual for the project.

If anything looks off (chart geometry, tooltip position, color contrast), those are
small fixes in `dashboard/src/components/BandwidthChart.tsx` and `src/theme.css`.

---

## Next step 3 — Extension tracks (optional, do in this order)

Each meaningfully strengthens the project; none is required. Do them **after** steps
1–2 so they build on real numbers.

### Sprint 6 — 1D-CNN sequence-model comparison (highest value / effort ratio)
- `pip install -e ".[deep]"` (adds torch).
- Build a 1D-CNN over the raw `seq_size_*` / `seq_iat_*` columns (already produced by
  the feature extractor — input shape `(K, 2)`, signed size + inter-arrival).
- **Evaluate on the exact same session split** as the RF baseline (reuse
  `models/split.py`) so the comparison is fair.
- Report accuracy, per-class F1, confusion matrix, **and per-flow latency** for both,
  plus whether the two models miss the *same* flows. Deliverable: a comparison table
  in the README. See `EXECUTION_PLAN.md` Sprint 6.

### Sprint 7 — Methodology writeup + plots
- Polished README/writeup: problem framing, methodology (SNI labeling, leakage
  avoidance, session split), results (comparison table + confusion image + honest
  failure-mode discussion), architecture diagram, and explicit limitations
  (dataset size, prototype-not-IDS). Do this once Sprint 6 numbers exist.

### Sprint 8 — Raspberry Pi inline tap (hardware-gated, fine to skip)
- Run capture + assembler on a Pi (Wi-Fi AP mode or Ethernet bridge), score on-Pi or
  forward features to a laptop; measure CPU/mem/latency under real load. Needs spare
  hardware.

---

## Quick reference

```bash
# env
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest && ruff check .        # 51 tests, should be green

# synthetic end-to-end (no capture)
tiresias-synth --sessions 40 --out data/datasets/synth.parquet
tiresias-train --dataset data/datasets/synth.parquet
tiresias-serve --source synthetic
```

- Capture privileges: `sudo`, or
  `sudo setcap cap_net_raw,cap_net_admin+eip "$(readlink -f .venv/bin/python)"`.
- Raw captures / flow dumps / datasets live under `data/` and are **gitignored** —
  never committed. Regenerate via the commands above.
- Shared feature order lives in `models/registry.py` — offline training and live
  scoring both go through it, so they can't drift. If you add features, both paths
  update together automatically.

## Open questions still worth confirming (from the original plan)
1. Final class list — currently the 8 in `src/tiresias/__init__.py` (`CLASS_NAMES`) and
   `synth/generate.py` PROFILES. Adjust if your real captures suggest different
   well-separated classes.
2. Headline model — plan trains both RF and LightGBM; RF is saved as the headline for
   interpretability. LightGBM was slightly more accurate and ~3× faster per flow on
   synthetic data — reconsider once you have real numbers.
