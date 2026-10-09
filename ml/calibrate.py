"""Decision-layer fitting on VALIDATION only: temperature scaling, ECE, threshold + policy choice.

  python -m ml.calibrate --model crf
Steps
 1. Temperature T: rescale each word's label distribution p -> p^(1/T) (= temperature scaling of
    log-probs) to minimise NLL of the gold labels on validation gold words. Report token ECE before/after.
 2. Field ECE: field confidence (min token prob) vs whether the field is exactly right (real OCR).
 3. Sweep the confidence threshold (and two policy switches) on validation in real-OCR mode.
    Choose the policy that auto-posts the most receipts while correctness among auto-posted >= 98%
    (point estimate) with at least 20 auto-posted receipts; report a bootstrap 95% CI. With ~100
    validation receipts the CI is wide, and we say so.
Writes ml/artifacts/<model>_calibration.json, ml/artifacts/policy_<model>.json,
results/calibration_<model>.json, results/threshold_curve_<model>.json
"""
from __future__ import annotations

import argparse
import json
import math
import random

import numpy as np

from . import taggers
from .dataset import ROOT, gold_sequence, load_split
from .decision import DEFAULT_POLICY, decide
from .fields import assemble, gold_fields
from .metrics import compare
from .ocr import normalise_words
from .ocr_cache import load_cache

ART = ROOT / "ml" / "artifacts"
RES = ROOT / "results"
TARGET = 0.98


def _rescale(probs: dict, T: float) -> dict:
    logs = {k: math.log(max(v, 1e-12)) / T for k, v in probs.items()}
    m = max(logs.values())
    ex = {k: math.exp(v - m) for k, v in logs.items()}
    z = sum(ex.values())
    return {k: v / z for k, v in ex.items()}


def clopper_pearson(k: int, n: int, alpha: float = 0.05):
    """Exact binomial CI; unlike the bootstrap it is not degenerate when k == n."""
    from scipy.stats import beta
    if n == 0:
        return (None, None)
    lo = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return lo, hi


def ece(conf, correct, bins=10):
    conf, correct = np.asarray(conf), np.asarray(correct, dtype=float)
    e = 0.0
    for i in range(bins):
        m = (conf > i / bins) & (conf <= (i + 1) / bins)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return float(e)


