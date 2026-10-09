"""Project CORD gold labels onto real-OCR words, so models can also train on what they see at
inference time (OCR splits, merges and misreads), not only on clean gold words.

Each OCR word takes the label of the gold word it overlaps most (intersection / OCR-word area
>= 0.5); otherwise O. B/I follows the gold annotated line. TRAIN split only.
"""
from __future__ import annotations

from .dataset import label_map, load_split
from .layout import reading_order
from .ocr import normalise_words
from .ocr_cache import load_cache


def _overlap(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    return ix * iy / area


def project(rec: dict, ocr_words: list[dict], min_overlap: float = 0.5) -> list[dict]:
    lm = label_map()
    ws = reading_order(normalise_words(ocr_words))
    prev_line = None
    for w in ws:
        best, best_ov = None, min_overlap
        for g in rec["words"]:
            ov = _overlap(w["box"], g["box"])
            if ov >= best_ov:
                best, best_ov = g, ov
        cat = None if best is None else lm.get(best["category"], best["category"])
        if best is None or cat in (None, "O") or best.get("is_key"):
            w["label"] = "O"
            prev_line = None
            continue
        w["label"] = ("I-" if prev_line == best["line_idx"] else "B-") + cat
        prev_line = best["line_idx"]
    return ws


def ocr_train_sequences(split: str = "train") -> list[tuple[dict, list[dict], int, int]]:
    """[(record, labelled OCR words, width, height)] for receipts present in the OCR cache."""
    assert split == "train", "label projection is only used to build training data"
    cache = load_cache(split)
    out = []
    for rec in load_split(split):
        c = cache.get(rec["id"])
        if c is None:
            continue
        # OCR ran on an image resized by load_image(); rescale gold boxes into OCR coordinates
        sx, sy = c["width"] / rec["width"], c["height"] / rec["height"]
        scaled = dict(rec, words=[dict(g, box=[g["box"][0] * sx, g["box"][1] * sy, g["box"][2] * sx, g["box"][3] * sy])
                                  for g in rec["words"]])
        out.append((rec, project(scaled, c["words"]), c["width"], c["height"]))
    return out
