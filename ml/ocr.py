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
# Tier 1 (D25), inference only: split amounts that OCR glued across table columns ("55110.00" = 55 | 110.00)
SPLIT_MERGED = os.getenv("OCR_SPLIT_MERGED", "1") == "1"


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


# Tier 1 (D25), inference only: OCR drops the gap between table columns and glues numbers together.
_COL_GAP = re.compile(r"(\d[\d.,]*)[:|](\d[\d.,]*\.\d{2})")          # "110:330.00", "0.00|2.395.00"
_QTY_AMT = re.compile(r"(\d{1,2}\.\d)(\d{1,3}(?:[.,]\d{3})+\.\d{2})")  # "1.02.395.00" = qty 1.0 | 2.395.00
_TWO_AMT = re.compile(r"(\d+\.\d{2})([1-9]\d*\.\d{2})")              # "103.45103.45" = price | total
_PLAIN_AMT = re.compile(r"\d{4,}\.\d{2}")                             # "950950.00" = rate 950 | amount 950.00
_ROW_QTY = re.compile(r"\d{1,2}(\.0{1,2})?")


def _row_qty(w: dict, words: list[dict]) -> float | None:
    """Quantity printed at the left of the same row (vertical overlap), e.g. "2.00" before "CHAPATI"."""
    y0, y1 = w["box"][1], w["box"][3]
    best = None
    for u in words:
        if u is w or u["box"][2] > w["box"][0] or not _ROW_QTY.fullmatch(u["text"]):
            continue
        ov = min(y1, u["box"][3]) - max(y0, u["box"][1])
        if ov >= 0.5 * min(y1 - y0, u["box"][3] - u["box"][1]) and (best is None or u["box"][0] < best["box"][0]):
            best = u
    return float(best["text"]) if best and float(best["text"]) > 0 else None


def _column_parts(w: dict, words: list[dict]) -> list[str] | None:
    from .money import parse_money
    t = w["text"]
    m = _COL_GAP.fullmatch(t)
    # "8:000.00" is a thousands comma read as a colon, not a column gap: the right part never starts with 0
    if m and (m[2][0] != "0" or re.fullmatch(r"0\.\d{2}", m[2])):
        return [m[1], m[2]]
    m = _QTY_AMT.fullmatch(t)
    if m:
        return [m[1], m[2]]
    if parse_money(t) is not None and len(re.findall(r"[.,]", t)) >= 2:
        return None  # already a well-formed amount, e.g. "53.636.00"
    m = _TWO_AMT.fullmatch(t)
    if m:
        a, b = m[1], m[2]
        lead = a[:len(a) - len(b)]
        if a.endswith(b) and 1 <= len(lead) <= 2 and lead.isdigit():
            return [lead, b, b]  # "1405.17405.17" = qty 1 | price 405.17 | total 405.17
        return [a, b]
    if _PLAIN_AMT.fullmatch(t):
        whole = t.split(".")[0]
        qs = [q for q in (_row_qty(w, words), 1.0) if q]
        for k in range(2, len(whole) - 1):
            left, right = t[:k], t[k:]
            if right[0] != "0" and any(abs(float(left) * q - float(right)) < 0.005 for q in qs):
                return [left, right]  # rate x qty = amount
    return None


def _split_columns(words: list[dict]) -> list[dict]:
    out = []
    for w in words:
        parts = _column_parts(w, words)
        if not parts:
            out.append(w)
            continue
        x0, y0, x1, y1 = w["box"]
        n = sum(len(p) for p in parts)
        cx = x0
        for p in parts:
            dx = (x1 - x0) * len(p) / n
            out.append({**w, "text": p, "box": [cx, y0, cx + dx, y1]})
            cx += dx
    return out


def normalise_words(words: list[dict]) -> list[dict]:
    """Engine-agnostic clean-up applied to every real-OCR output (same for all models)."""
    if SPLIT_MERGED:
        words = _split_columns(words)
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
