"""Profile CORD v2 from the real data. Fits the rare-label merge on TRAIN only.

Writes: results/data_profile.md, results/data_quality.json, data/label_map.json, data/LABELS.md
Usage: python data/profile_cord.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml.dataset import load_split, image_path  # noqa: E402
from ml.fields import gold_fields  # noqa: E402
from ml.money import parse_money  # noqa: E402
from ml.schema import HEADER_FIELDS, HEADER_GT  # noqa: E402

RARE_MIN = 10
SPLITS = ("train", "validation", "test")


def money_shape(s: str) -> str:
    s = re.sub(r"\d", "9", s)
    return re.sub(r"9+", lambda m: "9" * min(len(m.group()), 3), s)


def main():
    res_dir = ROOT / "results"
    res_dir.mkdir(exist_ok=True)
    quality = {"splits": {}}
    cat_entities = {s: Counter() for s in SPLITS}
    cat_words = {s: Counter() for s in SPLITS}
    field_presence = {s: Counter() for s in SPLITS}
    shapes = Counter()
    parse_fail = []
    recon = defaultdict(Counter)
    recon_examples = defaultdict(list)
    img_hash = defaultdict(list)
    text_hash = defaultdict(list)
    n_words = {}
    for s in SPLITS:
        recs = load_split(s)
        issues = [{"id": r["id"], "issues": r["issues"]} for r in recs if r["issues"]]
        issue_types = Counter(re.sub(r"'.*'|\d+", "#", i) for r in recs for i in r["issues"])
        nw = [len(r["words"]) for r in recs]
        n_words[s] = nw
        quality["splits"][s] = {
            "n_receipts": len(recs), "n_with_issues": len(issues),
            "issue_types": dict(issue_types.most_common()), "examples": issues[:15],
            "words_per_receipt": {"min": min(nw), "median": sorted(nw)[len(nw) // 2], "max": max(nw)},
        }
        for r in recs:
            seen = set()
            for w in r["words"]:
                cat_words[s][w["category"]] += 1
                if w["line_idx"] not in seen:
                    seen.add(w["line_idx"])
                    cat_entities[s][w["category"]] += 1
            g = gold_fields(r["gt_parse"])
            for f, (sec, key) in HEADER_GT.items():  # raw gold values with no amount (e.g. "-")
                raw = (r["gt_parse"].get(sec) or {}) if isinstance(r["gt_parse"].get(sec), dict) else {}
                rv = raw.get(key)
                rv = rv[0] if isinstance(rv, list) and rv else rv
                if rv is not None and parse_money(rv) is None:
                    parse_fail.append({"id": r["id"], "field": f, "text": rv})
            for f in HEADER_FIELDS:
                if g["fields"][f] is not None:
                    field_presence[s][f] += 1
                    txt = g["fields"][f]["text"]
                    if s == "train":
                        shapes[money_shape(txt)] += 1
            field_presence[s]["line_items>0"] += bool(g["line_items"])
            # does the arithmetic hold on GOLD values? (sets the reconciliation rules)
            v = {f: (g["fields"][f]["value"] if g["fields"][f] else None) for f in HEADER_FIELDS}
            if v["total"] is not None and v["subtotal"] is not None:
                exp = v["subtotal"] + (v["tax"] or 0) + (v["service_charge"] or 0) - abs(v["discount"] or 0)
                d = abs(exp - v["total"])
                key = "exact" if d < 0.01 else ("<=1%" if d <= 0.01 * v["total"] else "fail")
                recon["sub+tax+svc-disc=total"][key] += 1
                if key == "fail" and len(recon_examples["sub+tax+svc-disc=total"]) < 8:
                    recon_examples["sub+tax+svc-disc=total"].append({"id": r["id"], **v, "expected": exp})
            else:
                recon["sub+tax+svc-disc=total"]["not_checkable"] += 1
            prices = [it["price_value"] for it in g["line_items"] if it["price_value"] is not None]
            if prices and v["subtotal"] is not None:
                d = abs(sum(prices) - v["subtotal"])
                recon["sum(items)=subtotal"]["exact" if d < 0.01 else "fail"] += 1
            else:
                recon["sum(items)=subtotal"]["not_checkable"] += 1
            # duplicates across splits
            with open(image_path(r), "rb") as f:
                img_hash[hashlib.md5(f.read()).hexdigest()].append(r["id"])
            text_hash[hashlib.md5(" ".join(w["text"] for w in r["words"]).encode()).hexdigest()].append(r["id"])

    dup_img = [v for v in img_hash.values() if len({x.split("_")[0] for x in v}) > 1]
    dup_txt = [v for v in text_hash.values() if len({x.split("_")[0] for x in v}) > 1]
    within_dup = [v for v in text_hash.values() if len(v) > 1 and len({x.split("_")[0] for x in v}) == 1]

    # rare-label merge, fitted on train only
    train_c = cat_entities["train"]
    all_cats = sorted(set().union(*[set(c) for c in cat_entities.values()]))
    key_cats = set(HEADER_FIELDS.values()) | {"menu.nm", "menu.cnt", "menu.price"}
    lmap = {}
    for c in all_cats:
        if train_c[c] >= RARE_MIN or c in key_cats:
            lmap[c] = c
        else:
            parent = c.split(".")[0] + ".etc"
            lmap[c] = parent if train_c[parent] >= RARE_MIN and parent != c else "O"
    (ROOT / "data" / "label_map.json").write_text(json.dumps(
        {"rare_min_train_entities": RARE_MIN, "map": lmap}, indent=1), encoding="utf-8")

    quality.update({
        "money_parse_failures_in_gold": parse_fail,
        "cross_split_duplicate_images": dup_img,
        "cross_split_duplicate_word_sequences": dup_txt,
        "within_split_duplicate_word_sequences": within_dup,
        "gold_reconciliation": {k: dict(v) for k, v in recon.items()},
        "gold_reconciliation_fail_examples": dict(recon_examples),
        "field_presence": {s: dict(field_presence[s]) for s in SPLITS},
        "category_entities": {s: dict(cat_entities[s]) for s in SPLITS},
    })
    (res_dir / "data_quality.json").write_text(json.dumps(quality, indent=1, ensure_ascii=False), encoding="utf-8")

    # ---- markdown report
    L = ["# CORD v2 data profile", "",
         "Generated by `data/profile_cord.py` from the downloaded data (not hand-written).", "",
         "## Splits (official, unchanged)", "", "| split | receipts | with issues | words/receipt (min/median/max) |", "|---|---|---|---|"]
    for s in SPLITS:
        q = quality["splits"][s]
        w = q["words_per_receipt"]
        L.append(f"| {s} | {q['n_receipts']} | {q['n_with_issues']} | {w['min']}/{w['median']}/{w['max']} |")
    L += ["", "Issue types (logged, records kept): " + "; ".join(
        f"{s}: {quality['splits'][s]['issue_types'] or 'none'}" for s in SPLITS), "",
        "## Key field presence (receipts with the field in gold)", "",
        "| field | " + " | ".join(SPLITS) + " |", "|---|---|---|---|"]
    for f in list(HEADER_FIELDS) + ["line_items>0"]:
        L.append(f"| {f} | " + " | ".join(f"{field_presence[s][f]}/{len(n_words[s])}" for s in SPLITS) + " |")
    L += ["", "## Money formats (train gold header amounts, digit runs collapsed to <=3 nines)", "",
          "| shape | count |", "|---|---|"]
    L += [f"| `{k}` | {v} |" for k, v in shapes.most_common(15)]
    L += ["", f"Gold header values with no parseable amount (treated as absent): {len(parse_fail)} " +
          (str([p['text'] for p in parse_fail[:10]]) if parse_fail else ""), "",
          "## Does the arithmetic hold in the gold labels?", ""]
    for k, v in recon.items():
        L.append(f"- `{k}`: {dict(v)}")
    L += ["", "## Duplicates", "",
          f"- Identical images across splits: {len(dup_img)}",
          f"- Identical word sequences across splits: {len(dup_txt)} {dup_txt[:5]}",
          f"- Identical word sequences within a split: {len(within_dup)} {within_dup[:5]}", "",
          "## Categories (entity count = annotated lines)", "", "| category | train | val | test | trained as |", "|---|---|---|---|---|"]
    for c in sorted(all_cats, key=lambda c: -train_c[c]):
        L.append(f"| {c} | {cat_entities['train'][c]} | {cat_entities['validation'][c]} | {cat_entities['test'][c]} | {lmap[c]} |")
    (res_dir / "data_profile.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    merged = {c: m for c, m in lmap.items() if c != m}
    lab = ["# Label set", "",
           f"Token labels are the CORD v2 categories with BIO tags. Categories with fewer than {RARE_MIN} annotated",
           "entities in TRAIN are merged into their section's `.etc` label (or `O` if that is also rare).",
           "Key accounting categories are never merged. The merge is computed on train only by `data/profile_cord.py`.", "",
           f"Kept: {len([c for c in lmap if lmap[c] == c])} categories. Merged: {len(merged)}.", "",
           "| original | train entities | merged into |", "|---|---|---|"]
    lab += [f"| {c} | {train_c[c]} | {m} |" for c, m in merged.items()]
    (ROOT / "data" / "LABELS.md").write_text("\n".join(lab) + "\n", encoding="utf-8")
    print((res_dir / "data_profile.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
