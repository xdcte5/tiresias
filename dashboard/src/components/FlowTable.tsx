import { colorVar, prettyLabel } from "../colors";
import { formatBytes, secondsAgo } from "../format";
import type { ScoredFlow } from "../types";

function ClassChip({ label }: { label: string }) {
  if (label === "unclassified") {
    // Status meaning never carried by color alone: icon + label.
    return (
      <span className="anom-flag" title="Model confidence below threshold">
        <span aria-hidden>⚠</span> Unclassified
      </span>
    );
  }
  return (
    <span className="chip">
      <span className="swatch" style={{ background: colorVar(label) }} aria-hidden />
      {prettyLabel(label)}
    </span>
  );
}

export default function FlowTable({ flows }: { flows: ScoredFlow[] }) {
  if (flows.length === 0) {
    return <div className="chart-empty">Waiting for flows…</div>;
  }
  return (
    <div className="table-wrap">
      <table className="flows">
        <thead>
          <tr>
            <th>When</th>
            <th>Source</th>
            <th>Destination</th>
            <th>Class</th>
            <th>Conf.</th>
            <th className="num">Size</th>
            <th className="num">Pkts</th>
            <th>Proto</th>
            <th>SNI</th>
          </tr>
        </thead>
        <tbody>
          {flows.slice(0, 60).map((f) => (
            <tr key={f.flow_id + f.scored_ts} className={f.anomalous ? "anom" : ""}>
              <td className="dim">{secondsAgo(f.scored_ts)}</td>
              <td className="mono">{f.src}</td>
              <td className="mono">{f.dst}</td>
              <td>
                <ClassChip label={f.label} />
              </td>
              <td>
                <span className="confbar" aria-hidden>
                  <span style={{ width: `${Math.round(f.confidence * 100)}%` }} />
                </span>
                <span className="mono">{Math.round(f.confidence * 100)}%</span>
              </td>
              <td className="num">{formatBytes(f.bytes_total)}</td>
              <td className="num">{f.n_packets}</td>
              <td className="dim">{f.protocol}</td>
              <td className="dim">{f.sni ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
