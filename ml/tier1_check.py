"""Score cached OOF predictions with the current decoding code (Tier 1 checks, D25).

  python -m ml.tier1_check --cv deskew_infer --save base      # snapshot
  python -m ml.tier1_check --cv tier1 --against base           # paired comparison
Posting-correct and fully-correct per receipt (Mode B, real OCR, rerank decoder, T=1.1); the snapshot lives in
results/cv/tier1_<name>.json.
"""
from __future__ import annotations

import argparse
import json

from .cv import RES, _records, load_folds, load_preds, paired_bootstrap
from .decode import rerank
from .fields import gold_fields
from .metrics import aggregate, compare
from .policy_cv import _temper


def score(cv: str) -> dict:
    recs = _records()
    comps = {}
    for p in load_preds(cv):
        comps[p["id"]] = compare(rerank(_temper(p["B"], 1.1), lam=1.5), gold_fields(recs[p["id"]]["gt_parse"]))
    agg = aggregate(list(comps.values()))
    return {"cv": cv, "posting_correct": agg["posting_correct_rate"], "fully_correct": agg["fully_correct_rate"],
            "line_item_f1": agg["line_item_f1"], "line_item_f1_lenient": agg["line_item_f1_lenient"],
            "posting": {i: int(c["posting_correct"]) for i, c in comps.items()},
            "fully": {i: int(c["fully_correct"]) for i, c in comps.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", required=True)
    ap.add_argument("--save")
    ap.add_argument("--against")
    a = ap.parse_args()
    s = score(a.cv)
    print(f"{a.cv}: posting {s['posting_correct']:.4f} fully {s['fully_correct']:.4f} "
          f"items {s['line_item_f1']:.3f}/{s['line_item_f1_lenient']:.3f}")
    if a.save:
        (RES / f"tier1_{a.save}.json").write_text(json.dumps(s))
    if a.against:
        g, _ = load_folds()
        b = json.loads((RES / f"tier1_{a.against}.json").read_text())
        for k in ("posting", "fully"):
            r = paired_bootstrap(b[k], s[k], g)
            print(f"  {k} vs {a.against}: {r['delta']:+.4f} CI {r['ci95'][0]:+.4f}..{r['ci95'][1]:+.4f} "
                  f"fixed/broken {r['b_wins']}/{r['b_losses']}")


if __name__ == "__main__":
    main()
