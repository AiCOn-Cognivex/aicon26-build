"""Robustness to amount values: does the model still work when every amount on a receipt is scaled?

  python -m ml.robustness --model crf --name after_aug
Validation, gold OCR words (Mode A). For each held-out factor in ml/augment.TEST_FACTORS (never used
for training) every amount on a receipt is multiplied by the factor, gold amounts likewise; receipts
where the factor would create fractions are skipped (n is reported). Writes results/robustness_<model>.json.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal

from seqeval.metrics import classification_report, f1_score

from . import taggers
from .augment import TEST_FACTORS, scale_words
from .dataset import ROOT, gold_sequence, load_split
from .fields import assemble, gold_fields
from .metrics import compare
from .money import parse_money, to_float


def _scaled_gold(gold: dict, factor: Decimal) -> dict:
    out = {"fields": {}, "line_items": []}
    for k, v in gold["fields"].items():
        if v is None:
            out["fields"][k] = None
        else:
            val = abs(parse_money(v["text"])) * factor if abs(parse_money(v["text"])) >= 100 else abs(parse_money(v["text"]))
            out["fields"][k] = {"text": str(val), "value": to_float(val)}
    return out


def _score(fn, recs_words, factor):
    yt, yp, posting = [], [], 0
    for r, gs, ws in recs_words:
        tagged = fn([{"text": w["text"], "box": w["box"]} for w in ws], r["width"], r["height"])
        key = lambda w: tuple(round(v, 1) for v in w["box"])
        gmap = {key(w): w["label"] for w in gs}
        yt.append([gmap.get(key(w), "O") for w in tagged])
        yp.append([w["label"] for w in tagged])
        gold = gold_fields(r["gt_parse"])
        gold = gold if factor == 1 else _scaled_gold(gold, factor)
        posting += compare(assemble(tagged), gold)["posting_correct"]
    rep = classification_report(yt, yp, output_dict=True, zero_division=0)
    return {"entity_f1": f1_score(yt, yp), "posting_correct_rate": posting / len(recs_words),
            "total_f1": rep.get("total.total_price", {}).get("f1-score")}


def run(model: str) -> dict:
    """Paired comparison: for each held-out factor, scaled vs unscaled on the SAME receipts."""
    name, rung, fn = taggers.load(model)
    res = {"model": name, "factors": {}}
    recs = [(r, gold_sequence(r)) for r in load_split("validation")]
    for factor in TEST_FACTORS:
        pairs = [(r, gs, scale_words(gs, factor)) for r, gs in recs]
        pairs = [(r, gs, ws) for r, gs, ws in pairs if ws is not None]
        orig = _score(fn, [(r, gs, gs) for r, gs, _ in pairs], Decimal(1))
        scal = _score(fn, pairs, factor)
        res["factors"][str(factor)] = {"n_receipts": len(pairs), "original": orig, "scaled": scal,
                                       "drop_entity_f1": orig["entity_f1"] - scal["entity_f1"],
                                       "drop_posting_correct": orig["posting_correct_rate"] - scal["posting_correct_rate"]}
    fs = res["factors"].values()
    res["mean_drop_entity_f1"] = sum(v["drop_entity_f1"] for v in fs) / len(fs)
    res["mean_drop_posting_correct"] = sum(v["drop_posting_correct"] for v in fs) / len(fs)
    res["mean_scaled_posting_correct"] = sum(v["scaled"]["posting_correct_rate"] for v in fs) / len(fs)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="crf")
    ap.add_argument("--name", required=True)
    a = ap.parse_args()
    res = run(a.model)
    path = ROOT / "results" / f"robustness_{a.model}.json"
    allr = json.loads(path.read_text()) if path.exists() else {}
    allr[a.name] = res
    path.write_text(json.dumps(allr, indent=1))
    for k, v in res["factors"].items():
        o, sc = v["original"], v["scaled"]
        print(f"x{k:<5} n={v['n_receipts']:3d} entity F1 {o['entity_f1']:.4f} -> {sc['entity_f1']:.4f} | "
              f"posting-correct {o['posting_correct_rate']:.3f} -> {sc['posting_correct_rate']:.3f} | "
              f"total F1 {o['total_f1']:.3f} -> {sc['total_f1']:.3f}")
    print(f"mean drop under scaling: entity F1 {res['mean_drop_entity_f1']:.4f}, posting-correct {res['mean_drop_posting_correct']:.3f}")


if __name__ == "__main__":
    main()
