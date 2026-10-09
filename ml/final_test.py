"""The single test-set evaluation. Run ONCE, after model, preprocessing and policy are frozen.

  python -m ml.final_test --final-model crf --confirm
Evaluates every frozen rung (rules, crf, lilt if present) on test in Mode A and Mode B with each
rung's own validation-fitted policy, plus the same metrics on a de-duplicated subset (test receipts
whose word sequence also appears in train removed). Refuses to overwrite results/test_metrics.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime

from . import taggers
from .calibrate import clopper_pearson
from .dataset import ROOT, load_split
from .evaluate import run
from .metrics import aggregate, stp_metrics

OUT = ROOT / "results" / "test_metrics.json"


def _sig(rec):
    return hashlib.md5(" ".join(w["text"] for w in rec["words"]).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final-model", required=True)
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    if not a.confirm:
        raise SystemExit("pass --confirm: the test set is evaluated exactly once")
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists: the test set has been used. Not overwriting.")
    train_sigs = {_sig(r) for r in load_split("train")}
    dup_ids = {r["id"] for r in load_split("test") if _sig(r) in train_sigs}
    evals, dedup = {}, {}
    for model in taggers.available():
        tg = taggers.load(model)
        for mode in ("A", "B"):
            res = run(model, "test", mode, tagger=tg)
            key = f"eval_{model}_test_mode{mode}"
            evals[key] = res["summary"]
            keep = [d for d in res["details"] if d["id"] not in dup_ids]
            comps = [{"fields": d["fields_ok"], "gold_present": {f: True for f in d["fields_ok"]},
                      "items_tp": d["items_tp"], "items_tp_lenient": 0, "items_pred": d["items_pred"],
                      "items_gold": d["items_gold"], "posting_correct": d["posting_correct"],
                      "fully_correct": d["fully_correct"]} for d in keep]
            agg = aggregate(comps)
            dedup[key] = {"n_receipts": len(keep), "posting_correct_rate": agg["posting_correct_rate"],
                          "fully_correct_rate": agg["fully_correct_rate"],
                          **stp_metrics([d["decision"] for d in keep], comps)}
            (ROOT / "results" / "details" / f"{model}_test_mode{mode}.json").write_text(
                json.dumps(res["details"], indent=1, ensure_ascii=False))
            s = res["summary"]
            print(f"{key}: posting={s['posting_correct_rate']:.3f} fully={s['fully_correct_rate']:.3f} "
                  f"STP={s['stp_rate']:.2f} auto_correct={s['auto_post_correctness']}")
    head = evals[f"eval_{a.final_model}_test_modeB"]
    k = round((head["auto_post_correctness"] or 0) * head["n_auto"])
    lo, hi = clopper_pearson(k, head["n_auto"])
    out = {"evaluated_at": datetime.now().isoformat(timespec="seconds"), "final_model": a.final_model,
           "headline": {**head, "auto_post_correct_count": k, "auto_post_ci95_exact": [lo, hi]},
           "evals": evals, "dedup_subset": {"removed_ids": sorted(dup_ids), "evals": dedup}}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"headline ({a.final_model}, test, real OCR): STP {head['stp_rate']:.2f}, "
          f"{k}/{head['n_auto']} auto-posts correct, exact 95% CI {lo:.3f}-{hi:.3f}; "
          f"{len(dup_ids)} test receipts duplicate train text")


if __name__ == "__main__":
    main()
