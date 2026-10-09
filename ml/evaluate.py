"""Evaluate one rung on one split in one mode. Definitions: see ml/metrics.py.

Mode A = gold OCR (CORD's own words + boxes, labels hidden): isolates the extractor.
Mode B = real OCR (cached engine output on the image): the true end-to-end number.

  python -m ml.evaluate --model rules --split validation --mode A
  python -m ml.evaluate --model crf --split validation --mode B
The test split refuses to run without --final (evaluated exactly once, after freezing everything).
Writes results/eval_{model}_{split}_mode{A|B}.json and results/details/... (per receipt).
"""
from __future__ import annotations

import argparse
import json
import time

from .dataset import ROOT, gold_sequence, load_split
from .decision import decide, receipt_confidence
from .fields import assemble, gold_fields
from .metrics import aggregate, compare, stp_metrics
from .ocr import ENGINE, normalise_words
from .ocr_cache import load_cache
from . import taggers

RES = ROOT / "results"


def run(model: str, split: str, mode: str, policy: dict | None = None,
        tagger=None) -> dict:
    from .predict import policy_for
    pol = policy or policy_for(model)
    name, rung, fn = tagger or taggers.load(model)
    recs = load_split(split)
    cache = load_cache(split) if mode == "B" else None
    comps, decisions, details, lat = [], [], [], []
    y_true, y_pred = [], []
    for r in recs:
        if mode == "A":
            words = [{"text": w["text"], "box": w["box"]} for w in r["words"]]
            W, H = r["width"], r["height"]
        else:
            c = cache[r["id"]]
            words, W, H = normalise_words(c["words"]), c["width"], c["height"]
        t0 = time.perf_counter()
        tagged = fn(words, W, H)
        lat.append(time.perf_counter() - t0)
        pred = assemble(tagged)
        gold = gold_fields(r["gt_parse"])
        comp = compare(pred, gold)
        d = decide(pred["fields"], pred["line_items"], pol, pred.get("absent_confidence"))
        comps.append(comp)
        decisions.append(d["decision"])
        if mode == "A":  # token-level alignment exists only with gold words
            gs = gold_sequence(r)
            key = lambda w: (w["text"], tuple(round(v, 1) for v in w["box"]))
            gmap = {key(w): w["label"] for w in gs}
            y_true.append([gmap.get(key(w), "O") for w in tagged])
            y_pred.append([w["label"] for w in tagged])
        details.append({"id": r["id"], "posting_correct": comp["posting_correct"], "fully_correct": comp["fully_correct"],
                        "fields_ok": comp["fields"], "decision": d["decision"], "reasons": d["reasons"],
                        "recon": d["reconciliation"]["status"], "conf": receipt_confidence(pred["fields"]),
                        "pred": {k: (v["text"] if v else None) for k, v in pred["fields"].items()},
                        "gold": {k: (v["text"] if v else None) for k, v in gold["fields"].items()},
                        "items_tp": comp["items_tp"], "items_pred": comp["items_pred"], "items_gold": comp["items_gold"]})
    out = {"model": name, "rung": rung, "split": split, "mode": mode, "ocr": "gold" if mode == "A" else ENGINE,
           "policy": pol, **aggregate(comps), **stp_metrics(decisions, comps),
           "latency_ms_median_extractor": round(1000 * sorted(lat)[len(lat) // 2], 1)}
    if mode == "A":
        from seqeval.metrics import f1_score, precision_score, recall_score
        rel = [[l for l in s] for s in y_true]
        out.update({"token_entity_f1": f1_score(rel, y_pred), "token_entity_precision": precision_score(rel, y_pred),
                    "token_entity_recall": recall_score(rel, y_pred)})
    return {"summary": out, "details": details}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="rules")
    ap.add_argument("--split", default="validation")
    ap.add_argument("--mode", default="A", choices=["A", "B"])
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    if a.split == "test" and not a.final:
        raise SystemExit("test split is evaluated once, at the end: pass --final")
    res = run(a.model, a.split, a.mode)
    (RES / "details").mkdir(parents=True, exist_ok=True)
    tag = f"{a.model}_{a.split}_mode{a.mode}"
    (RES / f"eval_{tag}.json").write_text(json.dumps(res["summary"], indent=1))
    (RES / "details" / f"{tag}.json").write_text(json.dumps(res["details"], indent=1, ensure_ascii=False))
    s = res["summary"]
    print(f"{tag}: key_field_EM={s['key_field_exact_match']:.3f} posting_correct={s['posting_correct_rate']:.3f} "
          f"fully_correct={s['fully_correct_rate']:.3f} item_F1={s['line_item_f1']:.3f} "
          f"STP={s['stp_rate']:.2f} auto_correct={s['auto_post_correctness']} "
          + (f"token_F1={s['token_entity_f1']:.3f}" if a.mode == "A" else ""))


if __name__ == "__main__":
    main()
