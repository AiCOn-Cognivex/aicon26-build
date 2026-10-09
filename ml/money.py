"""Single money parser used everywhere (data profiling, baselines, models, evaluation, API).

CORD receipts are Indonesian: "." is usually the thousands separator ("25.000" = 25000),
"," is sometimes thousands ("25,000") and sometimes decimal ("25.000,00").
Rule: the LAST separator is a decimal point only if it is followed by 1-2 digits;
a final group of exactly 3 digits means thousands.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_KEEP = re.compile(r"[^0-9.,\-()]")
_HAS_DIGIT = re.compile(r"\d")


def parse_money(text: str | None) -> Decimal | None:
    """Return the amount as a Decimal, or None if the string holds no parseable amount."""
    if text is None:
        return None
    s = str(text).strip()
    s = re.sub(r"[.,]\s*-+$", "", s)  # "25.000,-" is Indonesian for "25.000,00", not negative
    if not _HAS_DIGIT.search(s):
        return None
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")")) or s.endswith("-")
    s = _KEEP.sub("", s).replace("(", "").replace(")", "").replace("-", "")
    s = s.strip(".,")
    if not s:
        return None
    seps = [i for i, c in enumerate(s) if c in ".,"]
    if seps:
        last = seps[-1]
        tail = s[last + 1:]
        if len(tail) in (1, 2):
            # decimal separator at `last`; every other separator is thousands
            whole = re.sub(r"[.,]", "", s[:last])
            s = f"{whole or '0'}.{tail}"
        else:
            s = re.sub(r"[.,]", "", s)
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def money_equal(a: str | Decimal | None, b: str | Decimal | None) -> bool:
    """Exact match on parsed value; falls back to normalised string compare if unparseable."""
    pa = a if isinstance(a, Decimal) else parse_money(a)
    pb = b if isinstance(b, Decimal) else parse_money(b)
    if pa is not None and pb is not None:
        return abs(pa) == abs(pb)  # sign conventions for discounts vary ("-5.000" vs "5.000")
    return norm_text(a) == norm_text(b)


def norm_text(s) -> str:
    return " ".join(str(s or "").lower().split())


def to_float(d: Decimal | None) -> float | None:
    return None if d is None else float(d)
