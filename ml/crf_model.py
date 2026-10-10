"""Rung 1: linear-chain CRF on token + spatial features (sklearn-crfsuite).

A CRF tags each word using hand-made features (what the word looks like, where it sits on the
page, which keywords are on its line, its neighbours) and learns which tag sequences are likely.
"""
from __future__ import annotations

import math
import os
import pickle
import re
from pathlib import Path

from .layout import reading_order
from .money import parse_money
from .rules_baseline import KEYWORDS, SKIP_RE, is_money, QTY_RE

_KW = [(c.split(".")[-1], rx) for c, rx in KEYWORDS]
# Tier 1 (D25), inference only: label words of other receipt styles (Pakistan: "Net Bill", SST/GST/PST) and labels
# OCR misspelled by one letter ("Totnl", "SubTatal") switch on the SAME keyword features the CRF learned on CORD.
# Training code turns this off (ml/train_crf.py, ml/cv.py), as the production model was trained without it.
EXTRA_KEYWORDS = os.getenv("EXTRA_KEYWORDS", "1") == "1"
_KW_EXTRA = {
    "subtotal_price": re.compile(r"gross\s*(amount|total)", re.I),
    "tax_price": re.compile(r"\bsst\b|\bgst\b|\bpst\b|\bfed\b|sales\s*tax|\bs\.\s*s\.\s*t\b|\bg\.\s*s\.\s*t\b", re.I),
    "service_price": re.compile(r"service\s*charges?|\bs\s*/\s*c\b", re.I),
    "total_price": re.compile(r"net\s*bill|bill\s*amount|total\s*bill|net\s*payable|\bpayable\b|amount\s*due|"
                              r"net\s*amount|net\s*total", re.I),
}


def _kw_names(text: str) -> set[str]:
    """Header keyword classes on a line of text (base CORD keywords; plus the Tier 1 extension)."""
    hits = {name for name, rx in _KW if rx.search(text)}
    if EXTRA_KEYWORDS and text:
        canon = " ".join(_canon(t) for t in text.split())
        hits |= {name for name, rx in _KW if rx.search(canon)}
        hits |= {name for name, rx in _KW_EXTRA.items() if rx.search(text) or rx.search(canon)}
    return hits


def _shape(t: str) -> str:
    s = re.sub(r"[A-Z]", "X", t)
    s = re.sub(r"[a-z]", "x", s)
    s = re.sub(r"\d", "d", s)
    return re.sub(r"(.)\1{2,}", r"\1\1", s)[:8]


