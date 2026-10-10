"""Sign-in (OAuth2 password flow), current user, password change, demo accounts for the login page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db, utcnow
from ..models import Company, User
from ..security import (can_approve_advances, check_throttle, clear_failures, create_token, current_user,
                        hash_password, record_failure, verify_password)
from ..services.common import user_dict
from ..services.receipts import gemini_available

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token")
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    check_throttle(email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        record_failure(email)
        raise HTTPException(401, "Wrong email or password", headers={"WWW-Authenticate": "Bearer"})
    clear_failures(email)
    user.last_login = utcnow()
    db.commit()
    tok, ttl = create_token(user)
    return {"access_token": tok, "token_type": "bearer", "expires_in": ttl, "user": me_dict(db, user)}


def me_dict(db: Session, user: User) -> dict:
    company = db.get(Company, user.company_id)
    return {**user_dict(user), "company": {"name": company.name, "currency": company.currency,
                                           "fx_rates": company.fx_rates, "cutoff_day": company.cutoff_day},
            "can_approve_advances": can_approve_advances(user), "assistant": gemini_available()}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_dict(db, user)


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=72)


@router.post("/change-password")
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    user.password_hash = hash_password(body.new)
    db.commit()
    return {"ok": True}


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Test logins shown on the sign-in page (seeded demo company only)."""
    if not config.SEED_DEMO:
        return {"accounts": []}
    picks = ["ayesha@northwind.example", "sara@northwind.example", "omar@northwind.example"]
    users = {u.email: u for u in db.scalars(select(User).where(User.email.in_(picks)))}
    return {"password": config.DEMO_PASSWORD,
            "accounts": [{"email": e, "name": users[e].name, "role": users[e].role, "title": users[e].title}
                         for e in picks if e in users]}
