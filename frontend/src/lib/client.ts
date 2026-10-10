// Authenticated API client for the finance app (the public model demo keeps using lib/api.ts).
import { API_URL } from "./api";

const TOKEN_KEY = "cvx_token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: session lives in memory only */
  }
}

async function errorMessage(r: Response): Promise<string> {
  try {
    const j = await r.json();
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {}
  return `Request failed (${r.status})`;
}

type Opts = { method?: string; json?: unknown; form?: FormData | URLSearchParams; timeoutMs?: number; auth?: boolean };

export async function request(path: string, opts: Opts = {}): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (opts.auth !== false && token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) body = opts.form;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 30000);
  let r: Response;
  try {
    r = await fetch(`${API_URL}${path}`, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, signal: ctrl.signal, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Can't reach the server. It may be waking up, try again in a few seconds.");
  } finally {
    clearTimeout(timer);
  }
  if (r.status === 401 && opts.auth !== false) {
    setToken(null);
    window.dispatchEvent(new Event("cvx:signed-out"));
  }
  if (!r.ok) throw new ApiError(r.status, await errorMessage(r));
  return r;
}

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  return (await request(path, opts)).json();
}

export async function blobUrl(path: string): Promise<string> {
  const r = await request(path);
  return URL.createObjectURL(await r.blob());
}

export async function download(path: string, filename: string) {
  const url = await blobUrl(path);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
