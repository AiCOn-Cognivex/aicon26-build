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


def xy(split):
    X, y = [], []
    for r in load_split(split):
        ws = gold_sequence(r)
        X.append(featurise(ws, r["width"], r["height"]))
        y.append([w["label"] for w in ws])
    return X, y


def xy_ocr():
    from .project_labels import ocr_train_sequences
    X, y = [], []
    for rec, ws, W, H in ocr_train_sequences("train"):
        X.append(featurise(ws, W, H))
        y.append([w["label"] for w in ws])
    return X, y


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="gold", choices=["gold", "ocr", "both"],
                    help="train on gold words, real-OCR words with projected labels, or both")
    ap.add_argument("--out", default=str(ROOT / "ml" / "artifacts" / "crf.pkl"))
    a = ap.parse_args()
    Xtr, ytr = xy("train") if a.source != "ocr" else ([], [])
    if a.source != "gold":
        Xo, yo = xy_ocr()
        Xtr, ytr = Xtr + Xo, ytr + yo
    Xva, yva = xy("validation")
    best = None
    rows = []
    for c1, c2 in GRID:
        t0 = time.time()
        m = CRFTagger(c1=c1, c2=c2).fit(Xtr, ytr)
        f1 = f1_score(yva, m.crf.predict(Xva))
        dt = time.time() - t0
        print(f"c1={c1} c2={c2} val_entity_f1={f1:.4f} ({dt:.0f}s)")
        rows.append([datetime.now().isoformat(timespec="seconds"), f"crf[{a.source}]", f"c1={c1}", f"c2={c2}", "", "", "", "",
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
