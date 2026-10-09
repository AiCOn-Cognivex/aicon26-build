"""Evaluation definitions (written before any numbers were reported; see docs/decision_log.md).

- Field exact match (per header field): correct if gold and prediction are both absent, or both
  present and the parsed amounts are equal (money_equal; sign of discounts ignored).
- Correct line item: normalised name (lowercase, collapsed whitespace) equal AND qty value equal
  AND price value equal. Line items are matched as multisets -> precision / recall / F1.
- Posting-correct receipt: all 5 header fields (total, subtotal, tax, service_charge, discount)
  correct. This is what an auto-post writes to the ledger, so auto-post correctness uses it.
- Fully-correct receipt: posting-correct AND the predicted line-item multiset equals gold exactly.
- STP rate: fraction of receipts auto-posted. Auto-post correctness: fraction of auto-posted
  receipts that are posting-correct.
"""
from __future__ import annotations

from collections import Counter

from .fields import item_key
from .money import money_equal
from .schema import HEADER_FIELDS


def compare(pred: dict, gold: dict) -> dict:
    per_field = {}
    for f in HEADER_FIELDS:
        p, g = pred["fields"].get(f), gold["fields"].get(f)
        if p is None and g is None:
            per_field[f] = True
        elif p is None or g is None:
            per_field[f] = False
        else:
            per_field[f] = money_equal(p["text"], g["text"])
    pc, gc = Counter(map(item_key, pred["line_items"])), Counter(map(item_key, gold["line_items"]))
    tp = sum((pc & gc).values())
    posting = all(per_field.values())
    return {
        "fields": per_field,
        "gold_present": {f: gold["fields"].get(f) is not None for f in HEADER_FIELDS},
        "items_tp": tp, "items_pred": sum(pc.values()), "items_gold": sum(gc.values()),
        "posting_correct": posting,
        "fully_correct": posting and pc == gc,
    }


def aggregate(comps: list[dict]) -> dict:
    n = len(comps)
    out = {"n_receipts": n}
    for f in HEADER_FIELDS:
        out[f"{f}_acc"] = sum(c["fields"][f] for c in comps) / n
        present = [c for c in comps if c["gold_present"][f]]
        out[f"{f}_exact_when_present"] = (sum(c["fields"][f] for c in present) / len(present)) if present else None
        out[f"{f}_n_present"] = len(present)
    tp = sum(c["items_tp"] for c in comps)
    npred = sum(c["items_pred"] for c in comps)
    ngold = sum(c["items_gold"] for c in comps)
    p = tp / npred if npred else 0.0
    r = tp / ngold if ngold else 0.0
    out.update({
        "key_field_exact_match": sum(sum(c["fields"].values()) for c in comps) / (n * len(HEADER_FIELDS)),
        "line_item_precision": p, "line_item_recall": r,
        "line_item_f1": 2 * p * r / (p + r) if p + r else 0.0,
        "posting_correct_rate": sum(c["posting_correct"] for c in comps) / n,
        "fully_correct_rate": sum(c["fully_correct"] for c in comps) / n,
    })
    return out


def stp_metrics(decisions: list[str], comps: list[dict]) -> dict:
    auto = [c for d, c in zip(decisions, comps) if d == "AUTO_POST"]
    n = len(comps)
    return {
        "stp_rate": len(auto) / n if n else 0.0,
        "n_auto": len(auto),
        "auto_post_correctness": (sum(c["posting_correct"] for c in auto) / len(auto)) if auto else None,
        "auto_post_fully_correct": (sum(c["fully_correct"] for c in auto) / len(auto)) if auto else None,
    }
