"use client";

import { useEffect, useRef, useState } from "react";
import { compact, d, money, monthLabel } from "@/lib/format";

/* Series colours: validated pair (dataviz validator, light surface: CVD dE 23.6, normal dE 26.6). */
export const SERIES = { a: "#0f7a55", b: "#5b6cf0" };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/** Circular progress with a rounded end. */
export function Ring({ value, size = 120, stroke = 12, color = "var(--color-brand)", track = "var(--color-line)", children }: { value: number; size?: number; stroke?: number; color?: string; track?: string; children?: React.ReactNode }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v)} className="draw" style={{ ["--dash" as string]: c }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{children}</div>
    </div>
  );
}

/** Half-circle gauge: used (solid) + pending (light) out of a limit. */
export function ArcGauge({ used, pending = 0, limit, size = 132, stroke = 12, children }: { used: number; pending?: number; limit: number; size?: number; stroke?: number; children?: React.ReactNode }) {
  const r = (size - stroke) / 2;
  const h = size / 2 + stroke / 2;
  const path = `M ${stroke / 2} ${size / 2} A ${r} ${r} 0 0 1 ${size - stroke / 2} ${size / 2}`;
  const u = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const p = limit > 0 ? Math.min(100 - u, (pending / limit) * 100) : 0;
  return (
    <div className="relative" style={{ width: size, height: h }}>
      <svg width={size} height={h} aria-hidden>
        <path d={path} fill="none" stroke="var(--color-line)" strokeWidth={stroke} strokeLinecap="round" />
        {p > 0.5 && (
          <path d={path} fill="none" stroke="var(--color-brand)" strokeOpacity={0.35} strokeWidth={stroke} strokeLinecap="round" pathLength={100} strokeDasharray={`${p} 200`} strokeDashoffset={-u} />
        )}
        {u > 0.5 && <path d={path} fill="none" stroke="var(--color-brand)" strokeWidth={stroke} strokeLinecap="round" pathLength={100} strokeDasharray={`${u} 200`} className="draw" style={{ ["--dash" as string]: u }} />}
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">{children}</div>
    </div>
  );
}

type Bar = { period: string; salary: number; reimbursements: number; pay_date: string; projected?: boolean };

