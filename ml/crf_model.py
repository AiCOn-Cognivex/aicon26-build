"""Rung 1: linear-chain CRF on token + spatial features (sklearn-crfsuite).

A CRF tags each word using hand-made features (what the word looks like, where it sits on the
page, which keywords are on its line, its neighbours) and learns which tag sequences are likely.
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path

from .layout import reading_order
from .rules_baseline import KEYWORDS, SKIP_RE, is_money, QTY_RE

_KW = [(c.split(".")[-1], rx) for c, rx in KEYWORDS]


def _shape(t: str) -> str:
    s = re.sub(r"[A-Z]", "X", t)
    s = re.sub(r"[a-z]", "x", s)
    s = re.sub(r"\d", "d", s)
    return re.sub(r"(.)\1{2,}", r"\1\1", s)[:8]


def featurise(words: list[dict], width: float, height: float) -> list[dict]:
    """words must already be in reading order with line_no / pos_in_line / line_len."""
    lines: dict[int, list[int]] = {}
    for i, w in enumerate(words):
        lines.setdefault(w["line_no"], []).append(i)
    line_text = {ln: " ".join(words[i]["text"] for i in idx) for ln, idx in lines.items()}
    n_lines = max(1, len(lines))
    feats = []
    for i, w in enumerate(words):
        t = w["text"]
        lt = line_text[w["line_no"]]
        x0, y0, x1, y1 = w["box"]
        f = {
            "bias": 1.0, "lower": t.lower()[:20], "shape": _shape(t),
            "suf3": t.lower()[-3:], "pre3": t.lower()[:3],
            "money": is_money(t), "qty": bool(QTY_RE.match(t)), "digit": t.isdigit(),
            "alpha": t.isalpha(), "upper": t.isupper(), "len": min(len(t), 10),
            "x": round(x0 / width, 1), "xr": round(x1 / width, 1), "y": round(y0 / height, 1),
            "line_frac": round(w["line_no"] / n_lines, 1),
            "first_in_line": w["pos_in_line"] == 0,
            "last_in_line": w["pos_in_line"] == w["line_len"] - 1,
            "line_len": min(w["line_len"], 6),
            "line_skip_kw": bool(SKIP_RE.search(lt)),
            "line_first": words[lines[w["line_no"]][0]]["text"].lower()[:12],
        }
        for name, rx in _KW:
            f[f"kw_{name}"] = bool(rx.search(lt))
        for off in (-2, -1, 1, 2):
            j = i + off
            if 0 <= j < len(words):
                f[f"{off}:lower"] = words[j]["text"].lower()[:20]
                f[f"{off}:money"] = is_money(words[j]["text"])
                f[f"{off}:sameline"] = words[j]["line_no"] == w["line_no"]
            else:
                f[f"{off}:pad"] = True
        # keywords on the previous line help for amounts printed under their label
        prev = line_text.get(w["line_no"] - 1, "")
        for name, rx in _KW:
            f[f"prev_kw_{name}"] = bool(rx.search(prev))
        feats.append(f)
    return feats


class CRFTagger:
    def __init__(self, c1: float = 0.05, c2: float = 0.05, max_iter: int = 200):
        import sklearn_crfsuite
        self.crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=c1, c2=c2, max_iterations=max_iter,
                                        all_possible_transitions=True)

    def fit(self, X, y):
        self.crf.fit(X, y)
        return self

    def tag(self, words: list[dict], width: float, height: float) -> list[dict]:
        """words (any order) -> reading-order words with label + prob (marginal of chosen label)."""
        ws = reading_order(words)
        if not ws:
            return []
        X = featurise(ws, width, height)
        labels = self.crf.predict_single(X)
        marg = self.crf.predict_marginals_single(X)
        for w, lab, m in zip(ws, labels, marg):
            w["label"], w["prob"] = lab, float(m[lab])
            w["probs"] = m
        return ws

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.crf, f)

    @classmethod
    def load(cls, path: Path) -> "CRFTagger":
        obj = cls.__new__(cls)
        with open(path, "rb") as f:
            obj.crf = pickle.load(f)
        return obj
