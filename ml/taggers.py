"""Load any rung by name -> (display name, rung, fn(words, width, height) -> tagged words)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import rules_baseline

ROOT = Path(__file__).resolve().parents[1]
ART = Path(os.getenv("MODEL_DIR", ROOT / "ml" / "artifacts"))
# point at another trained LiLT folder to evaluate a variant: LILT_DIR=ml/artifacts/lilt_lr3e-5
LILT_DIR = Path(os.getenv("LILT_DIR", ART / "lilt"))

NAMES = {
    "rules": ("Rules baseline (keywords + regex)", 0),
    "crf": ("CRF (token + layout features)", 1),
    "lilt": ("LiLT (lilt-roberta-en-base, fine-tuned on CORD v2)", 2),
}


def available() -> list[str]:
    out = ["rules"]
    if (ART / "crf.pkl").exists():
        out.append("crf")
    if (LILT_DIR / "labels.json").exists():
        out.append("lilt")
    return out


def _temperature(kind: str) -> float:
    p = ART / f"{kind}_calibration.json"
    return json.loads(p.read_text())["temperature"] if p.exists() else 1.0


def load(kind: str, calibrated: bool = True):
    """calibrated=False returns raw scores (used when fitting the temperature)."""
    if kind == "auto":
        kind = available()[-1]
    name, rung = NAMES[kind]
    if kind == "lilt":
        from .lilt_model import LiltTagger
        t = LiltTagger.load(LILT_DIR)
        t.T = _temperature("lilt") if calibrated else 1.0
        return name, rung, t.tag
    if kind == "crf":
        from .crf_model import CRFTagger
        t = CRFTagger.load(ART / "crf.pkl")
        t.T = _temperature("crf") if calibrated else 1.0
        return name, rung, t.tag
    return name, rung, lambda words, w, h: rules_baseline.tag(words)
