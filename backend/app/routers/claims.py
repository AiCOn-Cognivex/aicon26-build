"""Reimbursement claims: scan a receipt (model reads it), confirm, and get an instant decision."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models import Claim, Company, Event, ReceiptImage, User, Wallet
from ..security import current_user
from ..services import payroll as P
from ..services.payroll import nice_day
from ..services import receipts as R
from ..services.approval import image_flags, review_reasons, submit_flags
from ..services.common import claim_dict, event_dict, log_event, run_predict

router = APIRouter(prefix="/claims", tags=["claims"])
MAX_BYTES = 8 * 1024 * 1024


def _load(db: Session, cid: int, user: User) -> Claim:
    c = db.get(Claim, cid)
    if c is None or c.company_id != user.company_id or (c.user_id != user.id and user.role != "finance"):
        raise HTTPException(404, "Claim not found")
    return c


@router.post("/scan")
async def scan(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image larger than 8 MB")
    try:
        jpeg, img = await run_in_threadpool(R.prepare_image, data)
    except Exception:
        raise HTTPException(422, "That file is not a readable image")
    res = await run_predict(jpeg)
    qr = await run_in_threadpool(R.decode_qr, img)
    t = P.today()
    words = res["ocr"]["words"]
    lines = R.lines_from_words(words)
    text = "\n".join(lines)
    total = res["fields"].get("total")
    wallet_code, kw = R.suggest_wallet(text, bool(res["line_items"]))
    when = R.find_date(lines, t)
    merchant = R.guess_merchant(lines)
    sugg = {"amount": total["value"] if total else None, "amount_source": "model" if total else None,
            "amount_confidence": total["confidence"] if total else None,
            "date": when, "date_source": "rules" if when else None,
            "merchant": merchant, "merchant_source": "rules" if merchant else None,
            "wallet": wallet_code, "wallet_source": "rules" if wallet_code else None, "wallet_keywords": kw,
            "currency": R.detect_currency(text), "currency_source": "rules"}
    # Optional LLM fallback, only where our model is out of its depth (no total, unsure, or not a restaurant receipt)
    ai = None
    if R.gemini_available() and (total is None or res["decision"] != "AUTO_POST" or wallet_code not in (None, "meals")):
        ai = await run_in_threadpool(R.gemini_read, jpeg)
        if ai and not ai.get("error"):
            if sugg["amount"] is None and ai.get("total"):
                sugg.update(amount=ai["total"], amount_source="gemini", amount_confidence=None)
            if not sugg["date"] and ai.get("date"):
                sugg.update(date=ai["date"], date_source="gemini")
            if not sugg["merchant"] and ai.get("merchant"):
                sugg.update(merchant=ai["merchant"], merchant_source="gemini")
            if ai.get("category") and ai["category"] != "other" and (not wallet_code or ai["category"] != wallet_code):
                sugg.update(wallet=ai["category"], wallet_source="gemini")
            if ai.get("currency") and sugg["currency"] == "PKR" and ai["currency"] != "PKR":
                sugg.update(currency=ai["currency"], currency_source="gemini")
    claim = Claim(company_id=user.company_id, user_id=user.id, status="draft", currency=sugg["currency"],
                  model_name=res["model"]["name"], model_decision=res["decision"],
                  model_total=total["value"] if total else None,
                  extraction={"fields": res["fields"], "line_items": res["line_items"],
                              "reconciliation": res["reconciliation"], "decision": res["decision"],
                              "reasons": res["reasons"], "words": words, "image_size": res["ocr"]["image_size"],
                              "timings_ms": res["timings_ms"]},
                  suggestions=sugg, image_sha256=R.sha256(data), image_dhash=R.dhash(img), qr_payload=qr,
                  ai_fallback=ai)
    db.add(claim)
    db.flush()
    db.add(ReceiptImage(claim_id=claim.id, data=jpeg, width=img.width, height=img.height))
    claim.flags = image_flags(db, claim)
    db.commit()
    return {**claim_dict(claim, None, full=True), "wallets": P.wallet_balances(db, user, t)}


class SubmitIn(BaseModel):
    wallet: str
    amount: float = Field(gt=0, lt=100_000_000)
    currency: str = Field(default="PKR", min_length=3, max_length=3)
    receipt_date: date
    merchant: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


@router.post("/{cid}/submit")
def submit(cid: int, body: SubmitIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    claim = _load(db, cid, user)
    if claim.user_id != user.id:
        raise HTTPException(403, "Only the employee can submit their claim")
    if claim.status != "draft":
        raise HTTPException(409, "This claim was already submitted")
    wallet = db.scalar(select(Wallet).where(Wallet.company_id == user.company_id, Wallet.code == body.wallet))
    if wallet is None:
        raise HTTPException(422, "Unknown allowance")
    company = db.get(Company, user.company_id)
    cur = body.currency.upper()
    rate = 1.0 if cur == company.currency else company.fx_rates.get(cur)
    if rate is None:
        raise HTTPException(422, f"No exchange rate for {cur}")
    t = P.today()
    claim.wallet_id, claim.amount, claim.currency, claim.fx_rate = wallet.id, body.amount, cur, rate
    claim.amount_pkr = round(body.amount * rate, 2)
    claim.receipt_date, claim.merchant, claim.note = body.receipt_date, (body.merchant or None), (body.note or None)
    claim.edited = claim.model_total is not None and abs(body.amount - claim.model_total) > 0.5
    claim.submitted_at = utcnow()
    claim.flags = image_flags(db, claim) + submit_flags(db, claim, wallet)
    claim.reasons = review_reasons(db, claim, user, wallet, company, t)
    log_event(db, company_id=user.company_id, user_id=user.id, actor_id=user.id, kind="claim_submitted",
              title=f"{wallet.name} claim submitted", amount=claim.amount_pkr, ref_type="claim", ref_id=claim.id)
    if not claim.reasons:
        claim.status, claim.decided_at = "auto_approved", utcnow()
        claim.pay_date = P.pay_date_for(t, company.cutoff_day)
        log_event(db, company_id=user.company_id, user_id=user.id, kind="claim_auto_approved",
                  title=f"{wallet.name} claim auto-approved: paid on {nice_day(claim.pay_date)}", amount=claim.amount_pkr,
                  ref_type="claim", ref_id=claim.id)
    else:
        claim.status = "in_review"
        log_event(db, company_id=user.company_id, user_id=user.id, kind="claim_in_review",
                  title=f"{wallet.name} claim sent to finance for review", amount=claim.amount_pkr, ref_type="claim", ref_id=claim.id,
                  detail={"reasons": claim.reasons})
    db.commit()
    return claim_dict(claim, wallet, full=True)


@router.get("")
def list_claims(status: str | None = None, limit: int = 100, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    q = select(Claim).where(Claim.user_id == user.id, Claim.status != "draft")
    if status:
        q = q.where(Claim.status.in_(status.split(",")))
    wmap = {w.id: w for w in P.wallets_for(db, user.company_id)}
    rows = db.scalars(q.order_by(Claim.submitted_at.desc()).limit(min(limit, 500)))
    return {"claims": [claim_dict(c, wmap.get(c.wallet_id)) for c in rows]}


@router.get("/{cid}")
def get_claim(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _load(db, cid, user)
    names = {u.id: u.name for u in db.scalars(select(User).where(User.company_id == user.company_id))}
    events = db.scalars(select(Event).where(Event.ref_type == "claim", Event.ref_id == c.id).order_by(Event.ts))
    return {**claim_dict(c, db.get(Wallet, c.wallet_id) if c.wallet_id else None, db.get(User, c.user_id), full=True),
            "timeline": [event_dict(e, names) for e in events],
            "decided_by": names.get(c.decided_by_id) if c.decided_by_id else None}


@router.get("/{cid}/image")
def claim_image(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _load(db, cid, user)
    img = db.scalar(select(ReceiptImage).where(ReceiptImage.claim_id == c.id))
    if img is None:
        raise HTTPException(404, "No image")
    return Response(img.data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{cid}")
def discard(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _load(db, cid, user)
    if c.user_id != user.id or c.status != "draft":
        raise HTTPException(409, "Only your own unsubmitted scans can be discarded")
    img = db.scalar(select(ReceiptImage).where(ReceiptImage.claim_id == c.id))
    if img:
        db.delete(img)
    db.delete(c)
    db.commit()
    return {"ok": True}
