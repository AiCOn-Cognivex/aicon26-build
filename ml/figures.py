"""SVG figures from result files (no plotting dependency): reliability diagram and risk-coverage curve.

  python -m ml.figures      # -> results/figures/reliability_receipt_crf.svg, risk_coverage_crf.svg
Source: results/cv/confidence_base.json (OOF receipt confidence, 900 receipts, real OCR) and
results/cv/policy_cv_base_assemble.json (production field confidence, same receipts).
"""
from __future__ import annotations

import json

from .dataset import ROOT

RES = ROOT / "results"
OUT = RES / "figures"
W, H, PAD = 420, 320, 48
INK, GRID, A, B = "#1f2933", "#d5dbe1", "#0f7a55", "#5b6cf0"


def _frame(title, xl, yl, x0=0.0, x1=1.0, y0=0.0, y1=1.0):
    def sx(v):
        return PAD + (v - x0) / (x1 - x0) * (W - 2 * PAD)

    def sy(v):
        return H - PAD - (v - y0) / (y1 - y0) * (H - 2 * PAD)
    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="11">',
         f'<rect width="{W}" height="{H}" fill="#fff"/>',
         f'<text x="{W / 2}" y="18" text-anchor="middle" font-size="13" fill="{INK}">{title}</text>']
    for i in range(6):
        xv, yv = x0 + i * (x1 - x0) / 5, y0 + i * (y1 - y0) / 5
        g.append(f'<line x1="{PAD}" x2="{W - PAD}" y1="{sy(yv):.1f}" y2="{sy(yv):.1f}" stroke="{GRID}"/>')
        g.append(f'<text x="{PAD - 6}" y="{sy(yv) + 4:.1f}" text-anchor="end" fill="{INK}">{yv:.2f}</text>')
        g.append(f'<text x="{sx(xv):.1f}" y="{H - PAD + 16}" text-anchor="middle" fill="{INK}">{xv:.1f}</text>')
    g.append(f'<text x="{W / 2}" y="{H - 10}" text-anchor="middle" fill="{INK}">{xl}</text>')
    g.append(f'<text x="14" y="{H / 2}" text-anchor="middle" fill="{INK}" transform="rotate(-90 14 {H / 2})">{yl}</text>')
    return g, sx, sy


def reliability():
    d = json.loads((RES / "cv" / "confidence_base.json").read_text())
    g, sx, sy = _frame(f"Receipt confidence vs accuracy (OOF, n={d['n']}, ECE {d['calibration']['receipt_ece']:.3f})",
                       "predicted P(all amounts right)", "observed accuracy")
    g.append(f'<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(1)}" y2="{sy(1)}" stroke="{GRID}" stroke-dasharray="4 4"/>')
    for b in d["calibration"]["reliability"]:
        r = 3 + min(9, b["n"] ** 0.5 / 2)
        g.append(f'<circle cx="{sx(b["mean_p"]):.1f}" cy="{sy(b["accuracy"]):.1f}" r="{r:.1f}" fill="{A}" '
                 f'fill-opacity="0.8"><title>{b["n"]} receipts: mean {b["mean_p"]:.2f}, '
                 f'accuracy {b["accuracy"]:.2f}</title></circle>')
    g.append("</svg>")
    return "\n".join(g)


def risk_coverage():
    d = json.loads((RES / "cv" / "confidence_base.json").read_text())
    g, sx, sy = _frame("Auto-post precision vs coverage (OOF, real OCR)", "share of receipts auto-posted",
                       "correct among auto-posted", y0=0.9, y1=1.0)
    pts = [(c["coverage"], c["precision"]) for c in d["oof_risk_coverage"]]
    g.append(f'<polyline fill="none" stroke="{A}" stroke-width="2" points="'
             + " ".join(f"{sx(x):.1f},{sy(max(0.9, y)):.1f}" for x, y in pts) + '"/>')
    for t, col in ((0.98, B),):
        g.append(f'<line x1="{PAD}" x2="{W - PAD}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" stroke="{col}" stroke-dasharray="5 4"/>')
        g.append(f'<text x="{W - PAD}" y="{sy(t) - 4:.1f}" text-anchor="end" fill="{INK}">target {t:.0%}</text>')
    n = d["nested_target_0.98"]
    g.append(f'<circle cx="{sx(n["coverage"]):.1f}" cy="{sy(n["precision"]):.1f}" r="5" fill="{B}"><title>nested estimate: '
             f'{n["coverage"]:.1%} auto-posted, {n["n_correct"]}/{n["n_auto"]} correct</title></circle>')
    g.append(f'<text x="{PAD + 6}" y="{H - PAD - 8}" fill="{INK}">green: receipt confidence ranking; dot: nested 98% policy</text>')
    g.append("</svg>")
    return "\n".join(g)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reliability_receipt_crf.svg").write_text(reliability(), encoding="utf-8")
    (OUT / "risk_coverage_crf.svg").write_text(risk_coverage(), encoding="utf-8")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
