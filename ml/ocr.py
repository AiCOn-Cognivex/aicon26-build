"""OCR: image -> [{"text", "box":[x0,y0,x1,y1], "ocr_conf"}] (word level).

RapidOCR = PaddleOCR detection+recognition models run with ONNX Runtime (Apache-2.0), pip-only.
Chosen over Tesseract 5 on validation (docs/decision_log.md D5; Tesseract numbers in results/ocr_benchmark.json).
"""
from __future__ import annotations

import io
import math
import os
import re
from functools import lru_cache

import numpy as np
from PIL import Image

ENGINE = "rapidocr"  # name used in OCR cache files (data/cache/ocr_rapidocr_<split>.jsonl)


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


def _cpu_limit() -> int | None:
    """CPUs this process may really use: cgroup CPU quota (containers) or CPU affinity; None if unknown."""
    for path, parse in (("/sys/fs/cgroup/cpu.max", lambda t: t.split()[:2]),
                        ("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", lambda t: [t.strip(), "100000"])):
        try:
            q, period = parse(open(path).read())
            if q not in ("max", "-1"):
                return max(1, math.ceil(int(q) / int(period)))
        except (OSError, ValueError):
            pass
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return None


def ocr_threads() -> int | None:
    """ONNX Runtime threads for OCR. By default ORT starts one busy-waiting thread per core it can SEE;
    in a container capped at ~1 vCPU those threads fight each other. OCR_THREADS env overrides."""
    env = os.getenv("OCR_THREADS")
    return int(env) if env else _cpu_limit()


@lru_cache(maxsize=1)
def _rapid():
    import rapidocr_onnxruntime.utils as ru
    from rapidocr_onnxruntime import RapidOCR
    n = ocr_threads()
    if n:  # RapidOCR has no thread option: wrap the SessionOptions factory it calls
        base = ru.SessionOptions

        def opts():
            o = base()
            o.intra_op_num_threads, o.inter_op_num_threads = n, 1
            o.add_session_config_entry("session.intra_op.allow_spinning", "0")
            return o
        ru.SessionOptions = opts
    # Angle classifier off: it sometimes flips upright text 180 degrees. Chosen on 200 TRAIN receipts
    # (gold-amount recall 93.6% -> 94.9% with the merge rule), confirmed on validation (96.0% -> 99.1%).
    return RapidOCR(use_angle_cls=False)


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


# "1EGG", "2xNASI", "1S-Ovaltine": OCR glues the printed quantity onto the item name
_QTY_PREFIX = re.compile(r"^(\d{1,2})([xX]?)([A-Za-z][A-Za-z\-].*)$")
# "74." + "000" or "154" + "000": OCR puts a space inside an amount
_SPLIT_HEAD = re.compile(r"^\d{1,3}[.,]$")
_SPLIT_TAIL = re.compile(r"^\d{3}([.,]\d{3})*([.,]\d{1,2})?$")


def _merge_split_amounts(words: list[dict]) -> list[dict]:
    """Re-join an amount that OCR split at a thousands separator, only within one OCR line."""
    out = []
    for w in words:
        if out:
            p = out[-1]
            same_line = abs(p["box"][1] - w["box"][1]) < 1 and abs(p["box"][3] - w["box"][3]) < 1
            if same_line and ((_SPLIT_HEAD.match(p["text"]) and _SPLIT_TAIL.match(w["text"])) or
                              (re.fullmatch(r"\d{1,3}", p["text"]) and w["text"] == "000")):
                out[-1] = {**p, "text": p["text"] + w["text"],
                           "box": [p["box"][0], p["box"][1], w["box"][2], w["box"][3]],
                           "ocr_conf": min(p.get("ocr_conf", 1.0), w.get("ocr_conf", 1.0))}
                continue
        out.append(w)
    return out


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
    return _merge_split_amounts(out)


def run_ocr(img: Image.Image) -> list[dict]:
    return normalise_words(rapidocr_words(img))
