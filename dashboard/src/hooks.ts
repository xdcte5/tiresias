import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSummary, wsUrl } from "./api";
import type { ScoredFlow, Summary } from "./types";

const MAX_FLOWS = 200;

interface WsMessage {
  type: "snapshot" | "flow";
  flow?: ScoredFlow;
  flows?: ScoredFlow[];
  summary?: Summary;
}

/** Live scored-flow stream over WebSocket, with auto-reconnect. */
export function useLiveFlows(): { flows: ScoredFlow[]; connected: boolean } {
  const [flows, setFlows] = useState<ScoredFlow[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<number>(0);

  const connect = useCallback(() => {
    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retryRef.current = 0;
    };
    ws.onclose = () => {
      setConnected(false);
      // Exponential backoff reconnect (capped at 5s).
      const delay = Math.min(5000, 500 * 2 ** retryRef.current);
      retryRef.current += 1;
      window.setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (ev: MessageEvent<string>) => {
      const msg = JSON.parse(ev.data) as WsMessage;
      if (msg.type === "snapshot" && msg.flows) {
        setFlows(msg.flows.slice().reverse().slice(0, MAX_FLOWS));
      } else if (msg.type === "flow" && msg.flow) {
        setFlows((prev) => [msg.flow as ScoredFlow, ...prev].slice(0, MAX_FLOWS));
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      const ws = wsRef.current;
      if (ws) {
        ws.onclose = null; // prevent reconnect on unmount
        ws.close();
      }
    };
  }, [connect]);

  return { flows, connected };
}

/** Poll the REST summary on an interval (drives the bandwidth chart + tiles). */
export function useSummary(intervalMs = 2000): Summary | null {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await fetchSummary();
        if (alive) setSummary(s);
      } catch {
        /* backend not up yet; keep last */
      }
    };
    void tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [intervalMs]);

  return summary;
}
