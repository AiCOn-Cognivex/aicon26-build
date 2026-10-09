"""Rung 1: linear-chain CRF on token + spatial features (sklearn-crfsuite).

A CRF tags each word using hand-made features (what the word looks like, where it sits on the
page, which keywords are on its line, its neighbours) and learns which tag sequences are likely.
"""
from __future__ import annotations

import math
import pickle
import re
from pathlib import Path

from .layout import reading_order
from .money import parse_money
from .rules_baseline import KEYWORDS, SKIP_RE, is_money, QTY_RE

_KW = [(c.split(".")[-1], rx) for c, rx in KEYWORDS]


def _shape(t: str) -> str:
    s = re.sub(r"[A-Z]", "X", t)
    s = re.sub(r"[a-z]", "x", s)
    s = re.sub(r"\d", "d", s)
    return re.sub(r"(.)\1{2,}", r"\1\1", s)[:8]


def _amount_context(words: list[dict]) -> list[dict]:
    """Receipt-level context for money tokens (feature set v2): rank of the amount on the receipt,
    whether the same value appears elsewhere, size relative to the largest amount, and
    position among the amounts on its line."""
    vals = [parse_money(w["text"]) if is_money(w["text"]) else None for w in words]
    nums = [abs(v) for v in vals if v is not None and v != 0]
    distinct = sorted(set(nums), reverse=True)
    vmax = distinct[0] if distinct else None
    per_line: dict[int, list[int]] = {}
    for i, v in enumerate(vals):
        if v is not None:
            per_line.setdefault(words[i]["line_no"], []).append(i)
    out = []
    for i, v in enumerate(vals):
        if v is None or v == 0 or vmax is None:
            out.append({"amt": False})
            continue
        a = abs(v)
        rank = distinct.index(a) + 1
        line_m = per_line[words[i]["line_no"]]
        out.append({
            "amt": True, "amt_rank": str(min(rank, 4)), "amt_is_max": rank == 1,
            "amt_repeats": nums.count(a) > 1, "amt_mag": str(len(str(int(a)))),
            "amt_rel": str(round(float(a / vmax), 1)),
            "amt_last_on_line": line_m[-1] == i, "amt_n_on_line": str(min(len(line_m), 3)),
        })
    return out


def featurise(words: list[dict], width: float, height: float, version: str = "v2") -> list[dict]:
    """words must already be in reading order with line_no / pos_in_line / line_len."""
    lines: dict[int, list[int]] = {}
    for i, w in enumerate(words):
        lines.setdefault(w["line_no"], []).append(i)
    line_text = {ln: " ".join(words[i]["text"] for i in idx) for ln, idx in lines.items()}
    n_lines = max(1, len(lines))
    ctx = _amount_context(words) if version == "v2" else None
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
        if version == "v2":
            nxt = line_text.get(w["line_no"] + 1, "")
            for name, rx in _KW:
                f[f"next_kw_{name}"] = bool(rx.search(nxt))
            f.update(ctx[i])
        feats.append(f)
    return feats


class CRFTagger:
    def __init__(self, c1: float = 0.05, c2: float = 0.05, max_iter: int = 200, features: str = "v2"):
        import sklearn_crfsuite
        self.crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=c1, c2=c2, max_iterations=max_iter,
                                        all_possible_transitions=True)
        self.features = features
        self.T = 1.0

    def fit(self, X, y):
        self.crf.fit(X, y)
        return self

    def tag(self, words: list[dict], width: float, height: float) -> list[dict]:
        """words (any order) -> reading-order words with label + prob (marginal of chosen label)."""
        ws = reading_order(words)
        if not ws:
            return []
        X = featurise(ws, width, height, getattr(self, "features", "v1"))
        labels = self.crf.predict_single(X)
        marg = self.crf.predict_marginals_single(X)
        T = getattr(self, "T", 1.0)
        for w, lab, m in zip(ws, labels, marg):
            if T != 1.0:  # temperature scaling of the marginals (fitted on validation)
                logs = {k: math.log(max(v, 1e-12)) / T for k, v in m.items()}
                mx = max(logs.values())
                ex = {k: math.exp(v - mx) for k, v in logs.items()}
                z = sum(ex.values())
                m = {k: v / z for k, v in ex.items()}
            w["label"], w["prob"] = lab, float(m[lab])
            w["probs"] = m
        return ws

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"crf": self.crf, "features": self.features}, f)

    @classmethod
    def load(cls, path: Path) -> "CRFTagger":
        obj = cls.__new__(cls)
        with open(path, "rb") as f:
            obj.crf = pickle.load(f)
        if isinstance(obj.crf, dict):  # versioned format
            obj.features, obj.crf = obj.crf["features"], obj.crf["crf"]
        else:  # models saved before feature versioning used v1
            obj.features = "v1"
        obj.T = 1.0
        return obj
