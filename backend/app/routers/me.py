"""The signed-in employee's money: dashboard, activity, payslips, provident fund."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Claim, Event, User, Wallet
from ..security import current_user
from ..services import payroll as P
from ..services.payroll import short_day
from ..services import assistant as A
from ..services.common import claim_dict, event_dict, user_dict
from ..services.receipts import gemini_available

router = APIRouter(tags=["employee"])


def _fmt(v: float) -> str:
    return f"Rs {v:,.0f}"


def _nudges(wallets: list[dict], pay: dict, cutoff: date, t: date, n_review: int) -> list[dict]:
    out = []
    days_cut = (cutoff - t).days
    if days_cut <= 5:
        out.append({"kind": "cutoff", "text": f"Claim cut-off in {days_cut} day{'s' if days_cut != 1 else ''}: "
                    f"claims approved by {short_day(cutoff)} are paid on {short_day(date.fromisoformat(pay['pay_date']))}."})
    for w in wallets:
        if w["period"] == "annual" and w["limit"] and w["left"] / w["limit"] >= 0.3 and w["days_to_reset"] <= 120:
            out.append({"kind": "unused", "text": f"{_fmt(w['left'])} of your {w['name']} allowance is unused. "
                        f"It resets on {short_day(date.fromisoformat(w['resets_on']))}."})
        if w["runs_out_on"]:
            out.append({"kind": "pace", "text": f"At this pace your {w['name']} wallet runs out on "
                        f"{short_day(date.fromisoformat(w['runs_out_on']))}."})
    if n_review:
        out.append({"kind": "review", "text": f"{n_review} claim{'s are' if n_review > 1 else ' is'} with finance for review."})
    return out


@router.get("/me/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    company = user.company
    t = P.today()
    # each table is read once and shared by every widget (7 queries instead of 23)
    claims, advances, wallet_rows = P.user_claims(db, user), P.user_advances(db, user), P.wallets_for(db, user.company_id)
    wallets = P.wallet_balances(db, user, t, claims, wallet_rows)
    pay = P.expected_pay(db, user, company, t, claims, advances)
    slips = P.payslips_for(db, user)
    adv = P.advance_status(db, user, company, t, pay, advances)
    adv.pop("history")
    wmap = {w.id: w for w in wallet_rows}
    open_claims = sorted((c for c in claims if c.status in ("in_review", "auto_approved", "approved")),
                         key=lambda c: c.submitted_at or datetime.min, reverse=True)[:5]
    events = list(db.scalars(select(Event).where(Event.user_id == user.id, Event.kind != "claim_submitted")
                             .order_by(Event.ts.desc()).limit(8)))
    names = {u.id: u.name for u in db.scalars(select(User).where(User.company_id == user.company_id))}
    cutoff = P.next_cutoff(t, company.cutoff_day)
    n_review = sum(c.status == "in_review" for c in claims)
    totals = {k: sum(w[k] for w in wallets) for k in ("limit", "used", "pending", "left")}
    return {
        "user": user_dict(user), "company": {"name": company.name, "currency": company.currency},
        "today": t.isoformat(), "payday": pay,
        "cutoff": {"date": cutoff.isoformat(), "days_left": (cutoff - t).days},
        "wallets": wallets, "allowance_totals": totals,
        "paychecks": [{"period": s.period, "pay_date": s.pay_date.isoformat(), "net": s.net,
                       "salary": round(s.net - s.reimbursements), "reimbursements": s.reimbursements, "gross": s.gross}
                      for s in slips[-12:]],
        "pf": P.pf_summary(db, user, company, slips), "advance": adv,
        "open_claims": [claim_dict(c, wmap.get(c.wallet_id)) for c in open_claims],
        "activity": [event_dict(e, names) for e in events],
        "calendar": P.calendar(db, user, company, t, pay, wallets),
        "nudges": _nudges(wallets, pay, cutoff, t, n_review),
    }


@router.get("/me/activity")
def activity(limit: int = Query(50, ge=1, le=200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    names = {u.id: u.name for u in db.scalars(select(User).where(User.company_id == user.company_id))}
    events = db.scalars(select(Event).where(Event.user_id == user.id).order_by(Event.ts.desc()).limit(limit))
    return {"events": [event_dict(e, names) for e in events]}


@router.get("/me/wallets")
def wallets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"wallets": P.wallet_balances(db, user)}


def _slip(s, prev=None) -> dict:
    d = {k: getattr(s, k) for k in ("period", "basic", "house_rent", "utilities", "gross", "tax", "pf_employee",
                                     "pf_employer", "advance_repayment", "reimbursements", "net")}
    d["pay_date"] = s.pay_date.isoformat()
    if prev is not None:
        changes = []
        for k, label in (("gross", "Gross salary"), ("tax", "Income tax"), ("reimbursements", "Reimbursements"),
                         ("advance_repayment", "Advance deducted"), ("pf_employee", "Your PF contribution")):
            diff = getattr(s, k) - getattr(prev, k)
            if abs(diff) >= 1:
                changes.append({"label": label, "diff": round(diff)})
        d["changes"] = changes
        d["net_diff"] = round(s.net - prev.net)
    return d


@router.get("/payslips")
def payslips(user: User = Depends(current_user), db: Session = Depends(get_db)):
    slips = P.payslips_for(db, user)
    return {"payslips": [_slip(s, slips[i - 1] if i else None) for i, s in enumerate(slips)][::-1],
            "upcoming": P.expected_pay(db, user, user.company)}


@router.get("/payslips/{period}")
def payslip(period: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    slips = P.payslips_for(db, user)
    for i, s in enumerate(slips):
        if s.period == period:
            company = user.company
            return {"payslip": _slip(s, slips[i - 1] if i else None), "employee": user_dict(user),
                    "company": {"name": company.name}}
    raise HTTPException(404, "No payslip for that month")


@router.get("/me/pf")
def pf(user: User = Depends(current_user), db: Session = Depends(get_db)):
    company = user.company
    out = P.pf_summary(db, user, company)
    out["series_full"] = [{"period": s.period, "employee": s.pf_employee, "employer": s.pf_employer}
                          for s in P.payslips_for(db, user)]
    out["rate"] = company.pf_rate
    return out


@router.get("/me/certificate")
def certificate(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Data for a printable salary certificate (employees often wait days for HR to issue one)."""
    company = user.company
    basic, house, util = P.salary_parts(user.monthly_gross)
    return {"employee": user_dict(user), "company": {"name": company.name}, "issued_on": P.today().isoformat(),
            "monthly": {"basic": basic, "house_rent": house, "utilities": util, "gross": user.monthly_gross},
            "annual_gross": user.monthly_gross * 12}


