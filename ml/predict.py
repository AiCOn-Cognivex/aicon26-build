"""Inference entry point used by the backend.

predict(image_bytes) -> dict  (the interface contract between ML and full stack)
{
  "ocr":        {"engine", "image_size": [w, h], "words": [{"text", "box": [x0,y0,x1,y1], "label", "prob"}]},
  "fields":     {total|subtotal|tax|service_charge|discount: {"text","value","confidence"} | null},
  "line_items": [{"name","qty","price","price_value","qty_value","confidence"}],
  "reconciliation": {"status": PASS|FAIL|NOT_CHECKABLE, "checks": [{rule, expected, actual, ok}]},
  "decision":   "AUTO_POST" | "HUMAN_REVIEW",
  "reasons":    [str, ...],
  "model":      {"name", "rung"},
  "timings_ms": {"ocr", "model", "total"}
}
Model is chosen by env MODEL_KIND (rules | crf | lilt); default = best available artifact.
"""
from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path

from . import taggers
from .decision import DEFAULT_POLICY, decide
from .fields import assemble
from .ocr import load_image, run_ocr

ROOT = Path(__file__).resolve().parents[1]
ART = Path(os.getenv("MODEL_DIR", ROOT / "ml" / "artifacts"))
OCR_ENGINE = os.getenv("OCR_ENGINE", "rapidocr")


@lru_cache(maxsize=1)
def policy() -> dict:
    p = ART / "policy.json"
    if p.exists():
        return {**DEFAULT_POLICY, **json.loads(p.read_text())}
    return dict(DEFAULT_POLICY)


@lru_cache(maxsize=1)
def tagger():
    """Returns (name, rung, fn(words, w, h) -> tagged words). Falls back to rules if loading fails."""
    try:
        return taggers.load(os.getenv("MODEL_KIND", "auto"))
    except Exception as e:  # never leave the API without an extractor
        print(f"model load failed ({e!r}); falling back to rules baseline")
        return taggers.load("rules")


def predict_words(words: list[dict], width: int, height: int) -> dict:
    """Same pipeline from already-OCR'd words (used by evaluation and cached demos)."""
    name, rung, fn = tagger()
    t0 = time.perf_counter()
    tagged = fn(words, width, height)
    out = assemble(tagged)
    d = decide(out["fields"], out["line_items"], policy())
    return {
        "ocr": {"words": [{"text": w["text"], "box": [round(v, 1) for v in w["box"]],
                           "label": w.get("label", "O"), "prob": round(float(w.get("prob", 1.0)), 4)}
                          for w in tagged],
                "image_size": [width, height]},
        "fields": out["fields"], "line_items": out["line_items"],
        "reconciliation": d["reconciliation"], "decision": d["decision"], "reasons": d["reasons"],
        "model": {"name": name, "rung": rung},
        "timings_ms": {"model": round(1000 * (time.perf_counter() - t0), 1)},
    }


def predict(image_bytes: bytes) -> dict:
    t0 = time.perf_counter()
    img = load_image(image_bytes)
    words = run_ocr(img, OCR_ENGINE)
    t1 = time.perf_counter()
    res = predict_words(words, img.width, img.height)
    res["ocr"]["engine"] = OCR_ENGINE
    res["timings_ms"]["ocr"] = round(1000 * (t1 - t0), 1)
    res["timings_ms"]["total"] = round(1000 * (time.perf_counter() - t0), 1)
    return res


def warmup():
    tagger()
    policy()
