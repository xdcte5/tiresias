# Tiresias — Execution Plan

Encrypted-traffic application classifier. This plan turns
[`traffic_classifier_spec.md`](../traffic_classifier_spec.md) and
[`traffic_classifier_extensions.md`](../traffic_classifier_extensions.md) into an
ordered set of **sprints**. Each sprint is a self-contained, shippable unit that ends
with a **push to `main`**.

## How this plan runs

- **Repo**: `tiresias/` (remote: `github.com/xdcte5/tiresias`, branch `main`).
- **Cadence**: build sprint → verify exit criteria → commit → `git push origin main`.
  We push straight to `main` per your instruction (no PR flow). `gh` CLI is not
  installed; plain `git push` over HTTPS is used.
- **Language split**: Python for capture / features / ML / backend; React (Vite) for
  the dashboard.
- **Capture stack**: `scapy` (uses libpcap directly — **no `tshark` needed**, which
  matters because `tshark` is not installed here). `pyshark` is deliberately avoided
  for that reason.
- **Privacy/scope**: raw pcaps and captured flow dumps are **never committed**
  (`.gitignore`). Only code, small model artifacts, and evaluation reports/plots land
  in git. README carries the legal/scope disclaimer.

## Environment notes (from this machine)

| Tool | Status |
|------|--------|
| Python | 3.14.5 ✅ |
| Node | 26.2.0 ✅ |
| npm | 11.16.0 ✅ |
| tshark | ❌ not installed → use `scapy`, not `pyshark` |
| gh CLI | ❌ not installed → use raw `git push` |

`scapy` live capture needs packet-capture privileges (run capture scripts with
`sudo`, or grant `CAP_NET_RAW`/`CAP_NET_ADMIN` to the Python binary). This is called
out again in Sprint 1.

## ⚠️ Load-bearing dependency: you must generate data

Sprints 3+ cannot be finished by code alone — they need **real labeled captures**.
Sprint 2 ships a guided capture workflow, but **you** run the target apps (YouTube,
Zoom, browsing, a game, Spotify, a download, idle/DNS) for 5–10 min per session,
several sessions each. These are your action items, flagged 🧑‍💻 below. Everything up
to that point (Sprints 0–2) is fully buildable without you.

---

## Sprint roadmap at a glance

| # | Sprint | Depends on | Your data action? |
|---|--------|-----------|-------------------|
| 0 | Scaffolding, scope, tooling | — | no |
| 1 | Capture agent + flow assembler | 0 | no (smoke-test on own traffic) |
| 2 | Feature extraction + dataset builder | 1 | 🧑‍💻 collect sessions |
| 3 | Baseline model + evaluation report | 2 | 🧑‍💻 needs the dataset |
| 4 | Streaming scorer + FastAPI/WebSocket backend | 3 | no |
| 5 | React dashboard | 4 | no |
| 6 | **Ext. Track 1** — 1D-CNN sequence model comparison | 3 | no |
| 7 | **Ext. Track 3** — methodology writeup + plots | 3, 5, 6 | no |
| 8 | **Ext. Track 2** — Raspberry Pi inline tap (optional) | 3 | 🧑‍💻 hardware |

Sprints 0–5 are the core project ("solid"). 6–8 are the extensions ("standout").
6 and 7 need only a laptop; 8 is hardware-gated and skippable.

---

## Sprint 0 — Scaffolding, scope, tooling

**Goal**: an installable, importable Python package + committed scope/legal framing,
so every later sprint drops into a stable skeleton.

**Tasks**
- Package layout: `tiresias/` (src package) with submodules `capture/`, `flows/`,
  `features/`, `models/`, `pipeline/`, `api/`, plus `scripts/`, `tests/`, `data/`
  (gitignored), `artifacts/` (small models/plots, committed), `reports/`.
- `pyproject.toml` with pinned deps: `scapy`, `numpy`, `pandas`, `pyarrow`,
  `scikit-learn`, `lightgbm`, `fastapi`, `uvicorn`, `websockets`, `pydantic`,
  `pytest`, `ruff`. (Torch added later in Sprint 6, not now.)
