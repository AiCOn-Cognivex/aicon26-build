"""Auto-post policy on out-of-fold (OOF) predictions over train + validation (900 receipts), real OCR.

  python -m ml.policy_cv --cv base                          # production decoding (assemble)
  python -m ml.policy_cv --cv base --decoder rerank --lam 2 # constrained decoding (ml/decode.py)

1. Temperature T fitted on OOF gold-word tokens (Mode A), as ml/calibrate.py does on validation.
2. Policy family = ml/calibrate.py (threshold x require-arithmetic x OCR-confidence x absence check),
   plus an optional floor on the assignment posterior when the decoder provides one.
3. Cross-fitted estimate: for each fold, pick the policy on the other 4 folds (most coverage with
   correctness >= target), apply it to the held-out fold; pooled over 900 receipts with an exact
   Clopper-Pearson interval. This estimates what the selection procedure delivers on unseen receipts.
4. Final policy: the same rule on all 900 OOF receipts (what would be deployed).
Also reports field-confidence ECE and a 10-bin reliability table (OOF, Mode B).
Writes results/policy_cv_<cv>_<decoder>.json.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math

import numpy as np

from .calibrate import _rescale, clopper_pearson, ece
from .cv import K, RES, _records, load_preds
from .decision import DEFAULT_POLICY, decide
from .fields import assemble, gold_fields
from .metrics import compare

THRESHOLDS = [0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.925, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995]
POSTERIOR = [0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 0.98]


def fit_temperature(preds) -> float:
    toks = [(w["probs"], g) for p in preds for w, g in zip(p["A"], p["A_gold"])]

    def nll(T):
        return -sum(math.log(max(_rescale(pr, T).get(g, 1e-12), 1e-12)) for pr, g in toks) / len(toks)
    grid = [round(x, 2) for x in np.arange(0.6, 2.01, 0.05)]
    return float(min(grid, key=nll))


def _temper(tagged, T):
    if T == 1.0:
        return tagged
    out = []
    for w in tagged:
        q = _rescale(w["probs"], T)
        out.append({**w, "probs": q, "prob": q.get(w["label"], w["prob"])})
    return out


def rows_for(preds, decoder, T: float) -> list[dict]:
    recs = _records()
    rows = []
    for p in preds:
        tagged = _temper(p["B"], T)
        pred = decoder(tagged)
        comp = compare(pred, gold_fields(recs[p["id"]]["gt_parse"]))
        rows.append({"id": p["id"], "fold": p["fold"], "pred": pred, "correct": comp["posting_correct"],
                     "fields_ok": comp["fields"]})
    return rows


def decisions(rows, pol) -> list[bool]:
    out = []
    for r in rows:
        p = r["pred"]
        d = decide(p["fields"], p["line_items"], pol, p.get("absent_confidence"))["decision"] == "AUTO_POST"
        if d and pol.get("min_posterior", 0) > 0:
            d = p.get("assignment_posterior", 1.0) >= pol["min_posterior"]
        out.append(d)
    return out


def policies(with_posterior: bool):
    for req, ocr_c, absent in itertools.product((False, True), repeat=3):
        for t in THRESHOLDS:
            for mp in (POSTERIOR if with_posterior else [0.0]):
                yield {**DEFAULT_POLICY, "threshold": t, "require_reconciliation": req, "use_ocr_conf": ocr_c,
                       "check_absent": absent, "min_posterior": mp}


def pick(rows, target, pols, min_auto=20):
    best = None
    for pol in pols:
        d = decisions(rows, pol)
        auto = [r["correct"] for r, x in zip(rows, d) if x]
        if len(auto) < min_auto or sum(auto) / len(auto) < target:
            continue
        key = (len(auto), pol["threshold"], pol["min_posterior"])  # ties -> more conservative
        if best is None or key > best[0]:
            best = (key, pol)
    return best[1] if best else None


def evaluate(rows, target, with_posterior):
    pols = list(policies(with_posterior))
    cross = []
    chosen = []
    for k in range(K):
        train = [r for r in rows if r["fold"] != k]
        test = [r for r in rows if r["fold"] == k]
        pol = pick(train, target, pols)
        chosen.append(pol)
        d = decisions(test, pol) if pol else [False] * len(test)
        cross += [(r["correct"], x) for r, x in zip(test, d)]
    auto = [c for c, x in cross if x]
    k_ok = sum(auto)
    lo, hi = clopper_pearson(k_ok, len(auto))
    final = pick(rows, target, pols)
    fd = decisions(rows, final) if final else [False] * len(rows)
    fa = [r["correct"] for r, x in zip(rows, fd) if x]
    flo, fhi = clopper_pearson(sum(fa), len(fa))
    return {
        "target": target,
        "crossfit": {"coverage": len(auto) / len(rows), "n_auto": len(auto), "n_correct": k_ok,
                     "precision": k_ok / len(auto) if auto else None, "ci95_exact": [lo, hi],
                     "policies_per_fold": [_short(p) for p in chosen]},
        "final_policy_on_all_oof": {"policy": _short(final), "coverage": len(fa) / len(rows), "n_auto": len(fa),
                                    "n_correct": sum(fa), "precision": sum(fa) / len(fa) if fa else None,
                                    "ci95_exact": [flo, fhi], "note": "in-sample for the policy choice"},
        "_final": final,
    }


def _short(p):
    if p is None:
        return None
    return {k: p[k] for k in ("threshold", "require_reconciliation", "use_ocr_conf", "check_absent", "min_posterior")}


def reliability(rows, bins=10):
    cs, ok = [], []
    for r in rows:
        for f, v in r["pred"]["fields"].items():
            if v is not None:
                cs.append(v["confidence"])
                ok.append(r["fields_ok"][f])
    cs, ok = np.asarray(cs), np.asarray(ok, dtype=float)
    table = []
    for i in range(bins):
        m = (cs > i / bins) & (cs <= (i + 1) / bins)
        if m.any():
            table.append({"bin": [i / bins, (i + 1) / bins], "n": int(m.sum()), "mean_conf": float(cs[m].mean()),
                          "accuracy": float(ok[m].mean())})
    return {"field_ece": ece(cs, ok), "n_fields": int(len(cs)), "table": table}


def run(cv: str, decoder_name: str = "assemble", lam: float = 2.0, k: int = 3, write: bool = True) -> dict:
    preds = load_preds(cv)
    T = fit_temperature(preds)
    if decoder_name == "rerank":
        from .decode import rerank
        decoder = lambda t: rerank(t, lam=lam, k=k)
    else:
        decoder = assemble
    rows = rows_for(preds, decoder, T)
    with_post = decoder_name == "rerank"
    res = {"cv": cv, "decoder": decoder_name, "lam": lam if with_post else None, "temperature": T,
           "n": len(rows), "posting_correct_oof": sum(r["correct"] for r in rows) / len(rows),
           "calibration": reliability(rows),
           "per_receipt": {r["id"]: int(r["correct"]) for r in rows}}
    for target in (0.98, 0.99):
        e = evaluate(rows, target, with_post)
        fin = e.pop("_final")
        res[f"at_{int(target * 100)}"] = e
        if fin is not None:
            d = decisions(rows, fin)
            res[f"at_{int(target * 100)}"]["auto_per_receipt"] = {r["id"]: int(x) for r, x in zip(rows, d)}
    if write:
        tag = f"{cv}_{decoder_name}" + (f"_lam{lam:g}" if with_post else "")
        (RES / f"policy_cv_{tag}.json").write_text(json.dumps(res, indent=1))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", default="base")
    ap.add_argument("--decoder", default="assemble", choices=["assemble", "rerank"])
    ap.add_argument("--lam", type=float, default=2.0)
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args()
    r = run(a.cv, a.decoder, a.lam, a.k)
    print(f"{a.cv}/{a.decoder}: T={r['temperature']} posting-correct OOF {r['posting_correct_oof']:.3f}, "
          f"field ECE {r['calibration']['field_ece']:.3f}")
    for t in ("at_98", "at_99"):
        c, f = r[t]["crossfit"], r[t]["final_policy_on_all_oof"]
        print(f"  {t}: cross-fitted coverage {c['coverage']:.3f} ({c['n_correct']}/{c['n_auto']} correct, "
              f"CI {c['ci95_exact'][0]:.3f}-{c['ci95_exact'][1]:.3f}); final policy {f['policy']} "
              f"coverage {f['coverage']:.3f} ({f['n_correct']}/{f['n_auto']})")


if __name__ == "__main__":
    main()