/** Monthly take-home: salary + reimbursements (stacked), the next payday shown as a projection. */
export function PayChart({ data, height = 230 }: { data: Bar[]; height?: number }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const padL = 44, padB = 26, padT = 8;
  const max = Math.max(1, ...data.map((b) => b.salary + b.reimbursements)) * 1.08;
  const step = niceStep(max / 4);
  const ticks = Array.from({ length: Math.floor(max / step) + 1 }, (_, i) => i * step);
  const innerW = Math.max(0, w - padL);
  const slot = data.length ? innerW / data.length : 0;
  const bw = Math.max(6, Math.min(28, slot * 0.46));
  const y = (v: number) => padT + (height - padT - padB) * (1 - v / max);
  const hb = hover !== null ? data[hover] : null;
  return (
    <div ref={ref} className="relative select-none" onMouseLeave={() => setHover(null)}>
      {w > 0 && (
        <svg width={w} height={height} role="img" aria-label="Monthly take-home pay">
          <defs>
            <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="var(--color-brand-soft)" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--color-brand)" strokeOpacity="0.35" strokeWidth="2" />
            </pattern>
          </defs>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={padL} x2={w} y1={y(t)} y2={y(t)} stroke="var(--color-line)" strokeDasharray={t ? "3 5" : undefined} />
              <text x={padL - 10} y={y(t) + 4} textAnchor="end" className="fill-muted text-[10.5px]">{compact(t)}</text>
            </g>
          ))}
          {data.map((b, i) => {
            const cx = padL + slot * i + slot / 2;
            const x = cx - bw / 2;
            const ys = y(b.salary), yr = y(b.salary + b.reimbursements);
            const dim = hover !== null && hover !== i;
            return (
              <g key={b.period} opacity={dim ? 0.45 : 1} style={{ transition: "opacity .15s" }}>
                {b.projected ? (
                  <path d={roundTop(x, yr, bw, y(0) - yr, 7)} fill="url(#hatch)" stroke="var(--color-brand)" strokeOpacity="0.5" strokeDasharray="4 3" />
                ) : (
                  <>
                    <path d={roundTop(x, ys, bw, y(0) - ys, b.reimbursements > 0 ? 0 : 7)} fill={SERIES.a} />
                    {b.reimbursements > 0 && <path d={roundTop(x, yr, bw, Math.max(0, ys - yr - 2), 7)} fill={SERIES.b} />}
                  </>
                )}
                <text x={cx} y={height - 6} textAnchor="middle" className={b.projected ? "fill-brand text-[10.5px] font-semibold" : "fill-muted text-[10.5px]"}>
                  {b.projected ? "Next" : monthLabel(b.period)}
                </text>
                <rect x={padL + slot * i} y={0} width={slot} height={height - padB} fill="transparent" onMouseEnter={() => setHover(i)} onClick={() => setHover(i)} />
              </g>
            );
          })}
        </svg>
      )}
      {hb && (
        <div
          className="pointer-events-none absolute top-0 z-10 w-48 rounded-2xl bg-ink px-3.5 py-3 text-xs text-white shadow-[var(--shadow-lift)]"
          style={{ left: Math.min(Math.max(0, padL + slot * (hover as number) + slot / 2 - 96), Math.max(0, w - 192)) }}
        >
          <p className="mb-1.5 font-semibold">{hb.projected ? `Next payday · ${d(hb.pay_date, { day: "numeric", month: "short" })}` : `${d(hb.pay_date, { month: "long", year: "numeric" })}`}</p>
          <Row dot={SERIES.a} label="Salary" v={money(hb.salary)} />
          <Row dot={SERIES.b} label="Reimbursements" v={money(hb.reimbursements)} />
          <div className="mt-1.5 flex justify-between border-t border-white/15 pt-1.5 font-semibold">
            <span>{hb.projected ? "Expected" : "Take-home"}</span>
            <span className="num">{money(hb.salary + hb.reimbursements)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ dot, label, v }: { dot: string; label: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="flex items-center gap-1.5 text-white/75">
        <span className="h-2 w-2 rounded-full" style={{ background: dot }} />
        {label}
      </span>
      <span className="num">{v}</span>
    </div>
  );
}

function niceStep(raw: number) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1))));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

