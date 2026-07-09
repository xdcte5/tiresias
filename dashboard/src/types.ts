// Wire types mirroring the backend pydantic models (pipeline/scored.py).

export interface ScoredFlow {
  flow_id: string;
  protocol: string;
  src: string;
  dst: string;
  label: string;
  confidence: number;
  anomalous: boolean;
  n_packets: number;
  bytes_total: number;
  duration: number;
  sni: string | null;
  start_ts: number;
  scored_ts: number;
  top_probs: Record<string, number>;
}

export interface BandwidthBucket {
  t: number;
  bytes_by_class: Record<string, number>;
}

export interface Summary {
  total_flows: number;
  anomalous_flows: number;
  per_class_flows: Record<string, number>;
  per_class_bytes: Record<string, number>;
  bandwidth_series: BandwidthBucket[];
  classes: string[];
  bucket_s: number;
}