- `.gitignore`: `data/`, `*.pcap`, `*.parquet` under data/, captured flow JSON,
  `.venv/`, `node_modules/`, `__pycache__/`.
- Central `config.py` (interface name, flow timeout=15s, packet cap=100, class map)
  and a `logging` setup.
- Rewrite `README.md`: legal/ethical scope disclaimer (capture only your own
  networks/devices), the architecture diagram from the spec, and a "how to run"
  stub filled in as sprints land.
- `ruff` + `pytest` config; one trivial passing test to prove the harness runs.

**Exit criteria**: `pip install -e .` succeeds, `pytest` green, `ruff` clean, README
renders with scope disclaimer + diagram.
**Ship**: commit `chore: project scaffolding, scope disclaimer, tooling` → push `main`.

---

## Sprint 1 — Capture agent + flow assembler

**Goal**: turn live packets into buffered per-flow records dumped to disk. No ML.
This is spec build-step 1 — validate we see sane flows for known apps.

**Tasks**
- `capture/agent.py`: `scapy` sniffer on a configurable interface; also accepts a
  `.pcap` file as input so the whole pipeline is testable offline without root.
- `flows/assembler.py`: group packets by direction-normalized 5-tuple (sort the
  IP:port endpoint pair so both directions map to one flow). Per-flow state holds
  timestamps, sizes, direction, and the first TLS ClientHello bytes.
- Flow lifecycle: flush a flow when **either** it's idle > `flow_timeout` (15s) **or**
  it hits the packet cap (100). A background reaper ages out idle flows.
- `scripts/capture_to_disk.py`: run capture, write flushed flows to
  `data/flows/*.parquet` (schema: 5-tuple, per-packet size+ts+direction arrays,
  raw clienthello bytes, start/end ts).
- Tests on a small checked-in **sanitized** `.pcap` fixture (or a synthetic one built
  with scapy in-test) covering: bidirectional grouping, timeout flush, cap flush.

**🧑‍💻 / smoke test**: run `sudo python scripts/capture_to_disk.py` for ~60s of your
own browsing, eyeball that flow counts and endpoints look sane. (Optional at this
stage — the offline pcap path is enough to pass CI.)

**Privilege note**: document `sudo` / `setcap cap_net_raw,cap_net_admin+eip` in README.

**Exit criteria**: given a pcap, produces well-formed per-flow parquet; unit tests
green for grouping + both flush paths.
**Ship**: `feat: capture agent + flow assembler with disk dump` → push `main`.

---

## Sprint 2 — Feature extraction + dataset builder

**Goal**: per-flow feature vectors + a labeled dataset built from your capture
sessions. Spec build-step 2 and the labeling strategy.

**Tasks**
- `features/extract.py` — per flow, both directions (fwd/bwd):
  - Size stats: mean/std/min/max + raw first-K size sequence.
  - Inter-arrival timing: mean/std of deltas per direction.
  - Byte/packet ratios (up vs down), flow duration so far.
  - Burstiness: packet-size variance over sliding sub-windows.
  - TLS ClientHello parse: **SNI**, **JA3** fingerprint (md5 of the ordered TLS
    fields), cipher-suite count, extension set. Robust to non-TLS / QUIC / no
    handshake (features null → imputed).
- `features/labeling.py`: SNI → class map (`*.youtube.com`→video_streaming,
  `*.zoom.us`→video_conf, etc.), covering the 6–10 classes from the spec.
- **Leakage guard**: SNI-derived label and any SNI-identifying feature live in
  separate columns; training feature set **excludes** SNI by default. A flag can
  include it, but eval always also reports the honest SNI-excluded number.
- `scripts/build_dataset.py`: read `data/flows/*.parquet` → feature matrix +
  labels + a **`session_id`** column (so Sprint 3 can split by session, not flow).
- `scripts/collect_session.sh` / docs: guided workflow — "run app X for N minutes,
  captures land tagged with session id".
