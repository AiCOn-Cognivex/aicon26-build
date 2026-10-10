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


def _subset(details):
    comps = [{"fields": d["fields_ok"], "gold_present": {f: True for f in d["fields_ok"]},
              "items_tp": d["items_tp"], "items_tp_lenient": 0, "items_pred": d["items_pred"],
              "items_gold": d["items_gold"], "posting_correct": d["posting_correct"],
              "fully_correct": d["fully_correct"]} for d in details]
    agg = aggregate(comps)
    return {"n_receipts": len(details), "posting_correct_rate": agg["posting_correct_rate"],
            "fully_correct_rate": agg["fully_correct_rate"], **stp_metrics([d["decision"] for d in details], comps)}


def _near_duplicates(seen, test, threshold=0.5):
    """Test ids that share a template with a seen receipt (inputs only: words, never labels)."""
    import re
    from collections import Counter

    def toks(r):
        return {w["text"].lower().strip(".,:") for w in r["words"] if re.search(r"[a-z]{2,}", w["text"].lower())}
    ts = [toks(r) for r in seen]
    df = Counter(t for s in ts for t in s)
    common = {t for t, c in df.items() if c > 0.03 * len(seen)}
    ts = [s - common for s in ts]
    out = set()
    for r in test:
        a = toks(r) - common
        if len(a) >= 2 and any(len(b) >= 2 and len(a & b) / len(a | b) >= threshold for b in ts):
            out.add(r["id"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final-model", required=True)
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    if not a.confirm:
        raise SystemExit("pass --confirm: the test set is evaluated exactly once")
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists: the test set has been used. Not overwriting.")
    seen = load_split("train") + load_split("validation")  # the final model may be trained on both (D22)
    train_sigs = {_sig(r) for r in seen}
    dup_ids = {r["id"] for r in load_split("test") if _sig(r) in train_sigs}
    seen_tmpl = _near_duplicates(seen, load_split("test"))
    evals, dedup, unseen = {}, {}, {}
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
            dedup[key] = _subset(keep)
            unseen[key] = _subset([d for d in res["details"] if d["id"] not in seen_tmpl])
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
           "evals": evals, "dedup_subset": {"removed_ids": sorted(dup_ids), "evals": dedup},
           "unseen_template_subset": {"rule": "test receipts with no train/validation receipt sharing >= 50% of "
                                              "distinctive words (Jaccard, as the CV groups, ml/cv.py)",
                                      "removed_ids": sorted(seen_tmpl), "evals": unseen}}
    OUT.write_text(json.dumps(out, indent=1))
    print(f"headline ({a.final_model}, test, real OCR): STP {head['stp_rate']:.2f}, "
          f"{k}/{head['n_auto']} auto-posts correct, exact 95% CI {lo:.3f}-{hi:.3f}; "
          f"{len(dup_ids)} test receipts duplicate train text")


if __name__ == "__main__":
    main()
