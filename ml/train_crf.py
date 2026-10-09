"""Train the Rung-1 CRF. Defaults reproduce the production model (ml/artifacts/crf.pkl):

  python -m ml.train_crf                       # gold + real-OCR words, c1=0.5 c2=0.1 (chosen by ml.tune_crf)
  python -m ml.train_crf --c1 1.0 --c2 0.1 --out ml/artifacts/crf_try.pkl
Reports validation entity F1 (gold words) and appends a row to results/experiments.csv.
"""
from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from seqeval.metrics import f1_score

from .crf_model import FEATURES, CRFTagger, featurise
from .dataset import ROOT, gold_sequence, load_split


def train_sequences(source: str) -> list:
    """[(receipt id, words, W, H)]: CORD gold words and/or real-OCR words with projected labels."""
    seqs = []
    if source in ("gold", "both"):
        seqs += [(r["id"], gold_sequence(r), r["width"], r["height"]) for r in load_split("train")]
    if source in ("ocr", "both"):
        from .project_labels import ocr_train_sequences
        seqs += [(rec["id"], ws, W, H) for rec, ws, W, H in ocr_train_sequences("train")]
    return seqs


def to_xy(seqs):
    return ([featurise(ws, W, H) for _, ws, W, H in seqs], [[w["label"] for w in ws] for _, ws, W, H in seqs])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="both", choices=["gold", "ocr", "both"],
                    help="train on gold words, real-OCR words with projected labels, or both")
    ap.add_argument("--c1", type=float, default=0.5, help="L1 penalty")
    ap.add_argument("--c2", type=float, default=0.1, help="L2 penalty")
    ap.add_argument("--out", default=str(ROOT / "ml" / "artifacts" / "crf.pkl"))
    a = ap.parse_args()
    Xtr, ytr = to_xy(train_sequences(a.source))
    Xva, yva = to_xy([(r["id"], gold_sequence(r), r["width"], r["height"]) for r in load_split("validation")])
    t0 = time.time()
    m = CRFTagger(c1=a.c1, c2=a.c2).fit(Xtr, ytr)
    f1 = f1_score(yva, m.crf.predict(Xva))
    dt = time.time() - t0
    m.save(Path(a.out))
    exp = ROOT / "results" / "experiments.csv"
    new = not exp.exists()
    with open(exp, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "model", "lr", "weight_decay", "batch", "epochs_max", "epochs_run", "best_epoch",
                        "freeze_layers", "max_train", "seed", "val_entity_f1", "train_time_s", "device"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), f"crf[{a.source},{FEATURES}]", f"c1={a.c1}",
                    f"c2={a.c2}", "", "", "", "", "", "", 0, round(f1, 4), round(dt), "cpu"])
    print(f"c1={a.c1} c2={a.c2} val_entity_f1={f1:.4f} ({dt:.0f}s) -> {a.out}")


if __name__ == "__main__":
    main()
