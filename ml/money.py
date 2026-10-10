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


# OCR reads 0 as O/o/D/Q and 1 as l/I/| inside amounts ("RP3O.OOO"). Repaired only when, after an optional
# currency prefix, the token consists of digits, separators and these letters, with at least one digit (D21).
_OCR_DIGIT = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1"})
_CURRENCY = re.compile(r"^(rp\.?|idr)\s*", re.I)
_REPAIRABLE = re.compile(r"^[0-9OoDQlI|.,]*\d[0-9OoDQlI|.,]*[.,]?-?$")


# Tier 1 (D25): a colon read for the decimal point in an amount ("10320:00", never a clock time like "10:39"),
# and a final 0 read as c/C ("150.0c").
_COLON_DEC = re.compile(r"\d{3,}:\d{2}|\d{1,3}(?:[.,]\d{3})+:\d{2}")
_TRAIL_C = re.compile(r"\d[\d.,]*[.,]\d?[cC]")


def ocr_repair(text: str) -> str:
    t = text.strip()
    if _COLON_DEC.fullmatch(t):
        return t.replace(":", ".")
    if _TRAIL_C.fullmatch(t):
        return t[:-1] + "0"
    s = _CURRENCY.sub("", t)
    if s != text.strip() or any(c in s for c in "OoDQlI|"):
        if _REPAIRABLE.match(s) and sum(c.isdigit() for c in s) >= 1 and len(s) >= 2:
            return s.translate(_OCR_DIGIT)
    return text


def _well_grouped(s: str) -> bool:
    """With 2+ separators every thousands group has 3 digits, the first 1-3 digits (not a lone 0)."""
    groups = re.split(r"[.,]", s)
    th = groups[1:-1] if len(groups[-1]) in (1, 2) else groups[1:]
    return 1 <= len(groups[0]) <= 3 and not (groups[0] == "0" and th) and all(len(g) == 3 for g in th)


def parse_money(text: str | None) -> Decimal | None:
    """Return the amount as a Decimal, or None if the string holds no parseable amount."""
    if text is None:
        return None
    s = ocr_repair(str(text).strip())
    s = re.sub(r"[.,]\s*-+$", "", s)  # "25.000,-" is Indonesian for "25.000,00", not negative
    if not _HAS_DIGIT.search(s):
        return None
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")")) or s.endswith("-")
    s = _KEEP.sub("", s).replace("(", "").replace(")", "").replace("-", "")
    s = s.strip(".,")
    if not s:
        return None
    s = re.sub(r"[.,]{2,}", lambda m: m.group(0)[-1], s)  # OCR doubles a separator: "24,.000" = "24.000"
    seps = [i for i, c in enumerate(s) if c in ".,"]
    if len(seps) >= 2 and not _well_grouped(s):
        return None  # e.g. "1405.17405.17": two OCR columns glued together, not one amount (D25)
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
