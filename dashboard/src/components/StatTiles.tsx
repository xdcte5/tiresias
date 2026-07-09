import { formatRate } from "../format";
import type { ScoredFlow, Summary } from "../types";

function recentThroughput(summary: Summary | null): number {
  if (!summary || summary.bandwidth_series.length === 0) return 0;
  // Bytes/sec in the most recent bucket, summed across classes.
  const last = summary.bandwidth_series[summary.bandwidth_series.length - 1];
  const bytes = Object.values(last.bytes_by_class).reduce((a, b) => a + b, 0);
  return bytes / summary.bucket_s;
}

export default function StatTiles({
  summary,
  flows,
}: {
  summary: Summary | null;
  flows: ScoredFlow[];
}) {
  const totalFlows = summary?.total_flows ?? 0;
  const anomalous = summary?.anomalous_flows ?? 0;
  const activeClasses = summary
    ? Object.keys(summary.per_class_flows).length
    : new Set(flows.map((f) => f.label)).size;

  return (
    <div className="tiles">
      <div className="tile">
        <div className="value mono">{totalFlows.toLocaleString()}</div>
        <div className="label">Flows classified</div>
      </div>
      <div className="tile">
        <div className={`value mono ${anomalous > 0 ? "warn" : ""}`}>
          {anomalous.toLocaleString()}
        </div>
        <div className="label">Flagged unclassified</div>
      </div>
      <div className="tile">
        <div className="value mono">{activeClasses}</div>
        <div className="label">Active classes</div>
      </div>
      <div className="tile">
        <div className="value mono">{formatRate(recentThroughput(summary))}</div>
        <div className="label">Current throughput</div>
      </div>
    </div>
  );
}
