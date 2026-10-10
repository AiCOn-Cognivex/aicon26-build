// Authenticated API client for the finance app (the public model demo keeps using lib/api.ts).
import { API_URL } from "./api";

const TOKEN_KEY = "cvx_token";
const USER_KEY = "cvx_user";

// Last response of each GET, so a page seen before renders at once while it refreshes (stale-while-revalidate),
// and in-flight GETs, so two components asking for the same path share one request. Both are cleared on sign-in,
// sign-out and after any change (POST/PUT/DELETE): never older than the user's last action.
const responses = new Map<string, unknown>();
const inflight = new Map<string, Promise<unknown>>();

export function cachedResponse<T>(path: string): T | undefined {
  return responses.get(path) as T | undefined;
}

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
  responses.clear();
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  } catch {
    /* private mode: session lives in memory only */
  }
}

/** The signed-in user from the last visit: the app renders at once and confirms with /auth/me in the background. */
export function getCachedUser<T>(): T | null {
  try {
    const s = localStorage.getItem(USER_KEY);
    return s ? (JSON.parse(s) as T) : null;
  } catch {
    return null;
  }
}

export function setCachedUser(user: unknown) {
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {}
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
  const method = opts.method ?? (body ? "POST" : "GET");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 30000);
  let r: Response;
  try {
    r = await fetch(`${API_URL}${path}`, { method, headers, body, signal: ctrl.signal, cache: "no-store" });
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
  if (method !== "GET") responses.clear();
  return r;
}

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  if (opts.method || opts.json !== undefined || opts.form) return (await request(path, opts)).json();
  let p = inflight.get(path);
  if (!p) {
    p = request(path, opts)
      .then((r) => r.json())
      .then((d) => {
        responses.set(path, d);
        return d;
      })
      .finally(() => inflight.delete(path));
    inflight.set(path, p);
  }
  return p as Promise<T>;
}

/** Start loading a page's data before navigating to it (errors are left to the page). */
export function prefetch(path: string) {
  api(path, { timeoutMs: 60000 }).catch(() => {});
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
