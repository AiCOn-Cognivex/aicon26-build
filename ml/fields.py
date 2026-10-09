"""Turn token-level predictions into structured receipt fields, and read gold fields from CORD.

Every extractor (rules, CRF, transformer) produces a list of tagged words:
    {"text", "box", "label" (BIO tag, e.g. "B-total.total_price" or "O"), "prob" (0-1)}
and `assemble()` turns that into the same output structure, so evaluation and the
decision layer are identical across rungs.

Field confidence is conservative: the MINIMUM token probability inside the entity
(one doubtful token makes the whole field doubtful).
"""
from __future__ import annotations

from .money import parse_money, to_float, norm_text
from .schema import HEADER_FIELDS, HEADER_GT, ITEM_LABELS

_CAT_TO_FIELD = {v: k for k, v in HEADER_FIELDS.items()}


def entities(tagged: list[dict]) -> list[dict]:
    """Group BIO-tagged words (in reading order) into entities."""
    ents, cur = [], None
    for w in tagged:
        lab = w.get("label", "O")
        if lab == "O":
            cur = None
            continue
        tag, cat = lab.split("-", 1)
        if tag == "B" or cur is None or cur["category"] != cat:
            cur = {"category": cat, "words": [], "probs": [], "boxes": []}
            ents.append(cur)
        cur["words"].append(w["text"])
        cur["probs"].append(float(w.get("prob", 1.0)))
        cur["boxes"].append(w.get("box"))
    for e in ents:
        e["text"] = " ".join(e["words"])
        e["confidence"] = min(e["probs"]) if e["probs"] else 0.0
    return ents


def assemble(tagged: list[dict]) -> dict:
    """Tagged words -> {fields: {name: {text, value, confidence}}, line_items: [...]}."""
    ents = entities(tagged)
    fields: dict[str, dict | None] = {k: None for k in HEADER_FIELDS}
    for e in ents:
        f = _CAT_TO_FIELD.get(e["category"])
        if f is None or parse_money(e["text"]) is None:
            continue
        # several candidates: keep the most confident (ties -> later on the receipt)
        if fields[f] is None or e["confidence"] >= fields[f]["confidence"]:
            fields[f] = {"text": e["text"], "value": to_float(parse_money(e["text"])),
                         "confidence": round(e["confidence"], 4)}

    items, cur = [], None
    for e in ents:
        slot = ITEM_LABELS.get(e["category"])
        if slot is None:
            continue
        if cur is None or cur.get(slot) is not None:
            cur = {"name": None, "qty": None, "price": None, "confidence": 1.0}
            items.append(cur)
        cur[slot] = e["text"]
        cur["confidence"] = round(min(cur["confidence"], e["confidence"]), 4)
    for it in items:
        it["price_value"] = to_float(parse_money(it["price"]))
        it["qty_value"] = _qty(it["qty"])
    return {"fields": fields, "line_items": items}


def _qty(s):
    if s is None:
        return None
    d = parse_money(str(s).lower().replace("x", ""))
    return to_float(d)


def _first(v):
    """gt_parse values can be a string or a list of strings."""
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def gold_fields(gt_parse: dict) -> dict:
    """Gold header fields + line items from CORD gt_parse (the evaluation reference)."""
    fields = {}
    for f, (sec, key) in HEADER_GT.items():
        section = gt_parse.get(sec)
        if isinstance(section, list):  # rare: section stored as a list
            section = section[0] if section else {}
        val = _first((section or {}).get(key))
        # a gold value with no digits (6 cases of "-") means "no amount": treated as absent
        fields[f] = None if val is None or parse_money(val) is None else {"text": val, "value": to_float(parse_money(val))}
    items = []
    for m in _as_list(gt_parse.get("menu")):
        if not isinstance(m, dict):
            continue
        nm, cnt, price = _first(m.get("nm")), _first(m.get("cnt")), _first(m.get("price"))
        if nm is None and price is None:
            continue
        items.append({"name": nm, "qty": cnt, "price": price,
                      "price_value": to_float(parse_money(price)), "qty_value": _qty(cnt)})
    return {"fields": fields, "line_items": items}


def item_key(it: dict) -> tuple:
    """Canonical key for line-item exact match: normalised name, qty value, price value."""
    return (norm_text(it.get("name")), it.get("qty_value"), it.get("price_value"))
