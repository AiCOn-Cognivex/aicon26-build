"""Constrained decoding of header amounts: re-rank amount -> role assignments with the arithmetic.

The tagger labels each word independently-ish (CRF Viterbi). For the five posted amounts we instead
consider, per field, the top-k money tokens by the tagger's marginal probability of that field plus
"absent", enumerate the joint assignments (a token fills at most one field), and score

    score = sum_f log p_f(choice) + lam * arithmetic,  arithmetic = +1 PASS, 0 not checkable, -1 FAIL

(the same reconciliation rule as the decision layer, ml/decision.py). lam = 0 is plain per-field argmax.
The chosen assignment's softmax share over all assignments is its "assignment posterior", a receipt-level
confidence the decision policy can use. Line items are left as assembled.
"""
from __future__ import annotations

import math
from itertools import product

from .decision import DEFAULT_POLICY, reconcile
from .fields import assemble
from .money import parse_money, to_float
from .schema import HEADER_FIELDS

_FLOOR = 1e-4


def _field_p(w: dict, cat: str) -> float:
    p = w.get("probs") or {}
    return p.get(f"B-{cat}", 0.0) + p.get(f"I-{cat}", 0.0)


def _candidates(tagged: list[dict], k: int, min_p: float, pf: dict | None = None) -> dict[str, list[tuple]]:
    """field -> [(prob, token index, value, text)] best first, plus (p_absent, None, None, None).
    pf: optional {field: [prob per token]} (second-stage ranker, D27) instead of the CRF marginals."""
    money = []
    for i, w in enumerate(tagged):
        t = w["text"]
        if not any(ch.isdigit() for ch in t):
            continue
        v = parse_money(t)
        if v is None or v == 0:
            continue
        money.append((i, abs(float(v)), t))
    out = {}
    for f, cat in HEADER_FIELDS.items():
        fp = (lambda i: pf[f][i]) if pf else (lambda i, cat=cat: _field_p(tagged[i], cat))
        cands = sorted(((fp(i), i, v, t) for i, v, t in money), reverse=True)
        pmax = max((fp(i) for i in range(len(tagged))), default=0.0)
        keep = [c for c in cands[:k] if c[0] >= min_p]
        out[f] = keep + [(max(1.0 - pmax, _FLOOR), None, None, None)]
    return out


def decode(tagged: list[dict], policy: dict = DEFAULT_POLICY) -> dict:
    """The field decoder named by the decision policy (assemble = production before D21)."""
    if policy.get("decoder") != "rerank":
        return assemble(tagged)
    pred = rerank(tagged, lam=policy.get("lam", 1.5), policy=policy)
    if policy.get("receipt_model"):
        from .receipt_conf import load_model, receipt_features, score
        from .taggers import ART
        model = load_model(str(ART / policy["receipt_model"]))
        pred["receipt_confidence"] = round(score(model, receipt_features(pred, assemble(tagged), policy)), 4)
    return pred


def rerank(tagged: list[dict], lam: float = 2.0, k: int = 3, min_p: float = 0.02,
           policy: dict = DEFAULT_POLICY, pf: dict | None = None) -> dict:
    """Tagged words (with per-word marginals `probs`) -> assemble()-style prediction with re-ranked fields."""
    base = assemble(tagged)
    if not tagged or "probs" not in tagged[0]:
        return base
    cands = _candidates(tagged, k, min_p, pf)
    names = list(HEADER_FIELDS)
    scored = []
    for combo in product(*(cands[f] for f in names)):
        idx = [c[1] for c in combo if c[1] is not None]
        if len(idx) != len(set(idx)):
            continue
        fields = {f: (None if c[1] is None else {"value": c[2]}) for f, c in zip(names, combo)}
        if fields["total"] is None and lam > 0:
            arith = -1.0  # never prefer "no total" because nothing can then fail
        else:
            st = reconcile(fields, [], policy)["status"]
            arith = {"PASS": 1.0, "NOT_CHECKABLE": 0.0, "FAIL": -1.0}[st]
        s = sum(math.log(max(c[0], _FLOOR)) for c in combo) + lam * arith
        scored.append((s, combo))
    if not scored:
        return base
    scored.sort(key=lambda x: -x[0])
    best_s, best = scored[0]
    z = sum(math.exp(s - best_s) for s, _ in scored)
    fields = {}
    for f, c in zip(names, best):
        if c[1] is None:
            fields[f] = None
            continue
        w = tagged[c[1]]
        fields[f] = {"text": c[3], "value": to_float(parse_money(c[3])), "confidence": round(c[0], 4),
                     "ocr_confidence": round(float(w.get("ocr_conf", 1.0)), 4)}
    absent = {f: round(best[names.index(f)][0], 4) for f in names if fields[f] is None}
    return {**base, "fields": fields, "absent_confidence": absent,
            "assignment_posterior": round(1.0 / z, 4)}

