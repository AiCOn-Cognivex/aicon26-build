"""Failure taxonomy: why each receipt is not posting-correct (and why line items are wrong), real OCR.

  python -m ml.taxonomy                 # production CRF on validation + OOF predictions of `ml.cv --name base`
  python -m ml.taxonomy --cv base       # OOF only
Writes results/failure_taxonomy.json. Buckets per wrong header field (gold vs prediction, 0 = absent):
  OCR layer (the gold amount is not a token the tagger could pick):
    ocr_split_amount    2-3 adjacent tokens on one line join into the gold amount ("74." "00")
    ocr_digit_misread   a token is one digit edit away from the gold amount, or letter/digit confusion
    ocr_missed          no token close to the gold amount (not detected)
  Model / assembly layer (a token holds the gold amount):
    role_confusion      gold token tagged as ANOTHER header field, or the prediction equals another
                        gold header amount (subtotal/total/tax/service confusion)
    tagged_non_header   gold token tagged as item price / cash / change / other non-header label
    missed_field        gold token tagged O and nothing predicted for the field
    wrong_candidate     prediction is another amount on the receipt (gold token tagged O)
    spurious_field      the field is absent in gold but predicted
    parse_error         same digits as gold, parsed to a different value
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter

from .dataset import ROOT, load_split
from .fields import assemble, gold_fields
from .metrics import compare, _nonzero
from .money import parse_money
from .schema import HEADER_FIELDS

RES = ROOT / "results"
_CAT = {v: k for k, v in HEADER_FIELDS.items()}
_CONFUSE = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "i": "1", "|": "1",
                          "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6", "b": "6", "g": "9", "q": "9"})


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _val(t):
    v = parse_money(t)
    return None if v is None else abs(float(v))


def _digits(x: float) -> str:
    return str(int(round(x)))


def field_bucket(f: str, g: float | None, p: float | None, words: list[dict], gold_vals: dict) -> str:
    vals = [_val(w["text"]) for w in words]
    if g is not None:
        hits = [i for i, v in enumerate(vals) if v is not None and abs(v - g) < 0.005]
        if not hits:
            # split: join 2-3 consecutive tokens on the same visual line
            for i in range(len(words)):
                for n in (2, 3):
                    seg = words[i:i + n]
                    if len(seg) == n and len({w.get("line_no") for w in seg}) == 1:
                        v = _val("".join(w["text"] for w in seg))
                        if v is not None and abs(v - g) < 0.005:
                            return "ocr_split_amount"
            gd = _digits(g)
            for w in words:
                t = w["text"]
                if not re.search(r"\d", t):
                    continue
                v = _val(t.translate(_CONFUSE))
                if v is not None and abs(v - g) < 0.005:
                    return "ocr_digit_misread"
                d = re.sub(r"\D", "", t)
                if len(d) >= 3 and _lev(d.rstrip("0") or d, gd.rstrip("0") or gd) <= 1 and _lev(d, gd) <= 1:
                    return "ocr_digit_misread"
            return "ocr_missed"
        labs = [words[i].get("label", "O") for i in hits]
        cats = [l.split("-", 1)[1] if l != "O" else "O" for l in labs]
        if HEADER_FIELDS[f] in cats:  # the gold token carries the right label, yet the field is wrong
            if p is not None and any(abs(p - v) < 0.005 for k, v in gold_vals.items() if k != f):
                return "role_confusion"
            if p is not None and re.sub(r"\D", "", _digits(p)) == re.sub(r"\D", "", _digits(g)):
                return "parse_error"
            return "wrong_candidate"  # several candidates for the field; assembly kept another one
        if any(c in _CAT for c in cats):
            return "role_confusion"
        if p is not None and any(abs(p - v) < 0.005 for k, v in gold_vals.items() if k != f):
            return "role_confusion"
        if any(c != "O" for c in cats):
            return "tagged_non_header"
        return "missed_field" if p is None else "wrong_candidate"
    # gold absent, predicted present
    if p is not None and any(abs(p - v) < 0.005 for k, v in gold_vals.items() if k != f):
        return "role_confusion"
    return "spurious_field"


def item_buckets(pred_items, gold_items) -> list[str]:
    """Coarse line-item error types for one receipt (empty if the item multiset is exactly right)."""
    from .fields import item_key
    from .metrics import _squash
    from difflib import SequenceMatcher
    if Counter(map(item_key, pred_items)) == Counter(map(item_key, gold_items)):
        return []
    out = []
    if len(pred_items) < len(gold_items):
        out.append("items_fewer_than_gold (merge / missed)")
    elif len(pred_items) > len(gold_items):
        out.append("items_more_than_gold (split / extra)")
    used = set()
    for g in gold_items:
        best, bj = 0.0, None
        for j, p in enumerate(pred_items):
            if j in used:
                continue
            r = SequenceMatcher(None, _squash(p.get("name")), _squash(g.get("name"))).ratio()
            if p.get("price_value") == g.get("price_value"):
                r += 1
            if r > best:
                best, bj = r, j
        if bj is None:
            continue
        used.add(bj)
        p = pred_items[bj]
        if p.get("price_value") != g.get("price_value"):
            out.append("item_price_wrong")
        elif (p.get("name") or "").lower().split() != (g.get("name") or "").lower().split():
            sim = SequenceMatcher(None, _squash(p.get("name")), _squash(g.get("name"))).ratio()
            out.append("item_name_spelling (>=0.8 similar)" if sim >= 0.8 else "item_name_wrong (<0.8 similar)")
        elif p.get("qty_value") != g.get("qty_value"):
            out.append("item_qty_wrong")
    return sorted(set(out))


def analyse(rows, groups: dict | None = None) -> dict:
    """rows: [(id, tagged real-OCR words, assembled prediction, gold)]"""
    field_b, rec_b, item_b = Counter(), Counter(), Counter()
    by_field = Counter()
    failed, examples = [], {}
    tmpl = Counter()
    gsize = Counter(groups.values()) if groups else {}
    for rid, words, pred, gold in rows:
        comp = compare(pred, gold)
        templ = bool(groups) and gsize[groups[rid]] > 1
        tmpl[("templated" if templ else "singleton", comp["posting_correct"])] += 1
        gold_vals = {k: _nonzero(v)["value"] for k, v in gold["fields"].items() if _nonzero(v)}
        bs = []
        for f, ok in comp["fields"].items():
            if ok:
                continue
            g = _nonzero(gold["fields"].get(f))
            p = _nonzero(pred["fields"].get(f))
            b = field_bucket(f, g and abs(g["value"]), p and abs(p["value"]), words, gold_vals)
            bs.append((f, b))
            field_b[b] += 1
            by_field[f] += 1
            examples.setdefault(b, []).append(
                {"id": rid, "field": f, "gold": g and g["text"], "pred": p and p["text"]})
        if bs:
            failed.append({"id": rid, "wrong": bs})
            # receipt bucket = the earliest layer that failed (OCR before model)
            rec_b[min((b for _, b in bs), key=lambda b: (not b.startswith("ocr"), b))] += 1
        for b in item_buckets(pred["line_items"], gold["line_items"]):
            item_b[b] += 1
    n = len(rows)
    return {"n_receipts": n, "n_not_posting_correct": len(failed),
            "wrong_fields_by_bucket": dict(field_b.most_common()),
            "receipts_by_first_bucket": dict(rec_b.most_common()),
            "wrong_fields_by_field": dict(by_field.most_common()),
            "line_item_error_types_receipts": dict(item_b.most_common()),
            "posting_correct_by_template": {f"{k[0]}_{'ok' if k[1] else 'fail'}": v for k, v in sorted(tmpl.items())},
            "failed": failed, "examples": {k: v[:8] for k, v in examples.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", default="base")
    ap.add_argument("--no-validation", action="store_true")
    a = ap.parse_args()
    out = {}
    groups = json.loads((RES / "cv_groups.json").read_text())["groups"] if (RES / "cv_groups.json").exists() else None
    if not a.no_validation:
        from . import taggers
        from .ocr import normalise_words
        from .ocr_cache import load_cache
        _, _, fn = taggers.load("crf")
        cache = load_cache("validation")
        rows = []
        for r in load_split("validation"):
            c = cache[r["id"]]
            tagged = fn(normalise_words(c["words"]), c["width"], c["height"])
            rows.append((r["id"], tagged, assemble(tagged), gold_fields(r["gt_parse"])))
        out["production_crf_validation_modeB"] = analyse(rows, groups)
    if a.cv:
        from .cv import _records, load_preds
        recs = _records()
        rows = [(p["id"], p["B"], assemble(p["B"]), gold_fields(recs[p["id"]]["gt_parse"])) for p in load_preds(a.cv)]
        out[f"cv_{a.cv}_oof_modeB"] = analyse(rows, groups)
    (RES / "failure_taxonomy.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for k, v in out.items():
        print(f"== {k}: {v['n_not_posting_correct']}/{v['n_receipts']} not posting-correct")
        print("  wrong fields by bucket:", v["wrong_fields_by_bucket"])
        print("  receipts by first bucket:", v["receipts_by_first_bucket"])
        print("  wrong fields by field:", v["wrong_fields_by_field"])
        print("  line-item error types (receipts):", v["line_item_error_types_receipts"])
        print("  template:", v["posting_correct_by_template"])


if __name__ == "__main__":
    main()