def _amount_context(words: list[dict]) -> list[dict]:
    """Receipt-level context for money tokens: rank of the amount on the receipt,
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


# v3: OCR-robust keywords. "T0TAL", "SUBT0TAL", "TOTAI" are read as the keyword they are one edit away from.
_CANON = ["total", "subtotal", "tax", "service", "discount", "cash", "change", "kembali", "kembalian", "tunai",
          "jumlah", "grand", "pajak", "card", "debit", "charge", "items", "qty", "item"]
_LETTERS = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b", "|": "l", "$": "s"})
_KW3 = _KW + [("cash", re.compile(r"cash|tunai|bayar|paid|tendered", re.I)),
              ("change", re.compile(r"change|kembali", re.I)),
              ("card", re.compile(r"card|debit|credit|kartu|bca|edc", re.I)),
              ("count", re.compile(r"qty|items?|jumlah item", re.I))]


def _lev1(a: str, b: str) -> bool:
    """Levenshtein distance <= 1."""
    if abs(len(a) - len(b)) > 1:
        return False
    i = j = d = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        d += 1
        if d > 1:
            return False
        if len(a) > len(b):
            i += 1
        elif len(b) > len(a):
            j += 1
        else:
            i += 1
            j += 1
    return d + (len(a) - i) + (len(b) - j) <= 1


def _canon(t: str) -> str:
    w0 = t.lower().strip(".,:;=*()[]")
    for w in (w0, w0.translate(_LETTERS) if any(c.isalpha() for c in w0) else w0):
        if len(w) >= 4:
            for k in _CANON:
                if w == k or (len(k) >= 4 and _lev1(w, k)):
                    return k
    return w0


def _kw_class(text: str) -> str:
    for name, rx in _KW3:
        if rx.search(text):
            return name
    return "none"


def _v3(words: list[dict], width: float, height: float) -> list[dict]:
    """Extra v3 features: canonical keywords on the line, nearest word to the left on the same physical row
    (vertical overlap, robust to skew), amount position from the bottom, keyword lines sharing the value."""
    canon = [_canon(w["text"]) for w in words]
    lines: dict[int, list[int]] = {}
    for i, w in enumerate(words):
        lines.setdefault(w["line_no"], []).append(i)
    ltext = {ln: " ".join(canon[i] for i in idx) for ln, idx in lines.items()}
    lkw = {ln: _kw_class(t) for ln, t in ltext.items()}
    vals = [parse_money(w["text"]) if is_money(w["text"]) else None for w in words]
    money = [i for i, v in enumerate(vals) if v is not None and v != 0]
    by_val: dict = {}
    for i in money:
        by_val.setdefault(abs(vals[i]), []).append(i)
    out = []
    for i, w in enumerate(words):
        x0, y0, x1, y1 = w["box"]
        h = max(1.0, y1 - y0)
        left, lx = None, -1e9
        for j, u in enumerate(words):
            if j == i or u["box"][2] > x0 + 0.25 * h or not any(c.isalpha() for c in u["text"]):
                continue
            ov = min(y1, u["box"][3]) - max(y0, u["box"][1])
            if ov >= 0.5 * min(h, max(1.0, u["box"][3] - u["box"][1])) and u["box"][2] > lx:
                left, lx = j, u["box"][2]
        f = {"c_kw_line": lkw[w["line_no"]], "c_kw_prev": lkw.get(w["line_no"] - 1, "none"),
             "c_kw_next": lkw.get(w["line_no"] + 1, "none"), "c_word": canon[i][:12],
             "row_left": "none" if left is None else canon[left][:12],
             "row_left_kw": "none" if left is None else _kw_class(canon[left]),
             "h_rel": str(round(min(3.0, h / max(1.0, height) * 50), 1))}
        if i in money:
            k = len(money) - money.index(i) - 1
            f["amt_from_bottom"] = str(min(k, 5))
            for j in by_val[abs(vals[i])]:
                if j != i:
                    f[f"same_val_on_{lkw[words[j]['line_no']]}"] = True
        out.append(f)
    return out


def featurise(words: list[dict], width: float, height: float, features: str = "v2") -> list[dict]:
    """words must already be in reading order with line_no / pos_in_line / line_len."""
    lines: dict[int, list[int]] = {}
    for i, w in enumerate(words):
        lines.setdefault(w["line_no"], []).append(i)
    line_text = {ln: " ".join(words[i]["text"] for i in idx) for ln, idx in lines.items()}
    kw_line = {ln: _kw_names(t) for ln, t in line_text.items()}
    n_lines = max(1, len(lines))
    ctx = _amount_context(words)
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
        for name, _ in _KW:
            f[f"kw_{name}"] = name in kw_line[w["line_no"]]
        for off in (-2, -1, 1, 2):
            j = i + off
            if 0 <= j < len(words):
                f[f"{off}:lower"] = words[j]["text"].lower()[:20]
                f[f"{off}:money"] = is_money(words[j]["text"])
                f[f"{off}:sameline"] = words[j]["line_no"] == w["line_no"]
            else:
                f[f"{off}:pad"] = True
        # keywords on the previous line help for amounts printed under their label
        prev, nxt = kw_line.get(w["line_no"] - 1, set()), kw_line.get(w["line_no"] + 1, set())
        for name, _ in _KW:
            f[f"prev_kw_{name}"] = name in prev
            f[f"next_kw_{name}"] = name in nxt
        f.update(ctx[i])
        feats.append(f)
    if features == "v3":
        for f, g in zip(feats, _v3(words, width, height)):
            f.update(g)
    return feats


FEATURES = "v2"  # production feature-set version stored in the pickle; v1 (no amount context) is in git history
FEATURE_SETS = ("v2", "v3")


class CRFTagger:
    def __init__(self, c1: float = 0.5, c2: float = 0.1, max_iter: int = 200, algorithm: str = "lbfgs",
                 features: str = FEATURES):
        import sklearn_crfsuite
        kw = {"c1": c1, "c2": c2} if algorithm == "lbfgs" else {"c2": c2} if algorithm == "l2sgd" else {}
        self.crf = sklearn_crfsuite.CRF(algorithm=algorithm, max_iterations=max_iter,
                                        all_possible_transitions=True, **kw)
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
        X = featurise(ws, width, height, features=self.features)
        labels = self.crf.predict_single(X)
        marg = self.crf.predict_marginals_single(X)
        T = self.T
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
            d = pickle.load(f)
        if not isinstance(d, dict) or d.get("features") not in FEATURE_SETS:
            raise ValueError(f"{path}: CRF saved with an unknown feature set; retrain with python -m ml.train_crf")
        obj.crf, obj.T, obj.features = d["crf"], 1.0, d["features"]
        return obj
