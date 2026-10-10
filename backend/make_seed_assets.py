"""Build backend/seed_assets/: a few CORD v2 TEST receipts (CC-BY-4.0; the final model
trains on train + validation, decision log D23) with the model's real output,
used as the images of seeded demo claims. Receipts used as public demo samples (frontend/public/demo) are
excluded, so a judge uploading a sample is not flagged as a duplicate of a seeded claim.

  python backend/make_seed_assets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml import predict as P  # noqa: E402
from ml.dataset import image_path, load_split  # noqa: E402
from ml.ocr import load_image, normalise_words  # noqa: E402
from ml.ocr_cache import load_cache  # noqa: E402

OUT = ROOT / "backend" / "seed_assets"
DEMO = {p.stem for p in (ROOT / "frontend" / "public" / "demo").glob("test_*.jpg")}
WANT_AUTO, WANT_REVIEW = 4, 3


def main():
    OUT.mkdir(exist_ok=True)
    cache = load_cache("test")
    picked, n_auto, n_rev = [], 0, 0
    for rec in load_split("test"):
        name = f"test_{rec['idx']}"
        if name in DEMO:
            continue
        c = cache[rec["id"]]
        res = P.predict_words(normalise_words(c["words"]), c["width"], c["height"])
        total = res["fields"].get("total")
        if total is None or (total["value"] or 0) < 1000:
            continue
        auto = res["decision"] == "AUTO_POST"
        if (auto and n_auto >= WANT_AUTO) or (not auto and n_rev >= WANT_REVIEW):
            continue
        n_auto += auto
        n_rev += not auto
        img = load_image(image_path(rec).read_bytes())
        img.save(OUT / f"{name}.jpg", quality=85, optimize=True)
        picked.append({"file": f"{name}.jpg", "fields": res["fields"], "line_items": res["line_items"],
                       "reconciliation": res["reconciliation"], "decision": res["decision"], "reasons": res["reasons"],
                       "words": res["ocr"]["words"], "image_size": res["ocr"]["image_size"],
                       "model": res["model"]["name"]})
        if n_auto >= WANT_AUTO and n_rev >= WANT_REVIEW:
            break
    (OUT / "extractions.json").write_text(json.dumps(picked, indent=1), encoding="utf-8")
    for p in picked:
        print(p["file"], p["decision"], p["fields"]["total"]["text"], p["reasons"][0])


if __name__ == "__main__":
    main()
