"""Second-stage amount ranker (D27, REJECTED: no gain over the CRF + arithmetic decoder; not used in production).

Which money token is the total / subtotal / tax / service / discount?

  python -m ml.ranker --cv tier1                 # nested CV estimate -> results/cv/ranker_<cv>.json
  python -m ml.ranker --cv tier1 --write         # + final model ml/artifacts/ranker_crf.json and its OOF predictions

The CRF labels tokens from local evidence. The ranker re-scores every money token for each of the five posted
fields with receipt-level evidence the CRF cannot see: the CRF's own label distribution, the label words on the
token's line and the lines around it, its rank and position among the amounts, and arithmetic relations between
amounts (equals the sum of the item prices, is the sum of two other amounts, is a typical tax/service percentage of
another amount, is the base of one). One logistic model per field, trained on out-of-fold CRF predictions
(ml/cv.py), so it learns how the CRF errs on receipts it has not seen. Its probabilities replace the CRF marginals
in the arithmetic-constrained decoder (ml/decode.py). Served from plain coefficients (numpy only).
"""
from __future__ import annotations

import argparse
import json
import math
import re

import numpy as np

from .dataset import ROOT
from .money import parse_money
from .rules_baseline import SKIP_RE
from .schema import HEADER_FIELDS

ART = ROOT / "ml" / "artifacts"
FIELDS = list(HEADER_FIELDS)
_GROUPS = {"total": ["total.total_price"], "subtotal": ["sub_total.subtotal_price"], "tax": ["sub_total.tax_price"],
           "service": ["sub_total.service_price"], "discount": ["sub_total.discount_price"],
           "cash": ["total.cashprice", "total.creditcardprice", "total.emoneyprice"], "change": ["total.changeprice"],
           "item": ["menu.price", "menu.unitprice", "menu.sub.price", "menu.discountprice"]}
_KWC = ["total_price", "subtotal_price", "tax_price", "service_price", "discount_price"]
_RATES = (0.05, 0.06, 0.075, 0.1, 0.11, 0.12, 0.13, 0.15, 0.16, 0.17)


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _gp(w, g):
    pr = w.get("probs") or {}
    return sum(pr.get(f"{b}-{c}", 0.0) for c in _GROUPS[g] for b in "BI")


def _close(a, b):
    return abs(a - b) <= max(1.0, 0.002 * max(abs(a), abs(b)))


def token_features(tagged: list[dict]) -> tuple[list[int], list[float], list[dict]]:
    """Money tokens of a tagged receipt -> (token indices, values, feature dicts)."""
    from .crf_model import _kw_names
    money = []
    for i, w in enumerate(tagged):
        t = w["text"]
        if not any(ch.isdigit() for ch in t):
            continue
        v = parse_money(t)
        if v is None or v == 0:
            continue
        money.append((i, abs(float(v))))
    if not money:
        return [], [], []
    vals = [v for _, v in money]
    distinct = sorted(set(vals), reverse=True)
    vmax = distinct[0]
    lines: dict[int, list[int]] = {}
    for i, w in enumerate(tagged):
        lines.setdefault(w.get("line_no", 0), []).append(i)
    ltext = {ln: " ".join(tagged[i]["text"] for i in idx) for ln, idx in lines.items()}
    lkw = {ln: _kw_names(t) for ln, t in ltext.items()}
    lskip = {ln: bool(SKIP_RE.search(t)) for ln, t in ltext.items()}
    n_lines = max(1, max(lines) + 1) if lines else 1
    items = sum(v for i, v in money if tagged[i].get("label", "O").endswith("menu.price"))
    ys = [w["box"][1] for w in tagged]
    y0, y1 = min(ys), max(ys) + 1e-6
    xs = [w["box"][2] for w in tagged]
    x1 = max(xs) + 1e-6
    feats = []
    sv = sorted(vals)

    def has(x):  # an amount equal to x (rounding tolerance) printed on the receipt
        from bisect import bisect_left
        tol = max(1.0, 0.002 * abs(x))
        k = bisect_left(sv, x - tol)
        return k < len(sv) and sv[k] <= x + tol
    order = {i: k for k, (i, _) in enumerate(reversed(money))}
    for i, v in money:
        w = tagged[i]
        ln = w.get("line_no", 0)
        others = [u for j, u in money if j != i]
        pct = [r * v for r in _RATES]
        f = {g: _gp(w, g) for g in _GROUPS}
        f["other"] = max(0.0, 1.0 - sum(f[g] for g in _GROUPS))
        for g in ("total", "subtotal", "tax", "service", "discount"):
            f[f"logit_{g}"] = _logit(f[g])
        lab = w.get("label", "O")
        for g, cats in _GROUPS.items():
            f[f"viterbi_{g}"] = float(lab != "O" and lab.split("-", 1)[1] in cats)
        f.update({
            "log_value": math.log10(v + 1), "rank": min(distinct.index(v) + 1, 6) / 6, "is_max": float(v == vmax),
            "rel_max": v / vmax, "n_same": min(sum(_close(v, u) for u in others), 3) / 3,
            "eq_items": float(items > 0 and _close(v, items)),
            "is_sum_of_two": float(any(a < v and has(v - a) for a in others)),
            "part_of_sum": float(any(t > v and has(t - v) for t in others)),
            "is_pct_of_other": float(any(has(v / r) for r in _RATES)),
            "base_of_pct": float(any(has(x) for x in pct)),
            "base_plus_pct_present": float(any(has(x) and has(v + x) for x in pct)),
            "y_rel": (w["box"][1] - y0) / (y1 - y0), "x_right": w["box"][2] / x1,
            "line_from_bottom": min(n_lines - 1 - ln, 10) / 10, "money_from_bottom": min(order[i], 6) / 6,
            "last_on_line": float(lines[ln][-1] == i), "skip_line": float(lskip.get(ln, False)),
            "ocr_conf": float(w.get("ocr_conf", 1.0)),
        })
        for c in _KWC:
            f[f"kw_{c}"] = float(c in lkw.get(ln, ()))
            f[f"prev_kw_{c}"] = float(c in lkw.get(ln - 1, ()))
            f[f"next_kw_{c}"] = float(c in lkw.get(ln + 1, ()))
        f["kw_none"] = float(not lkw.get(ln) and not lskip.get(ln, False))
        feats.append(f)
    return [i for i, _ in money], vals, feats


