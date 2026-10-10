export const APP_NAME = "Cognivex Pay";

const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export const money = (v: number | null | undefined, cur = "PKR") =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${cur === "PKR" ? "Rs" : cur} ${nf0.format(Math.round(v))}`;

export const compact = (v: number) =>
  Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `${Math.round(v / 1e3)}k` : `${Math.round(v)}`;

/** A typed amount: "4,180", "Rs 4 180.50" -> 4180 / 4180.5 (parseFloat alone stops at the comma: "4,180" -> 4). */
export const parseAmount = (s: string) => parseFloat(s.replace(/[^d.]/g, "")) || 0;

export const pctf = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);

export function d(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }) {
  if (!iso) return "—";
  const dt = iso.length === 10 ? new Date(iso + "T00:00:00") : new Date(iso);
  return dt.toLocaleDateString("en-GB", opts);
}

export const dLong = (iso: string | null | undefined) => d(iso, { weekday: "short", day: "numeric", month: "short" });

export function ago(iso: string | null | undefined) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return d(iso);
}

export function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export const initials = (name: string) =>
  name
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

export const monthLabel = (period: string) => new Date(period + "-01T00:00:00").toLocaleDateString("en-GB", { month: "short" });
