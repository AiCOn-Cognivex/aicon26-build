"""Receipt-level confidence: P(all five posted amounts are right), learned on out-of-fold predictions.

  python -m ml.confidence --cv base            # -> results/cv/confidence_<cv>.json, ml/artifacts/receipt_conf_crf.json

The decision needs one number per receipt. Field confidences (min token probability) see one field at a time;
this small logistic regression combines the decoder's signals into a calibrated P(posting-correct):
min field confidence, assignment posterior, arithmetic status, lowest absence confidence, lowest OCR
confidence, whether the Viterbi decoding (assemble) and the arithmetic-constrained decoding (rerank) agree,
number of fields, and total present. Inputs are the OOF predictions of `ml.cv` (900 receipts, Mode B).
Honest evaluation is nested: for each outer fold the model AND the auto-post threshold are chosen on the
other 4 folds only (threshold from inner cross-fitted scores), then applied to the held-out fold.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from .calibrate import clopper_pearson, ece
from .cv import K, RES, _records, load_preds
from .dataset import ROOT
from .fields import assemble, gold_fields
from .metrics import compare
from .policy_cv import _temper

ART = ROOT / "ml" / "artifacts"
from .receipt_conf import FEATURES, receipt_features


def _fit(X, y, C=1.0):
    from sklearn.linear_model import LogisticRegression
    mu, sd = X.mean(0), X.std(0) + 1e-9
    m = LogisticRegression(C=C, max_iter=2000).fit((X - mu) / sd, y)
    return {"mu": mu, "sd": sd, "coef": m.coef_[0], "b": float(m.intercept_[0])}


def _score(m, X):
    z = ((X - m["mu"]) / m["sd"]) @ m["coef"] + m["b"]
    return 1 / (1 + np.exp(-z))


def gate(X):
    """Hard rules that hold whatever the score: a total was found and the arithmetic did not FAIL."""
    return (X[:, FEATURES.index("has_total")] > 0) & (X[:, FEATURES.index("recon_fail")] == 0)


def _threshold(scores, y, target, min_auto=20, allowed=None):
    """Lowest threshold whose auto-posted set has precision >= target (most coverage)."""
    order = [i for i in np.argsort(-scores) if allowed is None or allowed[i]]
    best = None
    ok = 0
    for n, i in enumerate(order, 1):
        ok += y[i]
        if n >= min_auto and ok / n >= target:
            best = scores[i]
    return best


def _inner_scores(X, y, folds, C):
    s = np.zeros(len(y))
    for k in np.unique(folds):
        tr, te = folds != k, folds == k
        s[te] = _score(_fit(X[tr], y[tr], C), X[te])
    return s


def build(cv: str, lam: float = 1.5, T: float = 1.1):
    from .decode import rerank
    recs = _records()
    rows = []
    for p in load_preds(cv):
        tagged = _temper(p["B"], T)
        pred, base = rerank(tagged, lam=lam), assemble(tagged)
        rows.append((p["id"], p["fold"], receipt_features(pred, base),
                     compare(pred, gold_fields(recs[p["id"]]["gt_parse"]))["posting_correct"]))
    X = np.array([[r[2][f] for f in FEATURES] for r in rows])
    y = np.array([int(r[3]) for r in rows])
    folds = np.array([r[1] for r in rows])
    return rows, X, y, folds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", default="base")
    ap.add_argument("--lam", type=float, default=1.5)
    ap.add_argument("--C", type=float, default=1.0)
    ap.add_argument("--no-artifact", action="store_true")
    ap.add_argument("--write-policy", type=float, default=None, help="e.g. 0.98: write ml/artifacts/policy_crf.json")
    a = ap.parse_args()
    rows, X, y, folds = build(a.cv, a.lam)
    out = {"cv": a.cv, "lam": a.lam, "C": a.C, "features": FEATURES, "n": len(y),
           "posting_correct_oof": float(y.mean())}
    # 1. OOF scores (model fitted on the other folds) -> calibration
    oof = _inner_scores(X, y, folds, a.C)
    bins = []
    for i in range(10):
        m = (oof > i / 10) & (oof <= (i + 1) / 10)
        if m.any():
            bins.append({"bin": [i / 10, (i + 1) / 10], "n": int(m.sum()), "mean_p": float(oof[m].mean()),
                         "accuracy": float(y[m].mean())})
    out["calibration"] = {"receipt_ece": ece(oof, y), "reliability": bins,
                          "brier": float(np.mean((oof - y) ** 2))}
    # 2. nested: model + threshold chosen on 4 folds, applied to the 5th
    for target in (0.98, 0.99, 0.995):
        auto_ok = auto_n = 0
        ths = []
        for k in range(K):
            tr, te = folds != k, folds == k
            inner = _inner_scores(X[tr], y[tr], folds[tr], a.C)
            th = _threshold(inner, y[tr], target, allowed=gate(X[tr]))
            ths.append(th)
            if th is None:
                continue
            s = _score(_fit(X[tr], y[tr], a.C), X[te])
            sel = (s >= th) & gate(X[te])
            auto_n += int(sel.sum())
            auto_ok += int(y[te][sel].sum())
        lo, hi = clopper_pearson(auto_ok, auto_n)
        out[f"nested_target_{target}"] = {"coverage": auto_n / len(y), "n_auto": auto_n, "n_correct": auto_ok,
                                          "precision": auto_ok / auto_n if auto_n else None, "ci95_exact": [lo, hi],
                                          "thresholds": ths}
        print(f"target {target}: nested coverage {auto_n / len(y):.3f}, {auto_ok}/{auto_n} correct "
              f"({(auto_ok / auto_n if auto_n else 0):.3f}, CI {lo or 0:.3f}-{hi or 0:.3f})")
    # 3. OOF risk-coverage curve (scores from models that did not see the receipt)
    order = [i for i in np.argsort(-oof) if gate(X)[i]]
    curve, ok = [], 0
    for n, i in enumerate(order, 1):
        ok += y[i]
        if n % 45 == 0 or n == len(y):
            curve.append({"coverage": n / len(y), "precision": ok / n, "score": float(oof[i])})
    out["oof_risk_coverage"] = curve
    # 4. final model on all 900 + thresholds from the OOF scores (what would be deployed)
    m = _fit(X, y, a.C)
    final = {"features": FEATURES, "mu": m["mu"].tolist(), "sd": m["sd"].tolist(), "coef": m["coef"].tolist(),
             "intercept": m["b"], "lam": a.lam,
             "thresholds": {str(t): _threshold(oof, y, t, allowed=gate(X)) for t in (0.98, 0.99, 0.995)}}
    out["final_model"] = final
    out["coefficients"] = dict(zip(FEATURES, [round(c, 3) for c in m["coef"]]))
    (RES / f"confidence_{a.cv}.json").write_text(json.dumps(out, indent=1))
    if not a.no_artifact:
        (ART / "receipt_conf_crf.json").write_text(json.dumps(final, indent=1))
    if a.write_policy:
        from .decision import DEFAULT_POLICY
        th = final["thresholds"][str(a.write_policy)]
        pol = {**DEFAULT_POLICY, "threshold": 0.0, "require_reconciliation": False, "use_ocr_conf": False,
               "check_absent": False, "decoder": "rerank", "lam": a.lam, "min_posterior": 0.0,
               "receipt_model": "receipt_conf_crf.json", "receipt_threshold": round(th, 4),
               "model": "crf", "temperature": 1.1,
               "note": f"rerank decoding + receipt confidence >= threshold for {a.write_policy:.1%} precision on "
                       f"OOF (results/cv/confidence_{a.cv}.json); a total and no arithmetic FAIL are always required"}
        (ART / "policy_crf.json").write_text(json.dumps(pol, indent=1))
        print("policy written:", pol)
        # same schema as ml/calibrate.py's curve, read by the app's /model page
        nest = out[f"nested_target_{a.write_policy}"]
        g = gate(X)
        points = []
        for t in sorted({0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.925, 0.95, 0.97, 0.98, 0.99, round(th, 4)}):
            sel = g & (oof >= t)
            k, n = int(y[sel].sum()), int(sel.sum())
            lo, hi = clopper_pearson(k, n)
            points.append({"threshold": t, "coverage": n / len(y), "correctness": k / n if n else None,
                           "n_auto": n, "ci_low": lo, "ci_high": hi})
        (ROOT / "results" / "threshold_curve_crf.json").write_text(json.dumps({
            "model": "CRF (token + layout features)", "split": "out-of-fold, train + validation", "mode": "B",
            "n": len(y), "target": a.write_policy, "score": "receipt confidence P(all five amounts right)",
            "chosen_threshold": round(th, 4), "chosen_policy": {k: v for k, v in pol.items() if k != "note"},
            "chosen_coverage": nest["coverage"], "chosen_correctness": nest["precision"],
            "chosen_ci95_exact": nest["ci95_exact"],
            "note": (f"Nested estimate (model and threshold chosen on 4 folds, applied to the 5th; 900 receipts, "
                     f"real OCR): {nest['coverage']:.1%} auto-posted, {nest['n_correct']}/{nest['n_auto']} correct "
                     f"(exact 95% CI {nest['ci95_exact'][0]:.1%}-{nest['ci95_exact'][1]:.1%}). Points: out-of-fold "
                     f"scores, threshold applied to all 900. A total and no arithmetic FAIL are always required."),
            "points": points}, indent=1))
    print(f"receipt ECE {out['calibration']['receipt_ece']:.3f}, Brier {out['calibration']['brier']:.3f}; "
          f"coefficients {out['coefficients']}")


if __name__ == "__main__":
    main()
