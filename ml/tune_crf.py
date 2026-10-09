"""Over/underfitting diagnosis and regularisation tuning for the CRF, using 4-fold CV on TRAIN only.

  python -m ml.tune_crf            # grid search + learning curve, writes results/crf_tuning.json
Folds are split by receipt, so the gold-word and OCR-word copies of one receipt never sit on both
sides. For every (c1, c2) we record train and held-out entity F1 and token NLL ("loss"):
a large train/held-out gap = overfitting (raise regularisation), both poor = underfitting.
Validation is not used here; it is only used afterwards to confirm the chosen setting.
"""
from __future__ import annotations

import json
import math
import pickle
import random
import time
from itertools import product
from multiprocessing import Pool
from pathlib import Path

from .dataset import ROOT, gold_sequence, load_split

C1 = [0.1, 0.5, 1.0, 2.0]
C2 = [0.01, 0.1, 0.5, 1.0]
K = 4
DATA = ROOT / "data" / "cache" / "_crf_tune_features.pkl"
_D = None


def _load():
    global _D
    with open(DATA, "rb") as f:
        _D = pickle.load(f)


def _nll(crf, X, y):
    marg = crf.predict_marginals(X)
    n = sum(len(s) for s in y)
    return -sum(math.log(max(m.get(g, 0.0), 1e-12)) for ms, gs in zip(marg, y) for m, g in zip(ms, gs)) / n


def _fit_eval(job):
    import sklearn_crfsuite
    from seqeval.metrics import f1_score
    c1, c2, fold, frac = job
    recs = _D["recs"]
    test_ids = {r for i, r in enumerate(recs) if i % K == fold} if fold >= 0 else set()
    train_ids = [r for r in recs if r not in test_ids]
    if frac < 1.0:
        train_ids = random.Random(0).sample(train_ids, int(frac * len(train_ids)))
    train_ids = set(train_ids)
    Xtr = [x for rid, x in _D["X"] if rid in train_ids]
    ytr = [y for rid, y in _D["y"] if rid in train_ids]
    t0 = time.time()
    crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=c1, c2=c2, max_iterations=200, all_possible_transitions=True)
    crf.fit(Xtr, ytr)
    out = {"c1": c1, "c2": c2, "fold": fold, "frac": frac, "fit_s": round(time.time() - t0, 1),
           "train_f1": f1_score(ytr, crf.predict(Xtr)), "train_nll": _nll(crf, Xtr, ytr)}
    for kind in ("gold", "ocr"):
        Xh = [x for (rid, k), x in zip(_D["meta"], [x for _, x in _D["X"]]) if rid in test_ids and k == kind]
        yh = [y for (rid, k), y in zip(_D["meta"], [y for _, y in _D["y"]]) if rid in test_ids and k == kind]
        if fold < 0:  # learning-curve mode: score on validation gold words
            Xh, yh = _D["Xval"], _D["yval"]
        if Xh:
            out[f"heldout_{kind}_f1"] = f1_score(yh, crf.predict(Xh))
            out[f"heldout_{kind}_nll"] = _nll(crf, Xh, yh)
    return out


def build_features(version="v2"):
    from .crf_model import featurise as _f

    def featurise(ws, W, H):
        return _f(ws, W, H, version)
    from .project_labels import ocr_train_sequences
    X, y, meta = [], [], []
    for r in load_split("train"):
        ws = gold_sequence(r)
        X.append((r["id"], featurise(ws, r["width"], r["height"])))
        y.append((r["id"], [w["label"] for w in ws]))
        meta.append((r["id"], "gold"))
    for rec, ws, W, H in ocr_train_sequences("train"):
        X.append((rec["id"], featurise(ws, W, H)))
        y.append((rec["id"], [w["label"] for w in ws]))
        meta.append((rec["id"], "ocr"))
    val = [(featurise(gold_sequence(r), r["width"], r["height"]), [w["label"] for w in gold_sequence(r)])
           for r in load_split("validation")]
    recs = [r["id"] for r in load_split("train")]
    random.Random(42).shuffle(recs)
    with open(DATA, "wb") as f:
        pickle.dump({"X": X, "y": y, "meta": meta, "recs": recs,
                     "Xval": [v[0] for v in val], "yval": [v[1] for v in val]}, f)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="v2", choices=["v1", "v2"])
    ap.add_argument("--grid", default="", help='e.g. "0.5:0.5,0.1:0.1" (default: full C1 x C2 grid)')
    ap.add_argument("--no-curve", action="store_true")
    a = ap.parse_args()
    build_features(a.features)
    settings = [tuple(map(float, g.split(":"))) for g in a.grid.split(",")] if a.grid else list(product(C1, C2))
    jobs = [(c1, c2, k, 1.0) for c1, c2 in settings for k in range(K)]
    t0 = time.time()
    with Pool(4, initializer=_load) as pool:
        rows = pool.map(_fit_eval, jobs)
    grid = []
    for c1, c2 in settings:
        rs = [r for r in rows if r["c1"] == c1 and r["c2"] == c2]
        agg = {k: sum(r[k] for r in rs) / len(rs) for k in rs[0] if k not in ("c1", "c2", "fold", "frac")}
        agg["heldout_f1"] = (agg["heldout_gold_f1"] + agg["heldout_ocr_f1"]) / 2
        agg["gap_f1"] = agg["train_f1"] - agg["heldout_f1"]
        grid.append({"c1": c1, "c2": c2, **agg})
        print(f"c1={c1:<4} c2={c2:<5} train F1 {agg['train_f1']:.3f} loss {agg['train_nll']:.3f} | "
              f"held-out F1 gold {agg['heldout_gold_f1']:.3f} ocr {agg['heldout_ocr_f1']:.3f} "
              f"loss gold {agg['heldout_gold_nll']:.3f} | gap {agg['gap_f1']:.3f}", flush=True)
    best = max(grid, key=lambda g: g["heldout_f1"])
    print(f"best by CV held-out F1: c1={best['c1']} c2={best['c2']} ({time.time() - t0:.0f}s)")
    out_path = ROOT / "results" / f"crf_tuning_{a.features}{'_' + a.grid.replace(':', '-').replace(',', '_') if a.grid else ''}.json"
    if a.no_curve:
        out_path.write_text(json.dumps({"method": f"{K}-fold CV on train, split by receipt; gold+OCR words",
                                        "features": a.features, "grid": grid}, indent=1))
        Path(DATA).unlink(missing_ok=True)
        return
    # learning curve with the chosen setting, scored on validation gold words
    lc_jobs = [(best["c1"], best["c2"], -1, f) for f in (0.125, 0.25, 0.5, 1.0)]
    with Pool(4, initializer=_load) as pool:
        lc = pool.map(_fit_eval, lc_jobs)
    for r in lc:
        print(f"learning curve: {int(r['frac'] * 800)} receipts -> train F1 {r['train_f1']:.3f}, "
              f"val F1 {r['heldout_gold_f1']:.3f}, val loss {r['heldout_gold_nll']:.3f}")
    out = {"method": f"{K}-fold CV on train, split by receipt; gold+OCR words", "features": a.features, "grid": grid,
           "best": {"c1": best["c1"], "c2": best["c2"]},
           "learning_curve": [{"train_receipts": int(r["frac"] * 800), "train_f1": r["train_f1"],
                               "val_f1": r["heldout_gold_f1"], "val_nll": r["heldout_gold_nll"]} for r in lc]}
    out_path.write_text(json.dumps(out, indent=1))
    Path(DATA).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
