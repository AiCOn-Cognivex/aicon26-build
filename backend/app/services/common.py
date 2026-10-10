"""Event log, JSON views of rows, and the shared OCR slot."""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Claim, Event, User, Wallet

# One OCR at a time: parallel OCRs only share the same CPUs, and each adds ~100 MB of RAM
_ocr_slot = asyncio.Semaphore(1)


async def run_predict(data: bytes) -> dict:
    from ml import predict as ml_predict
    async with _ocr_slot:
        return await run_in_threadpool(ml_predict.predict, data)


def iso(ts: datetime | None) -> str | None:
    return None if ts is None else ts.isoformat() + "Z"


def log_event(db: Session, *, company_id: int, user_id: int, kind: str, title: str, actor_id: int | None = None,
              amount: float | None = None, ref_type: str | None = None, ref_id: int | None = None,
              detail: dict | None = None, ts: datetime | None = None) -> Event:
    e = Event(company_id=company_id, user_id=user_id, actor_id=actor_id, kind=kind, title=title, amount=amount,
              ref_type=ref_type, ref_id=ref_id, detail=detail or {}, ts=ts or utcnow())
    db.add(e)
    return e


def user_dict(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "title": u.title,
            "department": u.department, "grade": u.grade, "joined_on": u.joined_on.isoformat()}


def event_dict(e: Event, names: dict[int, str] | None = None) -> dict:
    return {"id": e.id, "ts": iso(e.ts), "kind": e.kind, "title": e.title, "amount": e.amount,
            "ref_type": e.ref_type, "ref_id": e.ref_id, "detail": e.detail,
            "actor": (names or {}).get(e.actor_id) if e.actor_id else None}


def claim_dict(c: Claim, wallet: Wallet | None, user: User | None = None, full: bool = False) -> dict:
    d = {"id": c.id, "status": c.status, "wallet": None if wallet is None else {"code": wallet.code, "name": wallet.name},
         "merchant": c.merchant, "receipt_date": c.receipt_date.isoformat() if c.receipt_date else None,
         "currency": c.currency, "amount": c.amount, "amount_pkr": c.amount_pkr, "fx_rate": c.fx_rate,
         "model_decision": c.model_decision, "model_total": c.model_total, "reasons": c.reasons or [],
         "flags": c.flags or [], "edited": c.edited, "has_image": c.image_sha256 is not None,
         "created_at": iso(c.created_at), "submitted_at": iso(c.submitted_at), "decided_at": iso(c.decided_at),
         "pay_date": c.pay_date.isoformat() if c.pay_date else None, "paid_at": iso(c.paid_at),
         "reviewer_note": c.reviewer_note, "corrected_amount": c.corrected_amount, "note": c.note,
         "ai_fallback_used": bool(c.ai_fallback and not c.ai_fallback.get("error"))}
    if user is not None:
        d["employee"] = {"id": user.id, "name": user.name, "title": user.title, "grade": user.grade,
                         "department": user.department}
    if full:
        d["extraction"] = c.extraction
        d["suggestions"] = c.suggestions
        d["ai_fallback"] = c.ai_fallback
        d["qr_payload"] = c.qr_payload
        d["model_name"] = c.model_name
    return d
