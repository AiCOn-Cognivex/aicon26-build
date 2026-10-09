"""Rung 0 ("before"): OCR + keyword/regex rules, i.e. what template-based tools do today.

For each visual line: if it contains a keyword (TOTAL, SUBTOTAL, TAX/PB1/PPN, SERVICE, DISC),
the right-most money token on that line is that field. Lines above the first summary line
that end in a money token are line items (leading small integer = qty, rest = name).
Rules have no probabilities, so every tag gets prob=1.0.
"""
from __future__ import annotations

import re

from .layout import group_lines

MONEY_RE = re.compile(r"^[@(\-]?(rp\.?)?[@(\-]?\d{1,3}([.,]\d{3})+([.,]\d{1,2})?[)\-]?$|^[@(\-]?(rp\.?)?\d{3,}([.,]\d{1,2})?[)\-]?$", re.I)
QTY_RE = re.compile(r"^(x?\d{1,2}x?|\d{1,2}(pcs|pc)?)$", re.I)

KEYWORDS = [  # order matters: more specific first
    ("sub_total.subtotal_price", re.compile(r"sub\s*-?\s*t(o)?t(a)?l|subttl|sub total", re.I)),
    ("sub_total.tax_price", re.compile(r"\btax\b|pb\s*1|\bppn\b|pajak|\bvat\b|\bpb\b|restaurant tax", re.I)),
    ("sub_total.service_price", re.compile(r"service|\bsvc\b|\bserv\b|s\.?charge|\bsc\b", re.I)),
    ("sub_total.discount_price", re.compile(r"disc|diskon|potongan|promo|voucher", re.I)),
    ("total.total_price", re.compile(r"\btotal\b|\bttl\b|grand\s*total|jumlah|tagihan|amount", re.I)),
]
SKIP_RE = re.compile(r"cash|tunai|change|kembali|card|debit|credit|bayar|paid|payment|qty|item", re.I)


def is_money(t: str) -> bool:
    return bool(MONEY_RE.match(t.strip().replace(" ", "")))


def tag(words: list[dict]) -> list[dict]:
    """words (any order) -> words in reading order with BIO labels and prob."""
    lines = group_lines(words)
    out_lines = []
    summary_started = False
    for line in lines:
        ws = [dict(words[i], label="O", prob=1.0) for i in line]
        text = " ".join(w["text"] for w in ws)
        money_idx = [k for k, w in enumerate(ws) if is_money(w["text"])]
        cat = None
        for c, rx in KEYWORDS:
            if rx.search(text):
                cat = c
                break
        if cat and money_idx and not (cat == "total.total_price" and SKIP_RE.search(text)):
            summary_started = True
            ws[money_idx[-1]]["label"] = f"B-{cat}"
        elif cat or SKIP_RE.search(text):
            summary_started = summary_started or bool(cat)
        elif not summary_started and money_idx and money_idx[-1] == len(ws) - 1 and len(ws) >= 2:
            # candidate line item: [qty] name ... price
            p = money_idx[-1]
            ws[p]["label"] = "B-menu.price"
            start = 0
            if QTY_RE.match(ws[0]["text"]) and p > 1:
                ws[0]["label"] = "B-menu.cnt"
                start = 1
            name_toks = [k for k in range(start, p) if not is_money(ws[k]["text"])]
            if not name_toks or not any(ch.isalpha() for k in name_toks for ch in ws[k]["text"]):
                for w in ws:
                    w["label"] = "O"
            else:
                for j, k in enumerate(name_toks):
                    ws[k]["label"] = ("B-" if j == 0 else "I-") + "menu.nm"
        out_lines.append(ws)
    return [w for l in out_lines for w in l]
