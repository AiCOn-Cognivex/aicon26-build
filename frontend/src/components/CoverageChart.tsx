"use client";
import { useState } from "react";

export type CurvePoint = { threshold: number; coverage: number; correctness: number | null; n_auto: number; ci_low?: number | null; ci_high?: number | null };

/** Coverage (share auto-posted) vs correctness of auto-posted receipts, one point per threshold. */
export default function CoverageChart({ points, target, chosen }: { points: CurvePoint[]; target: number; chosen?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = points.filter((p) => p.correctness !== null).sort((a, b) => a.coverage - b.coverage);
  if (!pts.length) return null;
  const W = 560, H = 260, L = 44, R = 12, T = 12, B = 34;
  const yMin = Math.min(0.8, ...pts.map((p) => p.ci_low ?? p.correctness!));
  const x = (v: number) => L + v * (W - L - R);
  const y = (v: number) => T + (1 - (v - yMin) / (1 - yMin)) * (H - T - B);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.coverage).toFixed(1)},${y(p.correctness!).toFixed(1)}`).join(" ");
  const band =
    pts.every((p) => p.ci_low != null && p.ci_high != null) &&
    pts.map((p, i) => `${i ? "L" : "M"}${x(p.coverage)},${y(p.ci_high!)}`).join(" ") +
      " " + [...pts].reverse().map((p) => `L${x(p.coverage)},${y(p.ci_low!)}`).join(" ") + " Z";
  const yTicks = [yMin, (yMin + 1) / 2, 1].map((v) => Math.round(v * 100) / 100);
  const h = hover !== null ? pts[hover] : null;
  const chosenPt = chosen !== undefined ? pts.find((p) => Math.abs(p.threshold - chosen) < 1e-9) : undefined;

  return (
    <figure className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
        aria-label="Correctness of auto-posted receipts versus share of receipts auto-posted, one point per confidence threshold"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const cx = ((e.clientX - r.left) / r.width) * W;
          let best = 0;
          pts.forEach((p, i) => { if (Math.abs(x(p.coverage) - cx) < Math.abs(x(pts[best].coverage) - cx)) best = i; });
          setHover(best);
        }}>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--color-line)" />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--color-muted)">{Math.round(t * 100)}%</text>
          </g>
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <text key={t} x={x(t)} y={H - 14} textAnchor="middle" fontSize="11" fill="var(--color-muted)">{Math.round(t * 100)}%</text>
        ))}
        <text x={(L + W - R) / 2} y={H - 1} textAnchor="middle" fontSize="11" fill="var(--color-muted)">share of receipts auto-posted (coverage)</text>
        <line x1={L} x2={W - R} y1={y(target)} y2={y(target)} stroke="var(--color-muted)" strokeDasharray="4 4" />
        <text x={W - R} y={y(target) - 4} textAnchor="end" fontSize="11" fill="var(--color-muted)">target {Math.round(target * 100)}%</text>
        {band && <path d={band} fill="var(--color-brand)" opacity={0.12} />}
        <path d={path} fill="none" stroke="var(--color-brand)" strokeWidth={2} />
        {chosenPt && <circle cx={x(chosenPt.coverage)} cy={y(chosenPt.correctness!)} r={5} fill="var(--color-brand)" stroke="var(--color-surface)" strokeWidth={2} />}
        {h && (
          <>
            <line x1={x(h.coverage)} x2={x(h.coverage)} y1={T} y2={H - B} stroke="var(--color-muted)" opacity={0.4} />
            <circle cx={x(h.coverage)} cy={y(h.correctness!)} r={4} fill="var(--color-brand)" stroke="var(--color-surface)" strokeWidth={2} />
          </>
        )}
      </svg>
      {h && (
        <div className="pointer-events-none absolute rounded-md border border-line bg-surface px-2 py-1 text-xs shadow-sm"
          style={{ left: `${(100 * x(h.coverage)) / W}%`, top: 0, transform: "translateX(-50%)" }}>
          threshold {h.threshold.toFixed(2)} · auto-posted {Math.round(100 * h.coverage)}% ({h.n_auto}) · correct {(100 * h.correctness!).toFixed(1)}%
          {h.ci_low != null && <> (95% CI {(100 * h.ci_low).toFixed(0)}–{(100 * h.ci_high!).toFixed(0)}%)</>}
        </div>
      )}
      <figcaption className="mt-1 text-xs text-muted">
        Each point is a confidence threshold. Moving right auto-posts more receipts; the shaded band is a bootstrap 95% confidence interval.
        {chosenPt && " The filled dot is the threshold the app uses."}
      </figcaption>
    </figure>
  );
}
