"""Augmentation A: structure-preserving amount scaling.

Every money token on a receipt is multiplied by ONE factor, so ranks, equal values (total == subtotal)
and the arithmetic (subtotal + tax = total) all stay exactly true; each token keeps its own format
("25.000", "25,000", "Rp25.000,-", "@25.000", "(5,000)"). Labels and boxes are unchanged.
Why: perturbation test (docs/decision_log.md D16) showed the CRF partly memorises exact amounts
(total F1 0.965 -> 0.925 when amounts were scaled at test time).

Training factors and held-out test factors are disjoint, so the robustness check is not circular.
"""
from __future__ import annotations

import random
import re
from decimal import Decimal

from .money import parse_money
from .rules_baseline import is_money

TRAIN_FACTORS = [Decimal(2), Decimal(3), Decimal(10), Decimal("0.1")]
TEST_FACTORS = [Decimal(4), Decimal(7), Decimal("0.01")]
MIN_AMOUNT = 100  # quantities and tiny numbers are left alone

_TOKEN = re.compile(r"^(\D*?)(\d(?:[\d.,]*\d)?)(\D*)$")


def _render(tok: str, value: Decimal) -> str | None:
    """Write `value` in the same style as `tok` (prefix/suffix, thousands separator, decimals)."""
    m = _TOKEN.match(tok)
    if not m:
        return None
    pre, num, suf = m.groups()
    dec = re.search(r"([.,])(\d{1,2})$", num)
    body = num[: dec.start()] if dec else num
    seps = set(re.findall(r"[.,]", body))
    thou = seps.pop() if len(seps) == 1 else ""
    whole = int(abs(value))
    s = f"{whole:,}".replace(",", thou) if thou else str(whole)
    if dec:
        s += dec.group(1) + "0" * len(dec.group(2))
    return pre + s + suf


def scale_words(words: list[dict], factor: Decimal) -> list[dict] | None:
    """Copy of `words` with every amount (>= MIN_AMOUNT) multiplied by `factor`.
    Returns None if the factor would create fractions (e.g. /10 of 12,345)."""
    out = []
    changed = False
    for w in words:
        t = w["text"]
        v = parse_money(t) if is_money(t) else None
        if v is None or abs(v) < MIN_AMOUNT or v != v.to_integral_value():
            out.append(w)
            continue
        nv = abs(v) * factor
        if nv != nv.to_integral_value():
            return None
        new = _render(t, nv)
        if new is None or parse_money(new) is None or abs(parse_money(new)) != nv:
            return None
        out.append({**w, "text": new})
        changed = True
    return out if changed else None


def augment_sequences(seqs: list, k: int, seed: int = 0, factors=TRAIN_FACTORS) -> list:
    """seqs: [(key, words, width, height)] -> up to k scaled copies per sequence (labels kept)."""
    rng = random.Random(seed)
    out = []
    for key, ws, W, H in seqs:
        for f in rng.sample(factors, k=min(k, len(factors))):
            s = scale_words(ws, f)
            if s is not None:
                out.append((key, s, W, H))
    return out
