"""Reading order + line grouping for word boxes (same code for gold OCR and real OCR)."""
from __future__ import annotations

from statistics import median


def group_lines(words: list[dict]) -> list[list[int]]:
    """Cluster word indices into visual lines (top-to-bottom), each sorted left-to-right.

    A word joins the current line if its vertical centre is within half the median
    word height of the line's running centre.
    """
    if not words:
        return []
    heights = [max(1.0, w["box"][3] - w["box"][1]) for w in words]
    tol = 0.5 * median(heights)
    order = sorted(range(len(words)), key=lambda i: (words[i]["box"][1] + words[i]["box"][3]) / 2)
    lines: list[list[int]] = []
    centres: list[float] = []
    for i in order:
        yc = (words[i]["box"][1] + words[i]["box"][3]) / 2
        if lines and abs(yc - centres[-1]) <= tol:
            lines[-1].append(i)
            n = len(lines[-1])
            centres[-1] = centres[-1] + (yc - centres[-1]) / n
        else:
            lines.append([i])
            centres.append(yc)
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