def retag(ws, T):
    """Apply temperature T to stored word distributions and redo argmax + prob."""
    if not ws or "probs" not in ws[0]:
        return ws
    out = []
    for w in ws:
        p = _rescale(w["probs"], T)
        lab = max(p, key=p.get)
        out.append({**w, "label": lab, "prob": p[lab]})
    prev = "O"
    for w in out:  # BIO repair
        if w["label"].startswith("I-") and prev[2:] != w["label"][2:]:
            w["label"] = "B-" + w["label"][2:]
        prev = w["label"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="crf")
    ap.add_argument("--engine", default="rapidocr")
    a = ap.parse_args()
    name, rung, fn = taggers.load(a.model, calibrated=False)  # fit T on raw scores
    recs = load_split("validation")

    # ---- 1. temperature on gold words (token level); rules have no probabilities -> T = 1
    tok_cache = []
    has_probs = a.model != "rules"
    for r in recs:
        gs = gold_sequence(r)
        gmap = {(w["text"], tuple(round(v, 1) for v in w["box"])): w["label"] for w in gs}
        tagged = fn([{"text": w["text"], "box": w["box"]} for w in r["words"]], r["width"], r["height"])
        if not has_probs:
            continue
        for w in tagged:
            tok_cache.append((w["probs"], gmap.get((w["text"], tuple(round(v, 1) for v in w["box"])), "O")))

    def nll(T):
        return -sum(math.log(max(_rescale(p, T).get(g, 1e-12), 1e-12)) for p, g in tok_cache) / len(tok_cache)

    grid = [round(x, 2) for x in np.arange(0.5, 3.01, 0.05)]
    T = float(min(grid, key=nll)) if has_probs else 1.0

    def tok_ece(T):
        cs, ok = [], []
        for p, g in tok_cache:
            q = _rescale(p, T)
            lab = max(q, key=q.get)
            cs.append(q[lab])
            ok.append(lab == g)
        return ece(cs, ok)

    calib = {"model": name, "temperature": T}
    if has_probs:
        calib.update({"nll_before": nll(1.0), "nll_after": nll(T), "token_ece_before": tok_ece(1.0),
                      "token_ece_after": tok_ece(T), "n_tokens": len(tok_cache)})

    # ---- 2+3. real-OCR receipts on validation
    cache = load_cache(a.engine, "validation")
    rows = []
    for r in recs:
        c = cache[r["id"]]
        tagged = fn(normalise_words(c["words"]), c["width"], c["height"])
        gold = gold_fields(r["gt_parse"])
        rows.append((tagged, gold))

    def field_ece(T):
        cs, ok = [], []
        for tagged, gold in rows:
            pred = assemble(retag(tagged, T))
            comp = compare(pred, gold)
            for f, v in pred["fields"].items():
                if v is not None:
                    cs.append(v["confidence"])
                    ok.append(comp["fields"][f])
        return ece(cs, ok), len(cs)

    calib["field_ece_before"], n_fields = field_ece(1.0)
    calib["field_ece_after"], _ = field_ece(T)
    calib["n_predicted_fields"] = n_fields
    preds = []
    for tagged, gold in rows:
        pred = assemble(retag(tagged, T))
        preds.append((pred, compare(pred, gold)))

    def evaluate_policy(pol):
        dec = [decide(p["fields"], p["line_items"], pol, p.get("absent_confidence"))["decision"] for p, _ in preds]
        auto = [c["posting_correct"] for d, (_, c) in zip(dec, preds) if d == "AUTO_POST"]
        return dec, auto

    rng = random.Random(0)
    boot_idx = [[rng.randrange(len(preds)) for _ in preds] for _ in range(1000)]

    def ci(dec):
        vals = []
        for idx in boot_idx:
            auto = [preds[i][1]["posting_correct"] for i in idx if dec[i] == "AUTO_POST"]
            if auto:
                vals.append(sum(auto) / len(auto))
        vals.sort()
        return (vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]) if vals else (None, None)

    thresholds = sorted({0.0, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.925, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995, 0.999})
    candidates, curve = [], []
    import itertools
    # item rule stays off: it fails on 9% of TRAIN gold receipts (results/data_profile.md)
    for req, ocr_c, absent in itertools.product((False, True), repeat=3):
        for t in thresholds:
            pol = {**DEFAULT_POLICY, "threshold": t, "require_reconciliation": req,
                   "use_ocr_conf": ocr_c, "check_absent": absent}
            dec, auto = evaluate_policy(pol)
            cov = len(auto) / len(preds)
            corr = sum(auto) / len(auto) if auto else None
            candidates.append((pol, cov, corr, len(auto), dec))
    feasible = [c for c in candidates if c[2] is not None and c[2] >= TARGET and c[3] >= 20]
    if feasible:
        # ties in coverage -> the most conservative (highest) threshold
        best = max(feasible, key=lambda c: (c[1], c[0]["threshold"]))
        note = f"Chosen: most coverage with >= {int(TARGET * 100)}% correctness among >= 20 auto-posted validation receipts."
    elif [c for c in candidates if c[2] is not None and c[3] >= 10]:
        best = max([c for c in candidates if c[2] is not None and c[3] >= 10], key=lambda c: (c[2], c[1]))
        note = f"No policy reached {int(TARGET * 100)}% on validation; chose the most accurate policy with >= 10 auto-posts."
    else:  # model too weak to auto-post anything safely: send everything to review
        never = {**DEFAULT_POLICY, "threshold": 1.01, "require_reconciliation": True}
        best = (never, 0.0, None, 0, ["HUMAN_REVIEW"] * len(preds))
        note = "No policy auto-posted >= 10 validation receipts; everything goes to human review."
    pol = best[0]
    lo, hi = ci(best[4])
    k_ok = round(best[2] * best[3]) if best[2] is not None else 0
    cp_lo, cp_hi = clopper_pearson(k_ok, best[3])
    if best[3]:
        note += (f" {k_ok}/{best[3]} auto-posted validation receipts were correct; exact 95% CI {cp_lo:.1%}-{cp_hi:.1%}"
                 f" (bootstrap {lo:.1%}-{hi:.1%}). {best[3]} receipts cannot establish 98%;"
                 f" the single test-set run is the independent check.")
    for c in candidates:  # curve for the chosen switches
        if all(c[0][k] == pol[k] for k in ("require_reconciliation", "use_ocr_conf", "check_absent")):
            l, h = ci(c[4])
            k = round(c[2] * c[3]) if c[2] is not None else 0
            cl, ch = clopper_pearson(k, c[3])
            curve.append({"threshold": c[0]["threshold"], "coverage": c[1], "correctness": c[2], "n_auto": c[3],
                          "ci_low": cl, "ci_high": ch, "boot_low": l, "boot_high": h})

    ART.mkdir(parents=True, exist_ok=True)
    (ART / f"{a.model}_calibration.json").write_text(json.dumps({"temperature": T}))
    policy = {k: pol[k] for k in DEFAULT_POLICY} | {"model": a.model, "temperature": T}
    (ART / f"policy_{a.model}.json").write_text(json.dumps(policy, indent=1))
    (RES / f"calibration_{a.model}.json").write_text(json.dumps(calib, indent=1))
    (RES / f"threshold_curve_{a.model}.json").write_text(json.dumps({
        "model": name, "split": "validation", "mode": "B", "n": len(preds), "target": TARGET,
        "chosen_threshold": pol["threshold"], "chosen_policy": policy, "chosen_coverage": best[1],
        "chosen_correctness": best[2], "chosen_ci95_exact": [cp_lo, cp_hi], "chosen_ci95_bootstrap": [lo, hi],
        "note": note, "points": curve}, indent=1))
    print(json.dumps(calib, indent=1))
    print(note)
    print("policy:", policy, "coverage", best[1], "correctness", best[2])
    # transparency: best coverage per switch combination at >= target
    summ = {}
    for pol_, cov, corr, n, _ in candidates:
        key = f"req={pol_['require_reconciliation']},ocr={pol_['use_ocr_conf']},absent={pol_['check_absent']}"
        if corr is not None and corr >= TARGET and n >= 20 and cov > summ.get(key, (0,))[0]:
            summ[key] = (cov, corr, pol_["threshold"])
    for k, v in summ.items():
        print(f"  {k}: coverage {v[0]:.2f} correctness {v[1]:.3f} at threshold {v[2]}")


if __name__ == "__main__":
    main()
