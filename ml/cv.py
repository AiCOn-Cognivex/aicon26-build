"""Group-aware 5-fold cross-validation over train + validation (900 receipts): the tuning harness.

  python -m ml.cv --name base                     # production CRF settings -> results/cv_base.json
  python -m ml.cv --name f3 --features v3 --c1 0.5 --c2 0.1
  python -m ml.cv --compare base f3               # paired cluster bootstrap on posting-correct (Mode B)

Why: 100 validation receipts give +-1 point per receipt, and selecting on them overfits. Every receipt in
train+validation gets an out-of-fold (OOF) prediction from a CRF that never saw it or any receipt of its
group. Groups = exact duplicate word sequences + near-duplicate templates (Jaccard >= 0.5 on distinctive
words, i.e. words on <= 3% of receipts), so templated receipts never straddle folds. The test split is
never loaded here.
Each fold trains on gold words + real-OCR words with projected labels (as production, D9) of its training
receipts and predicts the held-out receipts in Mode A (gold words) and Mode B (cached real OCR).
OOF predictions (labels + marginals) are cached in data/cache/cv/<name>.pkl so decoding and decision
policies can be tuned without retraining. Every run is appended to results/tuning_cv.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import random
import re
import time
from collections import Counter
from datetime import datetime
from multiprocessing import Pool

from .dataset import ROOT, gold_sequence, load_split
from .fields import assemble, gold_fields
from .metrics import aggregate, compare
from .ocr import normalise_words
from .ocr_cache import load_cache

K = 5
SPLITS = ("train", "validation")
CV_DIR = ROOT / "data" / "cache" / "cv"
RES = ROOT / "results"
GROUPS_FILE = RES / "cv_groups.json"


# ---------------------------------------------------------------- groups and folds
def _distinctive(recs):
    toks = [{w["text"].lower().strip(".,:") for w in r["words"] if re.search(r"[a-z]{2,}", w["text"].lower())}
            for r in recs]
    df = Counter(t for s in toks for t in s)
    common = {t for t, c in df.items() if c > 0.03 * len(recs)}
    return [s - common for s in toks]


def build_groups(threshold: float = 0.5) -> dict[str, int]:
    """receipt id -> group id (union-find over exact and near-duplicate receipts)."""
    recs = [r for s in SPLITS for r in load_split(s)]
    par = list(range(len(recs)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    sig = {}
    for i, r in enumerate(recs):
        h = hashlib.md5(" ".join(w["text"] for w in r["words"]).encode()).hexdigest()
        if h in sig:
            par[find(i)] = find(sig[h])
        sig.setdefault(h, i)
    T = _distinctive(recs)
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            a, b = T[i], T[j]
            if len(a) >= 2 and len(b) >= 2 and len(a & b) / len(a | b) >= threshold:
                par[find(i)] = find(j)
    roots = {}
    return {r["id"]: roots.setdefault(find(i), len(roots)) for i, r in enumerate(recs)}


def assign_folds(groups: dict[str, int], k: int = K, seed: int = 0) -> dict[str, int]:
    """Largest groups first, each to the currently smallest fold (ties broken by a seeded shuffle)."""
    members: dict[int, list[str]] = {}
    for rid, g in groups.items():
        members.setdefault(g, []).append(rid)
    order = list(members)
    random.Random(seed).shuffle(order)
    order.sort(key=lambda g: -len(members[g]))
    sizes, fold = [0] * k, {}
    for g in order:
        f = min(range(k), key=lambda i: (sizes[i], i))
        for rid in members[g]:
            fold[rid] = f
        sizes[f] += len(members[g])
    return fold


def load_folds() -> tuple[dict[str, int], dict[str, int]]:
    if not GROUPS_FILE.exists():
        groups = build_groups()
        folds = assign_folds(groups)
        sizes = Counter(groups.values())
        GROUPS_FILE.write_text(json.dumps({
            "method": "union-find: identical word sequences + Jaccard >= 0.5 on distinctive words (on <= 3% of "
                      "receipts); groups assigned to 5 folds largest-first, seed 0. Train + validation only.",
            "n_receipts": len(groups), "n_groups": len(sizes),
            "n_receipts_in_multi_groups": sum(v for v in sizes.values() if v > 1),
            "largest_groups": sorted(sizes.values(), reverse=True)[:10],
            "fold_sizes": [sum(1 for f in folds.values() if f == i) for i in range(K)],
            "groups": groups, "folds": folds}, indent=0))
    d = json.loads(GROUPS_FILE.read_text())
    return d["groups"], d["folds"]


# ---------------------------------------------------------------- data
def ocr_sequence(rec: dict, c: dict) -> list[dict]:
    """Real-OCR words of one receipt with labels projected from gold (training data only)."""
    from .project_labels import project
    sx, sy = c["width"] / rec["width"], c["height"] / rec["height"]
    scaled = dict(rec, words=[dict(g, box=[g["box"][0] * sx, g["box"][1] * sy, g["box"][2] * sx, g["box"][3] * sy])
                              for g in rec["words"]])
    return project(scaled, c["words"])


def _records():
    return {r["id"]: r for s in SPLITS for r in load_split(s)}


def _caches(extra: list[str]):
    """Mode B cache per split (+ optional extra OCR caches of augmented TRAINING copies)."""
    main = {}
    for s in SPLITS:
        main.update(load_cache(s))
    aug = []
    for path in extra:
        with open(path, encoding="utf-8") as f:
            aug.append({r["id"]: r for r in map(json.loads, f)})
    return main, aug


# ---------------------------------------------------------------- one fold
def _slim(tagged):
    return [{"text": w["text"], "box": w["box"], "label": w["label"], "prob": w["prob"],
             "ocr_conf": w.get("ocr_conf", 1.0), "line_no": w.get("line_no"),
             "probs": {k: round(v, 6) for k, v in w["probs"].items() if v >= 1e-5}} for w in tagged]


def run_fold(job):
    cfg, k, folds = job
    from .crf_model import CRFTagger, featurise
    recs = _records()
    cache, aug = _caches(cfg.get("aug", []))
    feats = cfg.get("features", "v2")
    X, y = [], []
    for rid, r in recs.items():
        if folds[rid] == k:
            continue
        seqs = []
        if cfg.get("source", "both") in ("gold", "both"):
            seqs.append((gold_sequence(r), r["width"], r["height"]))
        if cfg.get("source", "both") in ("ocr", "both"):
            c = cache[rid]
            seqs.append((ocr_sequence(r, c), c["width"], c["height"]))
        for a in aug:  # augmented copies belong to the training fold of their source receipt only
            if rid in a:
                seqs.append((ocr_sequence(r, a[rid]), a[rid]["width"], a[rid]["height"]))
        for ws, W, H in seqs:
            X.append(featurise(ws, W, H, features=feats))
            y.append([w["label"] for w in ws])
    t0 = time.time()
    m = CRFTagger(c1=cfg["c1"], c2=cfg["c2"], max_iter=cfg.get("max_iter", 200),
                  algorithm=cfg.get("algorithm", "lbfgs"), features=feats).fit(X, y)
    fit_s = time.time() - t0
    out = []
    for rid, r in recs.items():
        if folds[rid] != k:
            continue
        c = cache[rid]
        tb = m.tag(normalise_words(c["words"]), c["width"], c["height"])
        ta = m.tag([{"text": w["text"], "box": w["box"]} for w in r["words"]], r["width"], r["height"])
        gmap = {(w["text"], tuple(round(v, 1) for v in w["box"])): w["label"] for w in gold_sequence(r)}
        out.append({"id": rid, "fold": k, "B": _slim(tb), "A": _slim(ta),
                    "A_gold": [gmap.get((w["text"], tuple(round(v, 1) for v in w["box"])), "O") for w in ta]})
    return {"fold": k, "fit_s": fit_s, "n_train_seqs": len(X), "preds": out}


# ---------------------------------------------------------------- scoring
def score(preds: list[dict], decode=None, mode: str = "B") -> dict:
    """OOF metrics overall, per fold (mean +- std) and on the official validation subset.
    decode(tagged) -> assembled prediction (default: production assemble)."""
    import statistics as st
    recs = _records()
    decode = decode or assemble
    rows = []
    for p in preds:
        pred = decode(p[mode])
        comp = compare(pred, gold_fields(recs[p["id"]]["gt_parse"]))
        rows.append((p, pred, comp))
    allc = [c for _, _, c in rows]
    out = {"n": len(allc), "oof": aggregate(allc)}
    per = []
    for k in range(K):
        ck = [c for p, _, c in rows if p["fold"] == k]
        if ck:
            per.append(aggregate(ck))
    for key in ("posting_correct_rate", "fully_correct_rate", "line_item_f1", "line_item_f1_lenient",
                "key_field_exact_match"):
        vals = [a[key] for a in per]
        out[f"{key}_fold_mean"] = st.mean(vals)
        out[f"{key}_fold_std"] = st.stdev(vals) if len(vals) > 1 else 0.0
    val = [c for p, _, c in rows if p["id"].startswith("validation_")]
    out["validation_subset"] = {k: v for k, v in aggregate(val).items()
                                if k in ("n_receipts", "posting_correct_rate", "fully_correct_rate",
                                         "line_item_f1", "line_item_f1_lenient")}
    out["per_receipt"] = {p["id"]: int(c["posting_correct"]) for p, _, c in rows}
    return out


def token_f1(preds) -> float:
    from seqeval.metrics import f1_score
    return f1_score([p["A_gold"] for p in preds], [[w["label"] for w in p["A"]] for p in preds])


def load_preds(name: str) -> list[dict]:
    with open(CV_DIR / f"{name}.pkl", "rb") as f:
        return pickle.load(f)


# ---------------------------------------------------------------- paired comparison
def paired_bootstrap(a: dict[str, int], b: dict[str, int], groups: dict[str, int], n: int = 10000,
                     seed: int = 0) -> dict:
    """Cluster (group) bootstrap of the difference b - a in a per-receipt 0/1 metric."""
    ids = sorted(set(a) & set(b))
    by_g: dict[int, list[str]] = {}
    for i in ids:
        by_g.setdefault(groups[i], []).append(i)
    gl = list(by_g.values())
    diff = [[b[i] - a[i] for i in g] for g in gl]
    gsum, gcnt = [sum(d) for d in diff], [len(d) for d in diff]
    rng = random.Random(seed)
    deltas = []
    for _ in range(n):
        s = c = 0
        for _ in gl:
            j = rng.randrange(len(gl))
            s += gsum[j]
            c += gcnt[j]
        deltas.append(s / c)
    deltas.sort()
    obs = sum(gsum) / sum(gcnt)
    wins = sum(1 for i in ids if b[i] > a[i])
    losses = sum(1 for i in ids if b[i] < a[i])
    return {"n": len(ids), "delta": obs, "ci95": [deltas[int(0.025 * n)], deltas[int(0.975 * n) - 1]],
            "p_not_better": sum(1 for d in deltas if d <= 0) / n, "b_wins": wins, "b_losses": losses}


def log_trial(entry: dict, path=RES / "tuning_cv.json"):
    rows = json.loads(path.read_text()) if path.exists() else []
    rows.append(entry)
    path.write_text(json.dumps(rows, indent=1))


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--features", default="v2")
    ap.add_argument("--c1", type=float, default=0.5)
    ap.add_argument("--c2", type=float, default=0.1)
    ap.add_argument("--max-iter", type=int, default=200)
    ap.add_argument("--algorithm", default="lbfgs")
    ap.add_argument("--source", default="both", choices=["gold", "ocr", "both"])
    ap.add_argument("--aug", nargs="*", default=[], help="extra OCR caches of augmented train/val images")
    ap.add_argument("--note", default="")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    a = ap.parse_args()
    groups, folds = load_folds()
    if a.compare:
        ra, rb = (json.loads((RES / f"cv_{n}.json").read_text()) for n in a.compare)
        res = paired_bootstrap(ra["per_receipt"], rb["per_receipt"], groups)
        print(json.dumps(res, indent=1))
        return
    cfg = {"features": a.features, "c1": a.c1, "c2": a.c2, "max_iter": a.max_iter, "algorithm": a.algorithm,
           "source": a.source, "aug": a.aug}
    t0 = time.time()
    with Pool(K) as pool:
        outs = pool.map(run_fold, [(cfg, k, folds) for k in range(K)])
    preds = [p for o in sorted(outs, key=lambda o: o["fold"]) for p in o["preds"]]
    CV_DIR.mkdir(parents=True, exist_ok=True)
    with open(CV_DIR / f"{a.name}.pkl", "wb") as f:
        pickle.dump(preds, f)
    sB, sA = score(preds, mode="B"), score(preds, mode="A")
    summary = {"name": a.name, "config": cfg, "note": a.note, "time": datetime.now().isoformat(timespec="seconds"),
               "wall_s": round(time.time() - t0), "fit_s": [round(o["fit_s"]) for o in outs],
               "token_f1_modeA": token_f1(preds),
               "modeB": {k: v for k, v in sB.items() if k != "per_receipt"},
               "modeA": {k: v for k, v in sA.items() if k != "per_receipt"},
               "per_receipt": sB["per_receipt"]}
    (RES / f"cv_{a.name}.json").write_text(json.dumps(summary, indent=1))
    log_trial({k: v for k, v in summary.items() if k != "per_receipt"})
    b = summary["modeB"]
    print(f"{a.name}: Mode B OOF posting-correct {b['oof']['posting_correct_rate']:.3f} "
          f"(fold mean {b['posting_correct_rate_fold_mean']:.3f} +- {b['posting_correct_rate_fold_std']:.3f}), "
          f"fully {b['oof']['fully_correct_rate']:.3f}, items F1 {b['oof']['line_item_f1']:.3f}/"
          f"{b['oof']['line_item_f1_lenient']:.3f}, val subset {b['validation_subset']['posting_correct_rate']:.2f}; "
          f"Mode A {summary['modeA']['oof']['posting_correct_rate']:.3f}, token F1 {summary['token_f1_modeA']:.3f} "
          f"({summary['wall_s']}s)")


if __name__ == "__main__":
    main()
