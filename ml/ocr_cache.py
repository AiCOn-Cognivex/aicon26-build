"""Run OCR over a split, cache word outputs, and benchmark them against gold words.

  python -m ml.ocr_cache --split validation
Writes data/cache/ocr_rapidocr_{split}.jsonl and results/ocr_benchmark.json (merged per split).

Benchmark measures (vs CORD gold words, no tuning on test):
  word_recall          share of gold words found verbatim (case-insensitive) among OCR words
  key_amount_recall    share of gold header amounts (total, subtotal, tax, ...) that appear as an
                       OCR token with the same parsed value -> an upper bound for Mode B extraction
  latency, peak RSS
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import psutil

from .dataset import ROOT, image_path, load_split
from .fields import gold_fields
from .money import parse_money
from .ocr import ENGINE, load_image, run_ocr

CACHE = ROOT / "data" / "cache"


def cache_path(split):
    return CACHE / f"ocr_{ENGINE}_{split}.jsonl"


def load_cache(split) -> dict:
    with open(cache_path(split), encoding="utf-8") as f:
        return {r["id"]: r for r in map(json.loads, f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="validation")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    recs = load_split(a.split)
    if a.limit:
        recs = recs[: a.limit]
    proc = psutil.Process()
    lat, peak = [], 0
    wr_hit = wr_tot = ka_hit = ka_tot = 0
    out = cache_path(a.split) if not a.limit else CACHE / f"ocr_{ENGINE}_{a.split}_first{a.limit}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in recs:
            img = load_image(image_path(r).read_bytes())
            t0 = time.perf_counter()
            words = run_ocr(img)
            lat.append(time.perf_counter() - t0)
            peak = max(peak, proc.memory_info().rss)
            f.write(json.dumps({"id": r["id"], "width": img.width, "height": img.height,
                                "words": words}, ensure_ascii=False) + "\n")
            ocr_c = Counter(w["text"].lower() for w in words)
            gold_c = Counter(w["text"].lower() for w in r["words"])
            wr_hit += sum((ocr_c & gold_c).values())
            wr_tot += sum(gold_c.values())
            vals = {parse_money(w["text"]) for w in words} - {None}
            for fv in gold_fields(r["gt_parse"])["fields"].values():
                if fv is not None and fv["value"] is not None:
                    ka_tot += 1
                    ka_hit += parse_money(fv["text"]) in vals
    lat.sort()
    res = {"engine": ENGINE, "split": a.split, "n": len(recs),
           "word_recall": round(wr_hit / wr_tot, 4), "key_amount_recall": round(ka_hit / max(ka_tot, 1), 4),
           "latency_s_median": round(lat[len(lat) // 2], 3), "latency_s_p90": round(lat[int(0.9 * (len(lat) - 1))], 3),
           "peak_rss_mb": round(peak / 2**20)}
    if a.split == "test":  # test is only touched by the final evaluation: cache OCR, report nothing
        print(f"cached {len(recs)} test receipts (no benchmark written for test)")
        return
    bench = ROOT / "results" / "ocr_benchmark.json"
    allres = json.loads(bench.read_text()) if bench.exists() else {}
    allres[f"{ENGINE}_{a.split}_n{len(recs)}"] = res
    bench.write_text(json.dumps(allres, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
