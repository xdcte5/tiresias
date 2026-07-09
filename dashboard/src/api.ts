// Backend connection config + REST helpers.
// Base URL is injected at build/dev time via VITE_API_BASE, defaulting to the
// local tiresias-serve backend.

import type { Summary } from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8000";

export function wsUrl(): string {
  const base = new URL(API_BASE);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = "/ws/flows";
  return base.toString();
}

export async function fetchSummary(): Promise<Summary> {
  const res = await fetch(`${API_BASE}/stats/summary`);
  if (!res.ok) throw new Error(`summary ${res.status}`);
  return (await res.json()) as Summary;
}
