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


def train_sequences(source: str, with_validation: bool = False) -> list:
    """[(receipt id, words, W, H)]: CORD gold words and/or real-OCR words with projected labels.
    with_validation: also train on the validation split (final model, D22); validation is then in-sample."""
    seqs = []
    splits = ["train", "validation"] if with_validation else ["train"]
    if source in ("gold", "both"):
        seqs += [(r["id"], gold_sequence(r), r["width"], r["height"]) for s in splits for r in load_split(s)]
    if source in ("ocr", "both"):
        from .project_labels import ocr_train_sequences
        seqs += [(rec["id"], ws, W, H) for rec, ws, W, H in ocr_train_sequences("train")]
        if with_validation:
            from .cv import ocr_sequence
            from .ocr_cache import load_cache
            cache = load_cache("validation")
            seqs += [(r["id"], ocr_sequence(r, cache[r["id"]]), cache[r["id"]]["width"], cache[r["id"]]["height"])
                     for r in load_split("validation")]
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
    ap.add_argument("--with-validation", action="store_true", help="train on train + validation (final model)")
    a = ap.parse_args()
    from . import crf_model, layout, ocr
    layout.DESKEW = False  # deskew is an inference-time step (D22); training data keeps the plain grouping
    crf_model.EXTRA_KEYWORDS = ocr.SPLIT_MERGED = False  # Tier 1 inference-time steps (D25)
    Xtr, ytr = to_xy(train_sequences(a.source, a.with_validation))
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
        w.writerow([datetime.now().isoformat(timespec="seconds"),
                    f"crf[{a.source},{FEATURES}{',+val' if a.with_validation else ''}]", f"c1={a.c1}",
                    f"c2={a.c2}", "", "", "", "", "", "", 0, round(f1, 4), round(dt), "cpu"])
    print(f"c1={a.c1} c2={a.c2} val_entity_f1={f1:.4f}{' (IN-SAMPLE: trained on validation)' if a.with_validation else ''}"
          f" ({dt:.0f}s) -> {a.out}")


if __name__ == "__main__":
    main()