FEATURES: list[str] | None = None


def _matrix(feats):
    global FEATURES
    if FEATURES is None:
        FEATURES = sorted(feats[0])
    return np.array([[f[k] for k in FEATURES] for f in feats], dtype=float)


def dataset(preds, recs):
    """Rows: one per money token of every receipt. Label for a field: the gold annotation projected onto that OCR
    token (position, as the CRF's OCR training data, D9) says it is that field. Value equality alone is noisy:
    the cash paid often equals the total, and the subtotal often equals the total."""
    from .cv import _caches, ocr_sequence
    from .policy_cv import _temper
    cache, _ = _caches([])
    cat2f = {v: k for k, v in HEADER_FIELDS.items()}
    rows, meta = [], []
    for p in preds:
        rec = recs[p["id"]]
        proj = {(w["text"], tuple(round(x, 1) for x in w["box"])): w["label"] for w in ocr_sequence(rec, cache[p["id"]])}
        tagged = _temper(p["B"], 1.1)
        idx, vals, feats = token_features(tagged)
        for i, v, ft in zip(idx, vals, feats):
            w = tagged[i]
            lab = proj.get((w["text"], tuple(round(x, 1) for x in w["box"])), "O")
            f_true = cat2f.get(lab.split("-", 1)[1]) if lab != "O" else None
            rows.append(ft)
            meta.append((p["id"], p["fold"], i, {f: int(f == f_true) for f in FIELDS}))
    return _matrix(rows), meta


KIND = "lr"


