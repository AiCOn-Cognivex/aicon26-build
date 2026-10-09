"""Download CORD v2 (official 800/100/100 split, unchanged) and write a flat, model-friendly copy.

Outputs (gitignored, reproducible):
  data/raw/images/{split}/{idx}.png
  data/processed/{split}.jsonl   one receipt per line:
     id, split, idx, width, height, gt_parse,
     words: [{text, box:[x0,y0,x1,y1] (pixels), category, group_id, row_id, line_idx}],
     issues: [...]   problems found while flattening (logged, never silently dropped)

Usage: python data/prepare_cord.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "images"
OUT = ROOT / "data" / "processed"


def quad_to_box(q: dict) -> list[float]:
    xs = [q["x1"], q["x2"], q["x3"], q["x4"]]
    ys = [q["y1"], q["y2"], q["y3"], q["y4"]]
    return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]


def flatten(gt: dict, width: int, height: int) -> tuple[list[dict], list[str]]:
    words, issues = [], []
    for li, line in enumerate(gt.get("valid_line", [])):
        cat = line.get("category")
        gid = line.get("group_id")
        if not cat:
            issues.append(f"line {li}: missing category")
        for w in line.get("words", []):
            text = (w.get("text") or "").strip()
            q = w.get("quad")
            if not text:
                issues.append(f"line {li}: empty word text")
                continue
            if not q:
                issues.append(f"line {li}: word '{text}' has no quad")
                continue
            box = quad_to_box(q)
            if box[2] <= box[0] or box[3] <= box[1]:
                issues.append(f"line {li}: degenerate box for '{text}'")
            if box[0] < -5 or box[1] < -5 or box[2] > width + 5 or box[3] > height + 5:
                issues.append(f"line {li}: box outside image for '{text}'")
            words.append({
                "text": text, "box": box, "category": cat, "group_id": gid,
                "row_id": w.get("row_id"), "line_idx": li,
            })
    if not words:
        issues.append("no words")
    return words, issues


def main() -> int:
    from datasets import load_dataset

    ds = load_dataset("naver-clova-ix/cord-v2")
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation", "test"):
        (RAW / split).mkdir(parents=True, exist_ok=True)
        n_issues = 0
        with open(OUT / f"{split}.jsonl", "w", encoding="utf-8") as f:
            for idx, ex in enumerate(ds[split]):
                img = ex["image"].convert("RGB")
                img_path = RAW / split / f"{idx}.png"
                if not img_path.exists():
                    img.save(img_path)
                issues = []
                try:
                    gt = json.loads(ex["ground_truth"])
                except json.JSONDecodeError as e:
                    gt, issues = {}, [f"ground_truth JSON error: {e}"]
                meta = gt.get("meta", {})
                size = meta.get("image_size", {})
                w, h = img.size
                if size and (size.get("width"), size.get("height")) != (w, h):
                    issues.append(f"meta image_size {size} != actual {(w, h)}")
                words, wi = flatten(gt, w, h)
                issues += wi
                n_issues += bool(issues)
                rec = {
                    "id": f"{split}_{idx}", "split": split, "idx": idx,
                    "width": w, "height": h, "image_id": meta.get("image_id"),
                    "gt_parse": gt.get("gt_parse", {}), "words": words, "issues": issues,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{split}: {len(ds[split])} receipts, {n_issues} with issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