- Tests: feature correctness on synthetic flows; JA3 against a known reference
  vector; labeler mapping; leakage-column separation.

**🧑‍💻 YOUR ACTION**: run the target apps across multiple sessions to produce the raw
captures this sprint's script consumes. Without this, Sprint 3 has no data.

**Exit criteria**: `build_dataset.py` turns captured flows into a labeled feature
table with `session_id`; SNI leakage is structurally prevented; tests green.
**Ship**: `feat: feature extraction (incl. JA3/TLS) + labeled dataset builder` →
push `main`.

---

## Sprint 3 — Baseline model + evaluation report ⭐ load-bearing

**Goal**: the artifact that makes the project real — a trained model with honest
per-class numbers. Spec build-step 3.

**Tasks**
- `models/train_baseline.py`: RandomForest **and** LightGBM on the Sprint-2 features.
- **Session-based** train/test split (`GroupKFold`/group split on `session_id`) — no
  flow-level leakage across the split.
- Metrics: overall accuracy, **per-class precision/recall/F1**, confusion matrix,
  and **per-flow inference latency** (ms). Report SNI-excluded numbers as the headline.
- Outputs: saved model → `artifacts/baseline_rf.joblib` (committed if small),
  `reports/eval_baseline.md` + confusion-matrix PNG + per-class table.
- `models/registry.py`: single load/predict interface both training and the live
  scorer (Sprint 4) share — avoids drift between offline and online feature order.
- Tests: split really separates sessions; predict interface shape/latency sanity.

**Exit criteria**: reproducible `train_baseline.py` produces saved model + committed
eval report with confusion matrix and latency; README results section populated with
real numbers.
**Ship**: `feat: baseline RF/LightGBM + evaluation report` → push `main`.

> **Review gate**: this is the natural point to sanity-check the numbers before
> investing in streaming/dashboard/extensions.

---

## Sprint 4 — Streaming scorer + FastAPI/WebSocket backend

**Goal**: score live flows and serve them. Spec build-steps 4–5.

**Tasks**
- `pipeline/scorer.py`: consume flows flushed by the assembler off an in-process
  queue (`asyncio.Queue`; Redis noted as a later swap), extract features via the
  Sprint-2 code, predict via `models/registry`.
- **Anomaly flag**: max class confidence < threshold → `unclassified/anomalous`.
- `api/server.py` (FastAPI): WebSocket `/ws/flows` streaming scored flows live +
  REST `/stats/summary` (bandwidth-by-class, counts) for historical summary.
- Wire capture(Sprint 1) → assembler → scorer → WebSocket so live capture drives the
  feed; keep the offline-pcap replay path for demoing without live capture.
- Tests: scorer over a queue of synthetic flows; WebSocket emits scored payloads;
  REST summary aggregates correctly (via FastAPI `TestClient`).

**Exit criteria**: with a replayed pcap, the server streams scored flows over
WebSocket and serves summary stats; anomaly flagging works.
**Ship**: `feat: streaming scorer + FastAPI WebSocket/REST backend` → push `main`.

---

## Sprint 5 — React dashboard

**Goal**: the visually compelling presentation layer. Spec build-step 6.

**Tasks**
- `dashboard/` Vite + React app (own `node_modules`, gitignored).
- Live flow table: src/dst, inferred class, confidence, size; anomalous rows flagged.
- **Rolling bandwidth-by-class chart** (stacked area, updates every few seconds) —
  prioritized as the headline visual per the spec.
- WebSocket client to `/ws/flows`; REST call to `/stats/summary` on load.
- README: run instructions for backend + dashboard; capture a screenshot/GIF for the
  results section.

**Exit criteria**: `npm run dev` shows a live-updating table + bandwidth chart driven
by the backend feed (live or replayed); screenshot committed to README.
**Ship**: `feat: live React dashboard (flow table + bandwidth-by-class chart)` →
push `main`.

*(End of core project — "solid". Extensions follow.)*

---

