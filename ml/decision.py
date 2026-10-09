"""Decision layer: arithmetic reconciliation + confidence threshold -> AUTO_POST / HUMAN_REVIEW.

Reconciliation never edits predictions; it only reports which rule failed.
It can only block auto-posting. It never overrides low confidence or a missing total.
"""
from __future__ import annotations

from .schema import DECISION_AUTO, DECISION_REVIEW, HEADER_FIELDS

DEFAULT_POLICY = {
    "threshold": 0.90,          # min field confidence to auto-post (chosen on validation)
    "tol_abs": 50.0,            # rounding tolerance in currency units (IDR), chosen on TRAIN gold
    "tol_rel": 0.01,            # ...but never more than 1% of the amount
    "require_reconciliation": False,  # if True, NOT_CHECKABLE also goes to review
    "use_ocr_conf": False,      # field confidence = min(tagger prob, OCR confidence of its words)
    "check_absent": False,      # review if a field we did not extract might be on the receipt
}


def _v(fields, k):
    f = fields.get(k)
    return None if f is None else f.get("value")


def reconcile(fields: dict, items: list[dict], policy: dict = DEFAULT_POLICY) -> dict:
    total, sub = _v(fields, "total"), _v(fields, "subtotal")
    tax, svc, disc = _v(fields, "tax") or 0.0, _v(fields, "service_charge") or 0.0, abs(_v(fields, "discount") or 0.0)
    checks = []

    def tol(ref):
        return max(0.01, min(policy["tol_abs"], policy["tol_rel"] * abs(ref or 0)))

    if total is not None and sub is not None:
        # CORD has both tax-exclusive and tax-inclusive receipts (tax printed "included",
        # subtotal == total); either convention reconciles.
        exp = sub + tax + svc - disc
        exp_incl = sub + svc - disc
        if abs(exp - total) <= tol(total) or not tax or abs(exp_incl - total) > tol(total):
            checks.append({"rule": "subtotal + tax + service - discount = total",
                           "expected": round(exp, 2), "actual": total, "ok": abs(exp - total) <= tol(total)})
        else:
            checks.append({"rule": "subtotal (tax included) + service - discount = total",
                           "expected": round(exp_incl, 2), "actual": total, "ok": True})
    # sum(line items) = subtotal is deliberately NOT checked: it fails on 9% of TRAIN gold receipts
    if not checks:
        status = "NOT_CHECKABLE"
    else:
        status = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    return {"status": status, "checks": checks}


def field_confidence(f: dict, policy: dict) -> float:
    c = f.get("confidence", 1.0)
    if policy.get("use_ocr_conf"):
        c = min(c, f.get("ocr_confidence", 1.0))
    return c


def decide(fields: dict, items: list[dict], policy: dict = DEFAULT_POLICY, absent: dict | None = None) -> dict:
    rec = reconcile(fields, items, policy)
    reasons = []
    if fields.get("total") is None:
        reasons.append("total not found")
    low = [(k, field_confidence(f, policy)) for k, f in fields.items()
           if k in HEADER_FIELDS and f is not None and field_confidence(f, policy) < policy["threshold"]]
    for k, c in low:
        reasons.append(f"low confidence on {k} ({c:.2f} < {policy['threshold']:.2f})")
    if policy.get("check_absent") and absent:
        for k, c in absent.items():
            if k != "total" and c < policy["threshold"]:
                reasons.append(f"{k} may be on the receipt but was not extracted (absence confidence {c:.2f})")
    if rec["status"] == "FAIL":
        for c in rec["checks"]:
            if not c["ok"]:
                reasons.append(f"arithmetic check failed: {c['rule']} (expected {c['expected']:,.2f}, got {c['actual']:,.2f})")
    if rec["status"] == "NOT_CHECKABLE" and policy.get("require_reconciliation"):
        reasons.append("arithmetic could not be checked (no subtotal)")
    decision = DECISION_REVIEW if reasons else DECISION_AUTO
    if not reasons:
        reasons.append("all key fields confident" + (" and arithmetic reconciles" if rec["status"] == "PASS" else ""))
    return {"decision": decision, "reasons": reasons, "reconciliation": rec}


def receipt_confidence(fields: dict, policy: dict = DEFAULT_POLICY) -> float:
    """Receipt-level score = min confidence over predicted header fields (0 if no total)."""
    if fields.get("total") is None:
        return 0.0
    return min(field_confidence(f, policy) for f in fields.values() if f is not None)
