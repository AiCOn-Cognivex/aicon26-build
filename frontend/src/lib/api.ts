import type { DemoExample, Extraction } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function fetchWithTimeout(url: string, init: RequestInit = {}, ms = 8000): Promise<Response> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal, cache: "no-store" });
  } finally {
    clearTimeout(t);
  }
}

export type ServerState = "unknown" | "waking" | "online" | "offline";

/** Poll /health until the backend answers (free hosts sleep when idle). */
export async function ensureAwake(onState?: (s: ServerState, elapsedS: number) => void, maxWaitS = 120): Promise<boolean> {
  const start = Date.now();
  let first = true;
  while ((Date.now() - start) / 1000 < maxWaitS) {
    try {
      const r = await fetchWithTimeout(`${API_URL}/health`, {}, first ? 4000 : 10000);
      if (r.ok) {
        onState?.("online", (Date.now() - start) / 1000);
        return true;
      }
    } catch {
      /* sleeping or unreachable */
    }
    first = false;
    onState?.("waking", Math.round((Date.now() - start) / 1000));
    await new Promise((res) => setTimeout(res, 3000));
  }
  onState?.("offline", maxWaitS);
  return false;
}

export async function health(): Promise<Record<string, unknown> | null> {
  try {
    const r = await fetchWithTimeout(`${API_URL}/health`, {}, 5000);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export async function extract(file: File): Promise<{ result: Extraction; latencyMs: number }> {
  const fd = new FormData();
  fd.append("file", file);
  const t0 = performance.now();
  const r = await fetchWithTimeout(`${API_URL}/extract`, { method: "POST", body: fd }, 90000);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      msg += `: ${(await r.json()).detail}`;
    } catch {}
    throw new Error(msg);
  }
  return { result: await r.json(), latencyMs: Math.round(performance.now() - t0) };
}

/** Live /results, or the bundled snapshot of the same files if the backend is unreachable. */
export async function getResults(): Promise<{ data: Record<string, any>; source: "live" | "snapshot" }> {
  try {
    const r = await fetchWithTimeout(`${API_URL}/results`, {}, 6000);
    if (r.ok) return { data: await r.json(), source: "live" };
  } catch {}
  const r = await fetch("/demo/results.json");
  return { data: r.ok ? await r.json() : {}, source: "snapshot" };
}

/** Cached demo examples are bundled with the frontend so they work with no backend at all. */
export async function getDemoExamples(): Promise<DemoExample[]> {
  const r = await fetch("/demo/examples.json");
  if (!r.ok) return [];
  return (await r.json()).examples ?? [];
}
