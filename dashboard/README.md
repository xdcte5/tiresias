# Tiresias dashboard

Single-page React (Vite + TypeScript) dashboard for the live classifier.

- **Live flow table** — most-recent classified flows: source/destination, inferred
  class (color-coded), model confidence, size, protocol, and SNI. Flows the model
  isn't confident about are flagged **Unclassified** (an icon + label, not color
  alone) — a lightweight nod to anomaly detection, not a real IDS.
- **Bandwidth-by-class chart** — a rolling stacked-area chart (hand-built SVG, no
  chart library) of throughput per traffic class, with a hover crosshair + tooltip,
  a legend, and light/dark theming. Colors use a CVD-validated categorical palette,
  one fixed slot per class.
- **Stat tiles** — flows classified, flows flagged unclassified, active classes,
  current throughput.

## Run

```bash
npm install
npm run dev        # http://localhost:5173, expects the backend on :8000
```

Point at a non-default backend with `VITE_API_BASE`:

```bash
VITE_API_BASE=http://192.168.1.50:8000 npm run dev
```

## Build / typecheck

```bash
npm run build      # tsc --noEmit + vite build -> dist/
npm run typecheck
```

Data flow: the table streams from `WS /ws/flows` (snapshot on connect, then live
scored flows); the chart and tiles poll `GET /stats/summary` every 2s.
