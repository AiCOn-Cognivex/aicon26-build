"""The auto-approval engine: the model's decision combined with company policy.

A claim is auto-approved only if EVERY check passes; otherwise it goes to a finance reviewer with
every failed check listed in plain language. The model alone can never approve a claim it is unsure
about, and the employee can never approve a claim by editing the amount the model read.
"""
from __future__ import annotations

import statistics
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Claim, Company, User, Wallet
from .payroll import APPROVED, wallet_balances
from .receipts import hamming

NEAR_DUP_BITS = 6


def fmt(v: float) -> str:
    return f"Rs {v:,.0f}"


def image_flags(db: Session, claim: Claim) -> list[dict]:
    """Duplicate checks that only need the image (run at scan time, shown to the employee at once)."""
    # only the fingerprint columns: this compares against every claim in the company
    others = db.execute(select(Claim.id, Claim.image_sha256, Claim.image_dhash, Claim.qr_payload).where(
        Claim.company_id == claim.company_id, Claim.id != claim.id, Claim.status != "draft")).all()
    flags = []
    for o in others:
        if claim.image_sha256 and o.image_sha256 == claim.image_sha256:
            flags.append({"type": "duplicate_image", "severity": "high", "claim_id": o.id,
                          "message": f"This exact photo was already claimed (claim #{o.id})"})
        elif claim.image_dhash and o.image_dhash and hamming(claim.image_dhash, o.image_dhash) <= NEAR_DUP_BITS:
            flags.append({"type": "similar_image", "severity": "high", "claim_id": o.id,
                          "message": f"Looks like the same receipt as claim #{o.id} (near-identical photo)"})
        if claim.qr_payload and o.qr_payload == claim.qr_payload:
            flags.append({"type": "same_tax_invoice", "severity": "high", "claim_id": o.id,
                          "message": f"Same tax-invoice QR code as claim #{o.id}"})
    return flags


def submit_flags(db: Session, claim: Claim, wallet: Wallet) -> list[dict]:
    """Checks that need the confirmed amount and date."""
    flags = []
    mine = db.execute(select(Claim.id, Claim.receipt_date, Claim.amount_pkr, Claim.wallet_id, Claim.status,
                             Claim.submitted_at).where(Claim.user_id == claim.user_id, Claim.id != claim.id,
                                                       Claim.status != "draft")).all()
    for o in mine:
        if (o.receipt_date and o.receipt_date == claim.receipt_date and o.amount_pkr
                and abs(o.amount_pkr - (claim.amount_pkr or 0)) < 1):
            flags.append({"type": "same_amount_date", "severity": "high", "claim_id": o.id,
                          "message": f"Same amount and date as your claim #{o.id}"})
    history = [o.amount_pkr for o in mine if o.wallet_id == wallet.id and o.status in APPROVED and o.amount_pkr]
    if len(history) >= 3 and claim.amount_pkr:
        med = statistics.median(history)
        if claim.amount_pkr > 3 * med:
            flags.append({"type": "unusual_amount", "severity": "medium",
                          "message": f"{claim.amount_pkr / med:.1f}x this employee's usual {wallet.name} claim ({fmt(med)})"})
    cap = wallet.per_claim_cap
    if cap and claim.amount_pkr and 0.85 * cap <= claim.amount_pkr <= cap and claim.submitted_at:
        week = [o for o in mine if o.wallet_id == wallet.id and o.submitted_at
                and abs((o.submitted_at - claim.submitted_at).days) <= 7 and o.amount_pkr and 0.85 * cap <= o.amount_pkr <= cap]
        if week:
            flags.append({"type": "split_claims", "severity": "medium",
                          "message": f"{len(week) + 1} claims just under the {fmt(cap)} auto-approve limit within a week"})
    return flags


def review_reasons(db: Session, claim: Claim, user: User, wallet: Wallet, company: Company, t: date) -> list[str]:
    reasons: list[str] = []
    ext = claim.extraction or {}
    if claim.model_total is None:
        reasons.append("The model could not find a total on this receipt")
    elif claim.model_decision != "AUTO_POST":
        reasons += [f"Model not sure: {r.replace('service_charge', 'service charge')}" for r in ext.get("reasons", [])][:3]
    if claim.model_total is not None and claim.amount is not None and abs(claim.amount - claim.model_total) > 0.5:
        reasons.append(f"Amount changed by the employee ({claim.model_total:,.0f} read, {claim.amount:,.0f} claimed)")
    if (claim.suggestions or {}).get("amount_source") == "gemini":
        reasons.append("Amount read by the AI fallback (Gemini): a person checks these")
    if not wallet.auto_approve:
        reasons.append(f"{wallet.name} claims are always checked by a person (our model is validated on restaurant receipts only)")
    bal = next((w for w in wallet_balances(db, user, t) if w["id"] == wallet.id), None)
    if bal is not None and claim.amount_pkr and claim.amount_pkr > bal["left"]:
        reasons.append(f"More than the {wallet.name} balance left ({fmt(bal['left'])})")
    if wallet.per_claim_cap and claim.amount_pkr and claim.amount_pkr > wallet.per_claim_cap:
        reasons.append(f"Above the auto-approve limit of {fmt(wallet.per_claim_cap)} per claim")
    if claim.receipt_date:
        if claim.receipt_date > t:
            reasons.append("Receipt date is in the future")
        elif (t - claim.receipt_date).days > wallet.max_age_days:
            reasons.append(f"Receipt is older than {wallet.max_age_days} days")
    for f in claim.flags or []:
        reasons.append(("Possible duplicate: " if f["severity"] == "high" else "Unusual: ") + f["message"])
    return reasons
