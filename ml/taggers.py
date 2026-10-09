"""Load any rung by name -> (display name, rung, fn(words, width, height) -> tagged words)."""
from __future__ import annotations

import os
from pathlib import Path

from . import rules_baseline

ROOT = Path(__file__).resolve().parents[1]
ART = Path(os.getenv("MODEL_DIR", ROOT / "ml" / "artifacts"))

NAMES = {
    "rules": ("Rules baseline (keywords + regex)", 0),
    "crf": ("CRF (token + layout features)", 1),
    "lilt": ("LiLT (lilt-roberta-en-base, fine-tuned on CORD v2)", 2),
}


def available() -> list[str]:
    out = ["rules"]
    if (ART / "crf.pkl").exists():
        out.append("crf")
    if (ART / "lilt" / "labels.json").exists():
        out.append("lilt")
    return out


def load(kind: str):
    if kind == "auto":
        kind = available()[-1]
    name, rung = NAMES[kind]
    if kind == "lilt":
        from .lilt_model import LiltTagger
        return name, rung, LiltTagger.load(ART / "lilt").tag
    if kind == "crf":
        from .crf_model import CRFTagger
        return name, rung, CRFTagger.load(ART / "crf.pkl").tag
    return name, rung, lambda words, w, h: rules_baseline.tag(words)
