"""Load processed CORD records and build word sequences with gold BIO labels."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .layout import reading_order

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
IMAGES = ROOT / "data" / "raw" / "images"
LABEL_MAP_PATH = ROOT / "data" / "label_map.json"


@lru_cache(maxsize=4)
def load_split(split: str) -> list[dict]:
    with open(PROC / f"{split}.jsonl", encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def image_path(rec: dict) -> Path:
    return IMAGES / rec["split"] / f"{rec['idx']}.png"


@lru_cache(maxsize=1)
def label_map() -> dict:
    """category -> category used for training (rare categories merged, see data/LABELS.md)."""
    if LABEL_MAP_PATH.exists():
        return json.loads(LABEL_MAP_PATH.read_text(encoding="utf-8"))["map"]
    return {}


def gold_sequence(rec: dict) -> list[dict]:
    """Gold words in reading order with BIO labels. An entity = one annotated CORD line."""
    lm = label_map()
    words = reading_order(rec["words"])
    prev_line = None
    for w in words:
        cat = lm.get(w["category"], w["category"])
        if cat in (None, "O"):
            w["label"] = "O"
            prev_line = None
            continue
        w["label"] = ("I-" if prev_line == w["line_idx"] else "B-") + cat
        prev_line = w["line_idx"]
    return words


def label_list() -> list[str]:
    cats = sorted({v for v in label_map().values() if v != "O"})
    return ["O"] + [f"{p}-{c}" for c in cats for p in ("B", "I")]
