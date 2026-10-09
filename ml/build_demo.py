"""Pre-compute demo examples + a results snapshot so the frontend works with no backend at all.

  python -m ml.build_demo --n-auto 5 --n-review 4
Examples are VALIDATION receipts, taken in id order (no cherry-picking on correctness): the first
N auto-posted and, for review, the first receipt of each distinct review reason. Each example carries
the gold values so the viewer can check the decision.
Writes results/demo_examples.json, results/demo_images/*, frontend/public/demo/{examples.json,
results.json, *.jpg}.
"""
from __future__ import annotations

import argparse
import json
import shutil

from PIL import Image

from .dataset import ROOT, image_path, load_split
from .fields import gold_fields
from .metrics import compare
from .ocr import normalise_words
from .ocr_cache import load_cache
from . import predict as P

FRONT = ROOT / "frontend" / "public" / "demo"
RES = ROOT / "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-auto", type=int, default=5)
    ap.add_argument("--n-review", type=int, default=4)
    a = ap.parse_args()
    cache = load_cache("rapidocr", "validation")
    picked, n_auto, n_rev, seen_reasons = [], 0, 0, set()
    (RES / "demo_images").mkdir(parents=True, exist_ok=True)
    FRONT.mkdir(parents=True, exist_ok=True)
    for rec in load_split("validation"):
        c = cache[rec["id"]]
        res = P.predict_words(normalise_words(c["words"]), c["width"], c["height"])
        res["ocr"]["engine"] = "rapidocr (cached)"
        auto = res["decision"] == "AUTO_POST"
        reason_type = res["reasons"][0].split("(")[0].split(":")[0].strip()
        if (auto and n_auto >= a.n_auto) or (not auto and n_rev >= a.n_review):
            continue
        if not auto and reason_type in seen_reasons:  # one review example per distinct reason
            continue
        seen_reasons.add(reason_type)
        n_auto += auto
        n_rev += not auto
        gold = gold_fields(rec["gt_parse"])
        ok = compare({"fields": res["fields"], "line_items": res["line_items"]}, gold)["posting_correct"]
        name = f"{rec['id']}.jpg"
        img = Image.open(image_path(rec)).convert("RGB")
        img = img.resize((c["width"], c["height"]))  # same coordinates as the OCR boxes
        img.thumbnail((900, 1600))
        img.save(RES / "demo_images" / name, quality=80)
        shutil.copy(RES / "demo_images" / name, FRONT / name)
        note = ("Auto-posted. " if auto else "Sent to human review. ") + \
               ("All posted amounts match the gold labels." if ok else "Some amounts differ from the gold labels.")
        picked.append({"id": rec["id"], "image": name, "note": note, "result": res,
                       "gold": {k: (v["text"] if v else None) for k, v in gold["fields"].items()},
                       "posting_correct": ok})
        if n_auto >= a.n_auto and n_rev >= a.n_review:
            break
    out = {"model": P.tagger()[0], "policy": P.policy(), "examples": picked}
    (RES / "demo_examples.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    (FRONT / "examples.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    # snapshot of what /results serves, for offline use
    snap = {}
    for p in sorted(RES.glob("*.json")):
        if p.name not in ("demo_examples.json", "data_quality.json"):
            snap[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    (FRONT / "results.json").write_text(json.dumps(snap), encoding="utf-8")
    print(f"{len(picked)} examples ({n_auto} auto, {n_rev} review), snapshot of {len(snap)} result files")


if __name__ == "__main__":
    main()
