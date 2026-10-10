"""Salary advance on pay already earned this month (earned wage access): interest-free, no fees,
deducted automatically on the next payday. Capped at a share of net pay earned so far.
Request-based (D29): a finance manager or higher approves or rejects each request (/admin/advances)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models import Advance, Company, User
from ..security import current_user
from ..services import payroll as P
from ..services.common import log_event

router = APIRouter(prefix="/advances", tags=["advances"])


@router.get("")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return P.advance_status(db, user, db.get(Company, user.company_id))


class AdvanceIn(BaseModel):
    amount: float = Field(ge=1000)
    reason: str = Field(default="", max_length=200)


@router.post("")
def request_advance(body: AdvanceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    company = db.get(Company, user.company_id)
    st = P.advance_status(db, user, company)
    if any(a["status"] == "requested" for a in st["history"]):
        raise HTTPException(409, "You already have a request waiting for approval")
    if body.amount > st["available"]:
        raise HTTPException(422, f"You can take up to Rs {st['available']:,.0f} right now")
    repay = date.fromisoformat(st["repay_date"])
    a = Advance(user_id=user.id, amount=round(body.amount), reason=body.reason.strip(), repay_date=repay,
                requested_at=utcnow())
    db.add(a)
    db.flush()
    log_event(db, company_id=user.company_id, user_id=user.id, actor_id=user.id, kind="advance_requested",
              title="Salary advance requested: waiting for a finance manager", amount=a.amount,
              ref_type="advance", ref_id=a.id)
    db.commit()
    return P.advance_status(db, user, company)
