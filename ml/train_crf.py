"""Train the Rung-1 CRF on train (gold words), pick c1/c2 on validation entity F1.

  python -m ml.train_crf
Saves ml/artifacts/crf.pkl and appends to results/experiments.csv.
"""
from __future__ import annotations

import csv
import time
from datetime import datetime

from seqeval.metrics import f1_score

from .crf_model import CRFTagger, featurise
from .dataset import ROOT, gold_sequence, load_split

GRID = [(0.05, 0.05), (0.1, 0.01), (0.5, 0.05)]


FEATURES = "v2"


def train_sequences(source: str, augment: int = 0) -> list:
    """[(receipt id, words, W, H)] for training; optional amount-scaling copies (ml/augment.py)."""
    seqs = []
    if source in ("gold", "both"):
        seqs += [(r["id"], gold_sequence(r), r["width"], r["height"]) for r in load_split("train")]
    if source in ("ocr", "both"):
        from .project_labels import ocr_train_sequences
        seqs += [(rec["id"], ws, W, H) for rec, ws, W, H in ocr_train_sequences("train")]
    if augment:
        from .augment import augment_sequences
        seqs += augment_sequences(seqs, augment)
    return seqs


def to_xy(seqs):
    return ([featurise(ws, W, H, FEATURES) for _, ws, W, H in seqs],
            [[w["label"] for w in ws] for _, ws, W, H in seqs])


def xy(split):
    X, y = [], []
    for r in load_split(split):
        ws = gold_sequence(r)
        X.append(featurise(ws, r["width"], r["height"], FEATURES))
        y.append([w["label"] for w in ws])
    return X, y


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="gold", choices=["gold", "ocr", "both"],
                    help="train on gold words, real-OCR words with projected labels, or both")
    ap.add_argument("--out", default=str(ROOT / "ml" / "artifacts" / "crf.pkl"))
    ap.add_argument("--features", default="v2", choices=["v1", "v2"])
    ap.add_argument("--augment", type=int, default=0, help="amount-scaling copies per training sequence")
    ap.add_argument("--c1", type=float, default=None, help="with --c2: train one setting (e.g. from ml.tune_crf)")
    ap.add_argument("--c2", type=float, default=None)
    a = ap.parse_args()
    global FEATURES
    FEATURES = a.features
    grid = [(a.c1, a.c2)] if a.c1 is not None and a.c2 is not None else GRID
    Xtr, ytr = to_xy(train_sequences(a.source, a.augment))
    Xva, yva = xy("validation")
    best = None
    rows = []
    for c1, c2 in grid:
        t0 = time.time()
        m = CRFTagger(c1=c1, c2=c2, features=a.features).fit(Xtr, ytr)
        f1 = f1_score(yva, m.crf.predict(Xva))
        dt = time.time() - t0
        print(f"c1={c1} c2={c2} val_entity_f1={f1:.4f} ({dt:.0f}s)")
        rows.append([datetime.now().isoformat(timespec="seconds"), f"crf[{a.source},{a.features}" + (f",scale{a.augment}" if a.augment else "") + "]", f"c1={c1}", f"c2={c2}", "", "", "", "",
                     "", "", 0, round(f1, 4), round(dt), "cpu"])
        if best is None or f1 > best[0]:
            best = (f1, c1, c2, m)
    from pathlib import Path
    best[3].save(Path(a.out))
    exp = ROOT / "results" / "experiments.csv"
    new = not exp.exists()
    with open(exp, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "model", "lr", "weight_decay", "batch", "epochs_max", "epochs_run", "best_epoch",
                        "freeze_layers", "max_train", "seed", "val_entity_f1", "train_time_s", "device"])
        w.writerows(rows)
    print(f"best c1={best[1]} c2={best[2]} val_entity_f1={best[0]:.4f} -> {a.out}")


if __name__ == "__main__":
    main()
