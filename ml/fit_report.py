"""Over/underfitting report for a saved CRF: train vs validation entity F1 and token NLL (loss).

  python -m ml.fit_report --model ml/artifacts/crf.pkl --name after
Appends/overwrites entry <name> in results/fit_report_crf.json.
"""
from __future__ import annotations

import argparse
import json
import math

from seqeval.metrics import f1_score

from .crf_model import CRFTagger, featurise
from .dataset import ROOT, gold_sequence, load_split
from .project_labels import ocr_train_sequences


def _stats(crf, X, y):
    pred = crf.predict(X)
    marg = crf.predict_marginals(X)
    n = sum(len(s) for s in y)
    nll = -sum(math.log(max(m.get(g, 0.0), 1e-12)) for ms, gs in zip(marg, y) for m, g in zip(ms, gs)) / n
    return {"entity_f1": f1_score(y, pred), "token_nll": nll}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "ml" / "artifacts" / "crf.pkl"))
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    t = CRFTagger.load(a.model)
    v = t.features
    gold = [(featurise(gold_sequence(r), r["width"], r["height"], v), [w["label"] for w in gold_sequence(r)])
            for r in load_split("train")]
    ocr = [(featurise(ws, W, H, v), [w["label"] for w in ws]) for _, ws, W, H in ocr_train_sequences("train")]
    val = [(featurise(gold_sequence(r), r["width"], r["height"], v), [w["label"] for w in gold_sequence(r)])
           for r in load_split("validation")]
    rep = {"model": a.model.replace("\\", "/").split("aicon26-build/")[-1], "features": v,
           "c1": t.crf.c1, "c2": t.crf.c2, "n_state_features": len(t.crf.state_features_),
           "train_gold": _stats(t.crf, *zip(*gold)), "train_ocr": _stats(t.crf, *zip(*ocr)),
           "validation_gold": _stats(t.crf, *zip(*val))}
    rep["f1_gap_train_minus_val"] = rep["train_gold"]["entity_f1"] - rep["validation_gold"]["entity_f1"]
    rep["loss_ratio_val_over_train"] = rep["validation_gold"]["token_nll"] / rep["train_gold"]["token_nll"]
    path = ROOT / "results" / "fit_report_crf.json"
    allr = json.loads(path.read_text()) if path.exists() else {}
    allr[a.name] = rep
    path.write_text(json.dumps(allr, indent=1))
    print(json.dumps({a.name: rep}, indent=1))


if __name__ == "__main__":
    main()
