"""OCR engines behind one interface: image -> [{"text", "box":[x0,y0,x1,y1], "ocr_conf"}] (word level).

- rapidocr: PaddleOCR detection+recognition models run with ONNX Runtime (Apache-2.0), pip-only.
- tesseract: Tesseract 5 via pytesseract (Apache-2.0), needs the system binary.
"""
from __future__ import annotations

import io
import os
import re
import shutil
from functools import lru_cache

import numpy as np
from PIL import Image

_TESS_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def load_image(image_bytes: bytes, max_side: int = 1600) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes))
    img = _exif_upright(img).convert("RGB")
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)))
    return img


def _exif_upright(img: Image.Image) -> Image.Image:
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


@lru_cache(maxsize=1)
def _rapid():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def rapidocr_words(img: Image.Image) -> list[dict]:
    result, _ = _rapid()(np.asarray(img))
    words = []
    for quad, text, score in result or []:
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        toks = text.split()
        if not toks:
            continue
        # split the line box across words proportionally to character count (incl. spaces)
        total = sum(len(t) for t in toks) + (len(toks) - 1)
        cx = x0
        for t in toks:
            w = (x1 - x0) * len(t) / max(total, 1)
            words.append({"text": t, "box": [float(cx), float(y0), float(cx + w), float(y1)],
                          "ocr_conf": float(score)})
            cx += w + (x1 - x0) / max(total, 1)
    return words


def tesseract_words(img: Image.Image) -> list[dict]:
    import pytesseract
    if not shutil.which("tesseract") and os.path.exists(_TESS_WIN):
        pytesseract.pytesseract.tesseract_cmd = _TESS_WIN
    d = pytesseract.image_to_data(img, config="--psm 4", output_type=pytesseract.Output.DICT)
    words = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        conf = float(d["conf"][i])
        if not t or conf < 0:
            continue
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        words.append({"text": t, "box": [float(x), float(y), float(x + w), float(y + h)],
                      "ocr_conf": conf / 100.0})
    return words


ENGINES = {"rapidocr": rapidocr_words, "tesseract": tesseract_words}

# "1EGG", "2xNASI", "1S-Ovaltine": OCR glues the printed quantity onto the item name
_QTY_PREFIX = re.compile(r"^(\d{1,2})([xX]?)([A-Za-z][A-Za-z\-].*)$")


def normalise_words(words: list[dict]) -> list[dict]:
    """Engine-agnostic clean-up applied to every real-OCR output (same for all models)."""
    out = []
    for w in words:
        m = _QTY_PREFIX.match(w["text"])
        if m:
            x0, y0, x1, y1 = w["box"]
            q, name = m.group(1) + m.group(2), m.group(3)
            split = x0 + (x1 - x0) * len(q) / len(w["text"])
            out.append({**w, "text": q, "box": [x0, y0, split, y1]})
            out.append({**w, "text": name, "box": [split, y0, x1, y1]})
        else:
            out.append(w)
    return out


def run_ocr(img: Image.Image, engine: str = "rapidocr") -> list[dict]:
    return normalise_words(ENGINES[engine](img))
