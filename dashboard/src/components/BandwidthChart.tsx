import { useMemo, useRef, useState } from "react";

import { colorVar, orderClasses, prettyLabel, UNCLASSIFIED } from "../colors";
import { formatClock, formatRate } from "../format";
import type { Summary } from "../types";
import Legend from "./Legend";

const W = 800;
const H = 280;
const M = { top: 12, right: 14, bottom: 26, left: 60 };
const INNER_W = W - M.left - M.right;
const INNER_H = H - M.top - M.bottom;

interface Bucket {
  t: number;
  vals: Record<string, number>;
}

interface Hover {
  i: number;
  x: number;
  y: number;
}

export default function BandwidthChart({ summary }: { summary: Summary | null }) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);

  const model = useMemo(() => {
    if (!summary) return null;
    // Bandwidth (bytes/sec) per class per bucket.
    const buckets: Bucket[] = summary.bandwidth_series.map((b) => {
      const vals: Record<string, number> = {};
      for (const [k, v] of Object.entries(b.bytes_by_class)) vals[k] = v / summary.bucket_s;
      return { t: b.t, vals };
    });
    // Labels present across buckets, in fixed categorical order (unclassified last).
    const present = new Set<string>();
    for (const b of buckets) for (const k of Object.keys(b.vals)) present.add(k);
    const labels = orderClasses([...present]);
    if (present.has(UNCLASSIFIED)) labels.push(UNCLASSIFIED);

    const totals = buckets.map((b) => labels.reduce((s, l) => s + (b.vals[l] ?? 0), 0));
    const yMax = Math.max(1, ...totals) * 1.1;
    return { buckets, labels, yMax };
  }, [summary]);

  if (!model || model.buckets.length < 2) {
    return (
      <>
        <div className="chart-empty">Collecting bandwidth data…</div>
        {model && <Legend labels={model.labels} />}
      </>
    );
  }

  const { buckets, labels, yMax } = model;
  const n = buckets.length;
  const x = (i: number) => M.left + (n === 1 ? INNER_W / 2 : (i / (n - 1)) * INNER_W);
  const y = (v: number) => M.top + INNER_H * (1 - v / yMax);

  // Stacked band paths (fixed order = fixed z-order, bottom to top).
  const bands = labels.map((label, k) => {
    const upper: string[] = [];
    const lower: string[] = [];
    buckets.forEach((b, i) => {
      let below = 0;
      for (let j = 0; j < k; j += 1) below += b.vals[labels[j]] ?? 0;
      const here = below + (b.vals[label] ?? 0);
      upper.push(`${x(i)},${y(here)}`);
      lower.push(`${x(i)},${y(below)}`);
    });
    const d = `M${upper.join("L")}L${lower.reverse().join("L")}Z`;
    const topLine = `M${upper.join("L")}`;
    return { label, d, topLine };
  });

  // Y gridlines / ticks.
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);
  // A few x ticks.
  const xTickIdx = n <= 4 ? buckets.map((_, i) => i) : [0, Math.floor((n - 1) / 2), n - 1];

  const handleMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const scale = W / rect.width;
    const vx = (e.clientX - rect.left) * scale;
    // Nearest bucket index.
    const i = Math.max(0, Math.min(n - 1, Math.round(((vx - M.left) / INNER_W) * (n - 1))));
    setHover({ i, x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const hoverBucket = hover ? buckets[hover.i] : null;
  const hoverRows = hoverBucket
    ? labels
        .map((l) => ({ label: l, v: hoverBucket.vals[l] ?? 0 }))
        .filter((r) => r.v > 0)
        .sort((a, b) => b.v - a.v)
    : [];

  return (
    <div className="chart-wrap">
      <svg
        ref={svgRef}
        className="chart-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Stacked area chart of network bandwidth by traffic class over time"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* y gridlines + labels */}
        {yTicks.map((v, i) => (
          <g key={i}>
            <line
              x1={M.left}
              x2={W - M.right}
              y1={y(v)}
              y2={y(v)}
              stroke="var(--grid)"
              strokeWidth={1}
            />
            <text
              x={M.left - 8}
              y={y(v)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={11}
              fill="var(--muted)"
            >
              {formatRate(v)}
            </text>
          </g>
        ))}

        {/* stacked bands */}
        {bands.map((b) => (
          <path key={b.label} d={b.d} fill={colorVar(b.label)} opacity={0.92} />
        ))}
        {/* 2px surface gaps between stacked segments (dataviz spacer rule) */}
        {bands.map((b) => (
          <path
            key={`edge-${b.label}`}
            d={b.topLine}
            fill="none"
            stroke="var(--surface-1)"
            strokeWidth={1.5}
          />
        ))}

        {/* x ticks */}
        {xTickIdx.map((i) => (
          <text
            key={i}
            x={x(i)}
            y={H - 8}
            textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
            fontSize={11}
            fill="var(--muted)"
          >
            {formatClock(buckets[i].t)}
          </text>
        ))}

        {/* baseline */}
        <line
          x1={M.left}
          x2={W - M.right}
          y1={y(0)}
          y2={y(0)}
          stroke="var(--baseline)"
          strokeWidth={1}
        />

        {/* hover crosshair */}
        {hover && (
          <line
            x1={x(hover.i)}
            x2={x(hover.i)}
            y1={M.top}
            y2={y(0)}
            stroke="var(--baseline)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}
      </svg>

      {hover && hoverBucket && hoverRows.length > 0 && (
        <div
          className="tooltip"
          style={{
            left: Math.min(hover.x + 14, 620),
            top: Math.max(0, hover.y - 10),
          }}
        >
          <div className="tt-time">{formatClock(hoverBucket.t)}</div>
          {hoverRows.map((r) => (
            <div className="tt-row" key={r.label}>
              <span className="name">
                <span className="swatch" style={{ background: colorVar(r.label) }} aria-hidden />
                {prettyLabel(r.label)}
              </span>
              <span className="val">{formatRate(r.v)}</span>
            </div>
          ))}
        </div>
      )}

      <Legend labels={labels} />
    </div>
  );
}
