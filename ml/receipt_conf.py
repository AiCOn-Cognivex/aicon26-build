"""Receipt-level confidence at inference: P(all five posted amounts are right) from a small logistic model.

Fitted on out-of-fold predictions by `python -m ml.confidence` (D21); stored as plain coefficients in
ml/artifacts/receipt_conf_<model>.json, so serving needs only the standard library.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from .decision import DEFAULT_POLICY, reconcile

FEATURES = ["min_conf", "logit_min_conf", "posterior", "logit_posterior", "recon_pass", "recon_fail",
            "min_absent", "min_ocr", "decoders_agree", "n_fields", "has_total"]


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def receipt_features(pred: dict, base: dict, policy: dict = DEFAULT_POLICY) -> dict:
    """pred = decoder output (rerank), base = assemble output on the same tagged words."""
    fs = {k: v for k, v in pred["fields"].items() if v is not None}
    conf = min((v["confidence"] for v in fs.values()), default=0.0)
    post = pred.get("assignment_posterior", 1.0)
    st = reconcile(pred["fields"], [], policy)["status"]
    agree = all((pred["fields"][k] or {}).get("value") == (base["fields"][k] or {}).get("value")
                for k in pred["fields"])
    return {"min_conf": conf, "logit_min_conf": _logit(conf), "posterior": post, "logit_posterior": _logit(post),
            "recon_pass": float(st == "PASS"), "recon_fail": float(st == "FAIL"),
            "min_absent": min(pred.get("absent_confidence", {}).values(), default=1.0),
            "min_ocr": min((v.get("ocr_confidence", 1.0) for v in fs.values()), default=0.0),
            "decoders_agree": float(agree), "n_fields": float(len(fs)), "has_total": float("total" in fs)}


@lru_cache(maxsize=4)
def load_model(path: str) -> dict:
    return json.loads(Path(path).read_text())


def score(model: dict, feats: dict) -> float:
    z = model["intercept"] + sum(c * (feats[f] - mu) / sd for f, c, mu, sd in
                                 zip(model["features"], model["coef"], model["mu"], model["sd"]))
    return 1 / (1 + math.exp(-z))