## Sprint 6 — Extension Track 1: sequence model comparison

**Goal**: "I ran a real comparison experiment," not "I trained a classifier."

**Tasks**
- Add `torch` to deps. `models/train_cnn.py`: 1D-CNN over the raw packet sequence,
  input `(K, 2)` = `[signed packet size, inter-arrival time]` (sign encodes
  direction), padded/truncated to K.
- Train/evaluate on the **exact same session split** as Sprint 3 (fair comparison).
- Report accuracy, per-class F1, confusion matrix, **and latency/flow** vs the
  baseline; analyze whether the two models miss the *same* flows or different ones.
- Optional LSTM/GRU as a third point if time allows.
- Deliverable: comparison table + 2–3 sentence tradeoff writeup in README.

**Exit criteria**: committed comparison table (RF vs CNN [vs LSTM]) with matched
split + latency; short honest tradeoff writeup.
**Ship**: `feat: 1D-CNN sequence model + classical-vs-learned comparison` → push
`main`.

---

## Sprint 7 — Extension Track 3: methodology writeup + plots

**Goal**: make results independently verifiable, not a take-on-faith resume line.

**Tasks**
- Polished `README.md` (or `docs/writeup.md`): problem framing (why encrypted
  classification is hard), methodology (SNI labeling, leakage avoidance, session
  split), results (comparison table + rendered confusion matrix image + honest
  failure-mode discussion), systems architecture diagram, and **explicit
  limitations** (dataset size/diversity, prototype-not-IDS).
- Embed images: confusion matrix, bandwidth-by-class dashboard chart, comparison
  table.

**Exit criteria**: one polished writeup with embedded plots and a limitations
section, linkable from a resume/portfolio.
**Ship**: `docs: methodology writeup with evaluation plots and limitations` → push
`main`.

---

## Sprint 8 — Extension Track 2: Raspberry Pi inline tap (optional, hardware-gated)

**Goal**: hardware + software + ML systems project. **Skip if no Pi available** —
Sprints 6–7 already deliver the standout upgrade.

**Tasks**
- Choose topology: Wi-Fi AP mode (`hostapd` + `dnsmasq` + `iptables` NAT) *or*
  Ethernet bridge mode (two NICs bridged) — bridge mode is the more "inline" version.
- Run capture agent + assembler **on the Pi**; either score on-Pi (RF baseline is
  cheap) or forward **features only** (not raw packets) to the laptop for scoring.
- Measure/report: Pi CPU/mem under load, real-time keep-up vs home traffic volume,
  accuracy/latency delta vs laptop.
- Deliverable: topology section + resource measurements (+ optional setup photo).

**🧑‍💻 YOUR ACTION**: provide the Pi + network hardware; run the live deployment.
**Exit criteria**: documented topology + resource/latency measurements from a real
Pi run.
**Ship**: `feat: Raspberry Pi inline-tap deployment + resource report` → push `main`.

---

## Cross-cutting conventions

- **Commit style**: Conventional Commits; each sprint = one focused push to `main`.
- **Never commit**: raw pcaps, captured flow dumps, `data/`, `node_modules/`, venvs.
- **Do commit**: code, small model artifacts, eval reports, plots, README/writeup.
- **Testing**: every code sprint ships `pytest` coverage of its new logic and stays
  `ruff`-clean before the push.
- **Shared feature order**: training and live scoring both go through
  `models/registry` so offline/online features never drift.

## Open questions for your greenlight

1. **Final class list** — confirm the 6–10 classes (spec suggests video_streaming,
   video_conf, web, file_transfer, gaming, music, vpn, dns/background). Lock this
   before Sprint 2's labeler.
2. **LightGBM vs RF as the headline baseline** — plan trains both; which is the
   "headline" model? (Default: report both, headline RF for interpretability.)
3. **Extension scope** — do you want all of Sprints 6–8, or stop at 7 (skip Pi)?
4. **Push-to-main directly** — confirmed you want direct pushes (no PRs) per your
   instruction; say if you'd rather I open PRs instead.
