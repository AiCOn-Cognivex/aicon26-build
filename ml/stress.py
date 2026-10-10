"""Robustness stress test: the production pipeline on validation images degraded at fixed levels.

  python -m ml.augment_images --stress      # OCR every degraded validation image once (cached)
  python -m ml.stress                       # -> results/robustness_images.json
Each level degrades every validation image the same way (blur, JPEG, noise, downscale, darkening, shadow,
rotation; levels in ml/augment_images.py STRESS), runs the production OCR on it, then the given model with
its own decision policy. Reports posting-correct, auto-post coverage and auto-post correctness per level,
next to the clean images. Nothing here is used for tuning.
"""
from __future__ import annotations

import argparse
import json

from . import taggers
from .augment_images import AUG, STRESS
from .dataset import ROOT, load_split
from .decision import decide
from .decode import decode
from .fields import gold_fields
from .metrics import compare
from .ocr import normalise_words
from .ocr_cache import load_cache


def run_level(cache: dict, fn, pol) -> dict:
    n = ok = auto = auto_ok = 0
    per = {}
    for r in load_split("validation"):
        c = cache[r["id"]]
        pred = decode(fn(normalise_words(c["words"]), c["width"], c["height"]), pol)
        comp = compare(pred, gold_fields(r["gt_parse"]))
        d = decide(pred["fields"], pred["line_items"], pol, pred.get("absent_confidence"),
                   pred.get("assignment_posterior"), pred.get("receipt_confidence"))["decision"]
        n += 1
        ok += comp["posting_correct"]
        per[r["id"]] = [int(comp["posting_correct"]), int(d == "AUTO_POST")]
        if d == "AUTO_POST":
            auto += 1
            auto_ok += comp["posting_correct"]
    return {"n": n, "posting_correct": ok / n, "stp": auto / n, "n_auto": auto, "auto_correct": auto_ok,
            "auto_post_correctness": auto_ok / auto if auto else None, "per_receipt": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="crf")
    ap.add_argument("--crf-path", default=None, help="evaluate another CRF pickle with the crf policy")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    from .predict import policy_for
    pol = policy_for(a.model)
    name, _, fn = taggers.load(a.model)
    if a.crf_path:
        from pathlib import Path
        from .crf_model import CRFTagger
        t = CRFTagger.load(Path(a.crf_path))
        t.T = pol.get("temperature", 1.0)
        name, fn = f"{name} [{Path(a.crf_path).name}]", t.tag
    out = {"model": name, "policy": {k: v for k, v in pol.items() if k != "note"}, "split": "validation",
           "levels": {"clean": run_level(load_cache("validation"), fn, pol)}}
    for lvl in STRESS:
        p = AUG / f"stress_validation_{lvl}.jsonl"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                out["levels"][lvl] = run_level({r["id"]: r for r in map(json.loads, f)}, fn, pol)
    (ROOT / "results" / "cv" / f"robustness_images_{a.model}{a.tag}.json").write_text(json.dumps(out, indent=1))
    for k, v in out["levels"].items():
        print(f"{k:11s} posting {v['posting_correct']:.2f}  STP {v['stp']:.2f}  auto correct {v['auto_correct']}/{v['n_auto']}")


if __name__ == "__main__":
    main()