def fit(X, meta, C=1.0) -> dict:
    if KIND == "gbm":  # experiment only (needs scikit-learn at inference)
        from sklearn.ensemble import HistGradientBoostingClassifier
        model = {"features": FEATURES, "sk": {}}
        for f in FIELDS:
            y = np.array([m[3][f] for m in meta])
            model["sk"][f] = (HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                             l2_regularization=1.0, random_state=0).fit(X, y)
                              if y.sum() else None)
        return model
    from sklearn.linear_model import LogisticRegression
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    model = {"features": FEATURES, "mu": mu.tolist(), "sd": sd.tolist(), "fields": {}}
    for f in FIELDS:
        y = np.array([m[3][f] for m in meta])
        if y.sum() == 0:
            model["fields"][f] = {"coef": [0.0] * len(FEATURES), "intercept": -10.0}
            continue
        lr = LogisticRegression(C=C, max_iter=3000).fit(Z, y)
        model["fields"][f] = {"coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0])}
    return model


def field_probs(tagged: list[dict], model: dict) -> dict[str, list[float]]:
    """{field: [prob per token]} for the decoder; 0 for tokens that are not amounts."""
    idx, _, feats = token_features(tagged)
    out = {f: [0.0] * len(tagged) for f in FIELDS}
    if not idx:
        return out
    X = np.array([[ft[k] for k in model["features"]] for ft in feats], dtype=float)
    if "sk" in model:
        for f in FIELDS:
            p = model["sk"][f].predict_proba(X)[:, 1] if model["sk"][f] is not None else np.zeros(len(idx))
            for i, pi in zip(idx, p):
                out[f][i] = float(pi)
        return out
    Z = (X - np.array(model["mu"])) / np.array(model["sd"])
    for f in FIELDS:
        m = model["fields"][f]
        p = 1 / (1 + np.exp(-(Z @ np.array(m["coef"]) + m["intercept"])))
        for i, pi in zip(idx, p):
            out[f][i] = float(pi)
    return out


def decode_ranked(tagged, model, lam=1.5, policy=None):
    from .decision import DEFAULT_POLICY
    from .decode import rerank
    return rerank(tagged, lam=lam, policy=policy or DEFAULT_POLICY, pf=field_probs(tagged, model))


# ---------------------------------------------------------------- evaluation
LAMS = (0.5, 1.0, 1.5, 2.0, 3.0)


def _correct(preds, recs, models_by_fold, lam):
    from .fields import gold_fields
    from .metrics import compare
    from .policy_cv import _temper
    out = {}
    for p in preds:
        t = _temper(p["B"], 1.1)
        pred = decode_ranked(t, models_by_fold[p["fold"]], lam)
        out[p["id"]] = int(compare(pred, gold_fields(recs[p["id"]]["gt_parse"]))["posting_correct"])
    return out


def main():
    from .cv import RES, _records, load_folds, load_preds, paired_bootstrap
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", default="tier1")
    ap.add_argument("--C", type=float, default=1.0)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--kind", default="lr", choices=["lr", "gbm"])
    a = ap.parse_args()
    global KIND
    KIND = a.kind
    recs, preds = _records(), load_preds(a.cv)
    groups, _ = load_folds()
    X, meta = dataset(preds, recs)
    folds = np.array([m[1] for m in meta])
    print(f"{len(meta)} money tokens, {len(FEATURES)} features", flush=True)
    nested, chosen = {}, {}
    for k in range(5):
        outer_tr = folds != k
        inner_models = {}
        for j in range(5):  # inner OOF ranker probabilities for the 4 training folds
            if j == k:
                continue
            m = (folds != k) & (folds != j)
            inner_models[j] = fit(X[m], [x for x, keep in zip(meta, m) if keep], a.C)
        inner_preds = [p for p in preds if p["fold"] != k]
        lam = max(LAMS, key=lambda l: (sum(_correct(inner_preds, recs, inner_models, l).values()), -abs(l - 1.5)))
        chosen[k] = lam
        model_k = fit(X[outer_tr], [x for x, keep in zip(meta, outer_tr) if keep], a.C)
        nested.update(_correct([p for p in preds if p["fold"] == k], recs, {k: model_k}, lam))
        print(f"fold {k}: lam {lam}", flush=True)
    base = json.loads((RES / "tier1_all.json").read_text())["posting"] if (RES / "tier1_all.json").exists() else None
    res = {"cv": a.cv, "C": a.C, "features": FEATURES, "lambda_per_fold": chosen,
           "posting_correct_nested": sum(nested.values()) / len(nested), "per_receipt": nested}
    if base:
        res["vs_tier1"] = paired_bootstrap(base, nested, groups)
        r = res["vs_tier1"]
        print(f"nested posting-correct {res['posting_correct_nested']:.4f} vs {sum(base.values()) / len(base):.4f}: "
              f"{r['delta']:+.4f} CI {r['ci95'][0]:+.4f}..{r['ci95'][1]:+.4f} fixed/broken {r['b_wins']}/{r['b_losses']}")
    (RES / f"ranker_{a.cv}_{a.kind}.json").write_text(json.dumps(res, indent=1))
    if a.write:  # final ranker on all 900 + OOF ranker models (for the receipt-confidence refit)
        oof = {j: fit(X[folds != j], [x for x, keep in zip(meta, folds != j) if keep], a.C) for j in range(5)}
        lam = max(LAMS, key=lambda l: (sum(_correct(preds, recs, oof, l).values()), -abs(l - 1.5)))
        final = fit(X, meta, a.C) | {"lam": lam, "trained_on": f"OOF CRF predictions, cv {a.cv}"}
        (ART / "ranker_crf.json").write_text(json.dumps(final))
        print("final ranker written, lam", lam)


if __name__ == "__main__":
    main()
