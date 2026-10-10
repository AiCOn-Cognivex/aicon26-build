"""Finance console: overview, review queue, decisions, payroll export, allowance policy. Finance role only."""
from __future__ import annotations

import csv
import io
import statistics
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, utcnow
from ..models import Advance, Claim, Company, Event, User, Wallet
from ..security import require_finance
from ..services import payroll as P
from ..services.payroll import nice_day
from ..services.common import claim_dict, event_dict, iso, log_event, user_dict

router = APIRouter(prefix="/admin", tags=["finance"])


def _maps(db: Session, cid: int):
    users = {u.id: u for u in db.scalars(select(User).where(User.company_id == cid))}
    wallets = {w.id: w for w in P.wallets_for(db, cid)}
    return users, wallets


def _is_auto(c: Claim) -> bool:
    return c.decided_by_id is None and c.status in ("auto_approved", "paid") and not c.reasons


@router.get("/overview")
def overview(fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    t = P.today()
    users, wallets = _maps(db, fin.company_id)
    claims = list(db.scalars(select(Claim).where(Claim.company_id == fin.company_id, Claim.status != "draft")))
    month = [c for c in claims if c.submitted_at and P.pkt_date(c.submitted_at) >= date(t.year, t.month, 1)]
    decided = [c for c in month if c.status != "in_review"]
    auto = [c for c in month if _is_auto(c)]
    manual = [c for c in claims if c.decided_by_id and c.decided_at and c.submitted_at]
    hours = [(c.decided_at - c.submitted_at).total_seconds() / 3600 for c in manual]
    queue = [c for c in claims if c.status == "in_review"]
    pd = P.payday_on_or_after(t)
    due = [c for c in claims if c.status in P.UNPAID_APPROVED and c.pay_date == pd]
    by_wallet = {}
    for c in month:
        if c.status in P.APPROVED + ("in_review",) and c.wallet_id in wallets:
            k = wallets[c.wallet_id].name
            by_wallet.setdefault(k, {"approved": 0.0, "pending": 0.0})
            by_wallet[k]["pending" if c.status == "in_review" else "approved"] += c.amount_pkr or 0
    advances = list(db.scalars(select(Advance).join(User, Advance.user_id == User.id)
                               .where(User.company_id == fin.company_id)))
    events = db.scalars(select(Event).where(Event.company_id == fin.company_id).order_by(Event.ts.desc()).limit(12))
    names = {k: v.name for k, v in users.items()}
    company = db.get(Company, fin.company_id)
    return {
        "today": t.isoformat(), "payday": pd.isoformat(), "cutoff": P.next_cutoff(t, company.cutoff_day).isoformat(),
        "month": {"submitted": len(month), "auto_approved": len(auto), "decided": len(decided),
                  "auto_rate": round(len(auto) / len(month), 4) if month else None,
                  "amount_approved": round(sum(c.amount_pkr or 0 for c in month if c.status in P.APPROVED)),
                  "rejected": sum(c.status == "rejected" for c in month)},
        "queue": {"count": len(queue), "amount": round(sum(c.amount_pkr or 0 for c in queue)),
                  "oldest_hours": round(max(((utcnow() - c.submitted_at).total_seconds() / 3600 for c in queue), default=0), 1)},
        "decision_hours_median": round(statistics.median(hours), 1) if hours else None,
        "payroll": {"pay_date": pd.isoformat(), "amount": round(sum(c.amount_pkr or 0 for c in due)),
                    "claims": len(due), "employees": len({c.user_id for c in due}),
                    "advances": round(sum(a.amount for a in advances if a.status == "approved" and a.repay_date == pd))},
        "labels_collected": {"reviewed": len(manual), "corrected": sum(c.corrected_amount is not None for c in claims)},
        "by_wallet": [{"wallet": k, **{kk: round(vv) for kk, vv in v.items()}} for k, v in by_wallet.items()],
        "advances_open": round(sum(a.amount for a in advances if a.status in ("approved", "requested") and a.repay_date and a.repay_date >= t)),
        "events": [{**event_dict(e, names), "employee": names.get(e.user_id)} for e in events],
        "employees": len([u for u in users.values() if u.is_active]),
    }


@router.get("/queue")
def queue(fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    users, wallets = _maps(db, fin.company_id)
    rows = db.scalars(select(Claim).where(Claim.company_id == fin.company_id, Claim.status == "in_review")
                      .order_by(Claim.submitted_at))
    now = utcnow()
    return {"claims": [{**claim_dict(c, wallets.get(c.wallet_id), users.get(c.user_id)),
                        "waiting_hours": round((now - c.submitted_at).total_seconds() / 3600, 1)} for c in rows]}


@router.get("/claims")
def all_claims(status: str | None = None, limit: int = 200, fin: User = Depends(require_finance),
               db: Session = Depends(get_db)):
    users, wallets = _maps(db, fin.company_id)
    q = select(Claim).where(Claim.company_id == fin.company_id, Claim.status != "draft")
    if status:
        q = q.where(Claim.status.in_(status.split(",")))
    rows = db.scalars(q.order_by(Claim.submitted_at.desc()).limit(min(limit, 1000)))
    return {"claims": [{**claim_dict(c, wallets.get(c.wallet_id), users.get(c.user_id)), "auto": _is_auto(c)} for c in rows]}


@router.get("/claims/{cid}")
def claim_detail(cid: int, fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    users, wallets = _maps(db, fin.company_id)
    c = db.get(Claim, cid)
    if c is None or c.company_id != fin.company_id:
        raise HTTPException(404, "Claim not found")
    hist = [o.amount_pkr for o in db.scalars(select(Claim).where(
        Claim.user_id == c.user_id, Claim.wallet_id == c.wallet_id, Claim.id != c.id,
        Claim.status.in_(P.APPROVED))) if o.amount_pkr]
    names = {k: v.name for k, v in users.items()}
    events = db.scalars(select(Event).where(Event.ref_type == "claim", Event.ref_id == c.id).order_by(Event.ts))
    bal = next((w for w in P.wallet_balances(db, users[c.user_id]) if w["id"] == c.wallet_id), None)
    return {**claim_dict(c, wallets.get(c.wallet_id), users.get(c.user_id), full=True),
            "history": {"count": len(hist), "median": round(statistics.median(hist)) if hist else None},
            "wallet_balance": bal, "timeline": [event_dict(e, names) for e in events],
            "decided_by": names.get(c.decided_by_id) if c.decided_by_id else None}


class DecideIn(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    amount: float | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)


@router.post("/claims/{cid}/decide")
def decide(cid: int, body: DecideIn, fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    c = db.get(Claim, cid)
    if c is None or c.company_id != fin.company_id:
        raise HTTPException(404, "Claim not found")
    if c.status != "in_review":
        raise HTTPException(409, "This claim is not waiting for review")
    if c.user_id == fin.id:
        raise HTTPException(403, "You cannot decide your own claim")
    company = db.get(Company, fin.company_id)
    wname = db.get(Wallet, c.wallet_id).name if c.wallet_id else "Expense"
    t = P.today()
    c.decided_at, c.decided_by_id, c.reviewer_note = utcnow(), fin.id, (body.note or None)
    if body.action == "reject":
        if not body.note:
            raise HTTPException(422, "Please give the employee a reason")
        c.status = "rejected"
        log_event(db, company_id=c.company_id, user_id=c.user_id, actor_id=fin.id, kind="claim_rejected",
                  title=f"{wname} claim rejected: {body.note}", amount=c.amount_pkr, ref_type="claim", ref_id=c.id)
    else:
        if body.amount is not None and abs(body.amount - (c.amount or 0)) > 0.5:
            c.corrected_amount = body.amount  # kept as a labelled example for the next model
            c.amount = body.amount
            c.amount_pkr = round(body.amount * c.fx_rate, 2)
            log_event(db, company_id=c.company_id, user_id=c.user_id, actor_id=fin.id, kind="claim_corrected",
                      title=f"Amount corrected to {c.currency} {body.amount:,.0f}", amount=c.amount_pkr,
                      ref_type="claim", ref_id=c.id)
        c.status = "approved"
        c.pay_date = P.pay_date_for(t, company.cutoff_day)
        log_event(db, company_id=c.company_id, user_id=c.user_id, actor_id=fin.id, kind="claim_approved",
                  title=f"{wname} claim approved: paid on {nice_day(c.pay_date)}", amount=c.amount_pkr,
                  ref_type="claim", ref_id=c.id)
    db.commit()
    return claim_dict(c, db.get(Wallet, c.wallet_id), db.get(User, c.user_id), full=True)


@router.get("/advances")
def advances(fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    users, _ = _maps(db, fin.company_id)
    rows = db.scalars(select(Advance).where(Advance.user_id.in_(list(users))).order_by(Advance.requested_at.desc()))
    return {"advances": [{"id": a.id, "employee": users[a.user_id].name, "amount": a.amount, "status": a.status,
                          "reason": a.reason, "requested_at": iso(a.requested_at),
                          "repay_date": a.repay_date.isoformat() if a.repay_date else None} for a in rows]}


def _payroll_rows(db: Session, fin: User, pd: date):
    users, _ = _maps(db, fin.company_id)
    claims = list(db.scalars(select(Claim).where(Claim.company_id == fin.company_id, Claim.pay_date == pd,
                                                 Claim.status.in_(P.APPROVED))))
    advs = list(db.scalars(select(Advance).where(Advance.user_id.in_(list(users)), Advance.repay_date == pd,
                                                 Advance.status.in_(("approved", "repaid")))))
    rows = []
    for u in sorted(users.values(), key=lambda u: u.name):
        mine = [c for c in claims if c.user_id == u.id]
        adv = sum(a.amount for a in advs if a.user_id == u.id)
        if not mine and not adv:
            continue
        reimb = round(sum(c.amount_pkr or 0 for c in mine))
        rows.append({"employee_id": u.id, "name": u.name, "email": u.email, "department": u.department,
                     "reimbursements": reimb, "claims": len(mine), "advance_deduction": round(adv),
                     "net_adjustment": round(reimb - adv), "paid": bool(mine) and all(c.status == "paid" for c in mine)})
    return rows, claims, advs


@router.get("/payroll")
def payroll(pay_date: date | None = None, fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    pd = pay_date or P.payday_on_or_after(P.today())
    rows, claims, _ = _payroll_rows(db, fin, pd)
    company = db.get(Company, fin.company_id)
    prev = P.previous_payday(pd)
    return {"pay_date": pd.isoformat(), "previous": prev.isoformat(),
            "next": P.last_working_day(*P.add_months(pd.year, pd.month, 1)).isoformat(),
            "cutoff": date(pd.year, pd.month, company.cutoff_day).isoformat(), "rows": rows,
            "totals": {k: sum(r[k] for r in rows) for k in ("reimbursements", "claims", "advance_deduction", "net_adjustment")},
            "closed": bool(claims) and all(c.status == "paid" for c in claims)}


@router.get("/payroll.csv")
def payroll_csv(pay_date: date | None = None, fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    pd = pay_date or P.payday_on_or_after(P.today())
    rows, _, _ = _payroll_rows(db, fin, pd)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["pay_date", "employee_id", "name", "email", "department", "reimbursements_pkr", "claims",
                "advance_deduction_pkr", "net_adjustment_pkr"])
    for r in rows:
        w.writerow([pd.isoformat(), r["employee_id"], r["name"], r["email"], r["department"], r["reimbursements"],
                    r["claims"], r["advance_deduction"], r["net_adjustment"]])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="payroll-adjustments-{pd.isoformat()}.csv"'})


class CloseIn(BaseModel):
    pay_date: date


@router.post("/payroll/close")
def close_payroll(body: CloseIn, fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    """Mark the pay run as paid: approved claims -> paid, advances -> repaid."""
    rows, claims, advs = _payroll_rows(db, fin, body.pay_date)
    now = utcnow()
    for c in claims:
        if c.status != "paid":
            c.status, c.paid_at = "paid", now
            log_event(db, company_id=c.company_id, user_id=c.user_id, actor_id=fin.id, kind="claim_paid",
                      title="Claim reimbursed with salary", amount=c.amount_pkr, ref_type="claim", ref_id=c.id)
    for a in advs:
        if a.status == "approved":
            a.status = "repaid"
            log_event(db, company_id=fin.company_id, user_id=a.user_id, actor_id=fin.id, kind="advance_repaid",
                      title="Advance deducted from salary", amount=a.amount, ref_type="advance", ref_id=a.id)
    db.commit()
    return {"ok": True, "employees": len(rows)}


@router.get("/wallets")
def wallets(fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    return {"wallets": [{"id": w.id, "code": w.code, "name": w.name, "period": w.period, "limits": w.limits,
                         "auto_approve": w.auto_approve, "per_claim_cap": w.per_claim_cap,
                         "max_age_days": w.max_age_days, "description": w.description}
                        for w in P.wallets_for(db, fin.company_id)]}


class WalletIn(BaseModel):
    limits: dict[str, float]
    auto_approve: bool
    per_claim_cap: float = Field(ge=0)
    max_age_days: int = Field(ge=1, le=365)


@router.put("/wallets/{wid}")
def update_wallet(wid: int, body: WalletIn, fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    w = db.get(Wallet, wid)
    if w is None or w.company_id != fin.company_id:
        raise HTTPException(404, "Allowance not found")
    if any(v < 0 for v in body.limits.values()):
        raise HTTPException(422, "Limits cannot be negative")
    before = {"limits": w.limits, "auto_approve": w.auto_approve, "per_claim_cap": w.per_claim_cap}
    w.limits = {k: float(v) for k, v in body.limits.items()}
    w.auto_approve, w.per_claim_cap, w.max_age_days = body.auto_approve, body.per_claim_cap, body.max_age_days
    log_event(db, company_id=fin.company_id, user_id=fin.id, actor_id=fin.id, kind="policy_changed",
              title=f"{w.name} policy updated", ref_type="wallet", ref_id=w.id, detail={"before": before})
    db.commit()
    return {"ok": True}


@router.get("/employees")
def employees(fin: User = Depends(require_finance), db: Session = Depends(get_db)):
    users, _ = _maps(db, fin.company_id)
    out = []
    for u in sorted(users.values(), key=lambda u: u.name):
        claims = db.scalars(select(Claim).where(Claim.user_id == u.id, Claim.status != "draft")).all()
        out.append({**user_dict(u), "monthly_gross": u.monthly_gross, "claims": len(claims),
                    "in_review": sum(c.status == "in_review" for c in claims),
                    "last_login": iso(u.last_login)})
    return {"employees": out}
