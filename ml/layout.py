"""Reading order + line grouping for word boxes (same code for gold OCR and real OCR)."""
from __future__ import annotations

import math
import os
from collections import Counter
from statistics import median


# D22: straighten photos tilted >= 1.5 degrees before grouping lines, at inference. Training code switches it
# off (ml/train_crf.py, ml/cv.py): the validated setting is "train on unmodified grouping, deskew when reading".
DESKEW = os.getenv("LAYOUT_DESKEW", "1") == "1"
DESKEW_MIN = float(os.getenv("LAYOUT_DESKEW_MIN", "0.026"))  # radians (1.5 degrees): leave near-straight photos


def skew_angle(words: list[dict]) -> float:
    """Tilt (radians, +-0.1) that best aligns word centres into horizontal lines (projection profile over
    bins of half a word height). 0 unless it beats the unrotated profile by 10%."""
    if len(words) < 6:
        return 0.0
    h = median(max(1.0, w["box"][3] - w["box"][1]) for w in words)
    pts = [((w["box"][0] + w["box"][2]) / 2, (w["box"][1] + w["box"][3]) / 2) for w in words]

    def score(a):
        t = math.tan(a)
        bins = Counter(int((y - x * t) // (h / 2)) for x, y in pts)
        return sum(v * v for v in bins.values())
    base = score(0.0)
    best = max((score(a), a) for a in (i * 0.005 for i in range(-20, 21)))
    return best[1] if best[0] > 1.1 * base and abs(best[1]) >= DESKEW_MIN else 0.0


def group_lines(words: list[dict]) -> list[list[int]]:
    """Cluster word indices into visual lines (top-to-bottom), each sorted left-to-right.

    A word joins the current line if its vertical centre is within half the median
    word height of the line's running centre. With DESKEW, centres are first corrected for the
    photo's tilt (estimated from the words themselves), so a tilted label and its amount share a line.
    """
    if not words:
        return []
    heights = [max(1.0, w["box"][3] - w["box"][1]) for w in words]
    tol = 0.5 * median(heights)
    t = math.tan(skew_angle(words)) if DESKEW else 0.0
    yc = [(w["box"][1] + w["box"][3]) / 2 - (w["box"][0] + w["box"][2]) / 2 * t for w in words]
    order = sorted(range(len(words)), key=lambda i: yc[i])
    lines: list[list[int]] = []
    centres: list[float] = []
    for i in order:
        if lines and abs(yc[i] - centres[-1]) <= tol:
            lines[-1].append(i)
            n = len(lines[-1])
            centres[-1] = centres[-1] + (yc[i] - centres[-1]) / n
        else:
            lines.append([i])
            centres.append(yc[i])
    return [sorted(l, key=lambda i: words[i]["box"][0]) for l in lines]


def reading_order(words: list[dict]) -> list[dict]:
    """Return words in reading order, each annotated with line_no and pos_in_line."""
    out = []
    for ln, line in enumerate(group_lines(words)):
        for p, i in enumerate(line):
            w = dict(words[i])
            w["line_no"], w["pos_in_line"], w["line_len"] = ln, p, len(line)
            out.append(w)
    return out


def normalise_boxes(words: list[dict], width: int, height: int) -> list[list[int]]:
    """Boxes scaled to 0-1000 (LayoutLM/LiLT convention), clipped."""
    res = []
    for w in words:
        x0, y0, x1, y1 = w["box"]
        b = [int(1000 * x0 / width), int(1000 * y0 / height), int(1000 * x1 / width), int(1000 * y1 / height)]
        res.append([min(1000, max(0, v)) for v in b])
    return res