/** Bar path with rounded top corners only (data end), flat at the baseline. */
function roundTop(x: number, y: number, w: number, h: number, r: number) {
  if (h <= 0) return "";
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} L${x},${y + rr} Q${x},${y} ${x + rr},${y} L${x + w - rr},${y} Q${x + w},${y} ${x + w},${y + rr} L${x + w},${y + h} Z`;
}

/** Smooth area line (monotone-ish cubic) with hover crosshair. */
export function AreaChart({ points, height = 160, axis = true, format = money }: { points: { label: string; value: number; sub?: string }[]; height?: number; axis?: boolean; format?: (v: number) => string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const padL = axis ? 44 : 4, padB = axis ? 24 : 4, padT = 10, padR = 6;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = hi - lo || hi || 1;
  const min = Math.max(0, lo - span * 0.25), max = hi + span * 0.15;
  const x = (i: number) => padL + ((w - padL - padR) * i) / Math.max(1, points.length - 1);
  const y = (v: number) => padT + (height - padT - padB) * (1 - (v - min) / (max - min || 1));
  const pts = points.map((p, i) => [x(i), y(p.value)] as const);
  const line = smooth(pts);
  const area = pts.length ? `${line} L${pts[pts.length - 1][0]},${height - padB} L${pts[0][0]},${height - padB} Z` : "";
  const gid = useRef(`g${Math.random().toString(36).slice(2, 8)}`).current;
  return (
    <div ref={ref} className="relative select-none" onMouseLeave={() => setHover(null)}>
      {w > 0 && pts.length > 1 && (
        <svg
          width={w} height={height} role="img" aria-label="Trend"
          onMouseMove={(e) => {
            const r = (e.currentTarget as SVGElement).getBoundingClientRect();
            const i = Math.round(((e.clientX - r.left - padL) / (w - padL - padR)) * (points.length - 1));
            setHover(Math.max(0, Math.min(points.length - 1, i)));
          }}
        >
          <defs>
            <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--color-brand)" stopOpacity="0.28" />
              <stop offset="100%" stopColor="var(--color-brand)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {axis &&
            [min, (min + max) / 2, max].map((t) => (
              <g key={t}>
                <line x1={padL} x2={w - padR} y1={y(t)} y2={y(t)} stroke="var(--color-line)" strokeDasharray="3 5" />
                <text x={padL - 10} y={y(t) + 4} textAnchor="end" className="fill-muted text-[10.5px]">{compact(t)}</text>
              </g>
            ))}
          <path d={area} fill={`url(#${gid})`} />
          <path d={line} fill="none" stroke="var(--color-brand)" strokeWidth={2.25} strokeLinecap="round" />
          {axis &&
            points.map((p, i) =>
              i % Math.ceil(points.length / 6) === 0 || i === points.length - 1 ? (
                <text key={i} x={x(i)} y={height - 6} textAnchor={i === points.length - 1 ? "end" : i === 0 ? "start" : "middle"} className="fill-muted text-[10.5px]">{p.label}</text>
              ) : null,
            )}
          {hover !== null && (
            <g>
              <line x1={pts[hover][0]} x2={pts[hover][0]} y1={padT} y2={height - padB} stroke="var(--color-ink)" strokeOpacity="0.15" />
              <circle cx={pts[hover][0]} cy={pts[hover][1]} r={6} fill="var(--color-surface)" stroke="var(--color-brand)" strokeWidth={2.5} />
            </g>
          )}
        </svg>
      )}
      {hover !== null && w > 0 && (
        <div className="pointer-events-none absolute -top-2 z-10 rounded-xl bg-ink px-3 py-2 text-xs text-white shadow-[var(--shadow-lift)]" style={{ left: Math.min(Math.max(0, pts[hover][0] - 60), w - 130) }}>
          <p className="text-white/70">{points[hover].sub ?? points[hover].label}</p>
          <p className="num font-semibold">{format(points[hover].value)}</p>
        </div>
      )}
    </div>
  );
}

function smooth(pts: readonly (readonly [number, number])[]) {
  if (!pts.length) return "";
  let p = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[Math.max(0, i - 1)], [x1, y1] = pts[i], [x2, y2] = pts[i + 1], [x3, y3] = pts[Math.min(pts.length - 1, i + 2)];
    const t = 0.18;
    const c1x = x1 + (x2 - x0) * t, c1y = y1 + (y2 - y0) * t;
    const c2x = x2 - (x3 - x1) * t, c2y = y2 - (y3 - y1) * t;
    const lo = Math.min(y1, y2), hi = Math.max(y1, y2);
    p += ` C${c1x},${Math.min(hi, Math.max(lo, c1y))} ${c2x},${Math.min(hi, Math.max(lo, c2y))} ${x2},${y2}`;
  }
  return p;
}

/** Horizontal stacked bars (two series) with values. */
export function HBars({ rows, labels }: { rows: { label: string; a: number; b: number }[]; labels: [string, string] }) {
  const max = Math.max(1, ...rows.map((r) => r.a + r.b));
  return (
    <div>
      <div className="mb-3 flex gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: SERIES.a }} />{labels[0]}</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: SERIES.b }} />{labels[1]}</span>
      </div>
      <div className="space-y-3.5">
        {rows.map((r) => (
          <div key={r.label} title={`${r.label}: ${money(r.a)} ${labels[0].toLowerCase()}, ${money(r.b)} ${labels[1].toLowerCase()}`}>
            <div className="mb-1.5 flex justify-between text-[13px]">
              <span className="font-medium">{r.label}</span>
              <span className="num text-muted">{money(r.a + r.b)}</span>
            </div>
            <div className="flex h-3 gap-[2px] overflow-hidden rounded-full bg-surface-2">
              {r.a > 0 && <div className="rounded-full" style={{ width: `${(r.a / max) * 100}%`, background: SERIES.a }} />}
              {r.b > 0 && <div className="rounded-full" style={{ width: `${(r.b / max) * 100}%`, background: SERIES.b }} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