@router.get("/wallets")
def company_wallets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"wallets": [{"code": w.code, "name": w.name, "period": w.period, "limit": w.limits.get(user.grade, 0),
                         "auto_approve": w.auto_approve, "per_claim_cap": w.per_claim_cap}
                        for w in db.scalars(select(Wallet).where(Wallet.company_id == user.company_id).order_by(Wallet.id))]}


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=400)


@router.post("/me/ask")
def ask(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ask Repay (optional, Gemini): answers questions about the employee's own pay from their own records only."""
    if not gemini_available():
        raise HTTPException(503, "The assistant is not switched on")
    if not A.allow(user.id):
        raise HTTPException(429, "That's a lot of questions. Please try again in a few minutes.")
    dash = dashboard(user, db)  # the same numbers the employee sees on their pages
    slips = P.payslips_for(db, user)
    recent = list(db.scalars(select(Claim).where(Claim.user_id == user.id, Claim.status != "draft")
                             .order_by(Claim.submitted_at.desc()).limit(10)))
    wmap = {w.id: w.name for w in P.wallets_for(db, user.company_id)}
    company = user.company
    data = {
        "employee": dash["user"], "today": dash["today"], "next_payday": dash["payday"], "claim_cutoff": dash["cutoff"],
        "allowance_wallets": dash["wallets"], "allowance_totals": dash["allowance_totals"],
        "salary_advance": P.advance_status(db, user, company), "provident_fund": dash["pf"],
        "last_12_paychecks": dash["paychecks"],
        "recent_payslips_with_changes": [_slip(s, slips[i - 1] if i else None) for i, s in enumerate(slips)][-3:],
        "recent_claims": [{"id": c.id, "status": c.status, "allowance": wmap.get(c.wallet_id), "merchant": c.merchant,
                           "amount_pkr": c.amount_pkr, "receipt_date": c.receipt_date.isoformat() if c.receipt_date else None,
                           "paid_with_salary_on": c.pay_date.isoformat() if c.pay_date else None,
                           "why_reviewed": (c.reasons or [])[:2], "reviewer_note": c.reviewer_note} for c in recent],
        "upcoming_dates": dash["calendar"],
        "company_rules": {
            "payday": "last working day (Mon-Fri) of each month",
            "claim_cutoff": f"claims approved by day {company.cutoff_day} are paid with that month's salary, later ones the month after",
            "salary_advance": f"up to {round(company.advance_share * 100)}% of net pay earned so far this month, no interest or fees, "
                              "a finance manager approves each request, deducted from the next salary",
            "provident_fund": f"employee and employer each put in {company.pf_rate:.2%} of basic salary every month",
            "salary_structure": "gross = basic + house rent (45% of basic) + utilities (10% of basic)",
        },
    }
    try:
        return A.ask(body.question.strip(), data, name=user.name, company=company.name, today=dash["today"])
    except RuntimeError:
        raise HTTPException(502, "The assistant couldn't answer just now. Please try again.")
