"""Pay-cycle maths: payday, claim cut-off, wallet balances, provident fund, salary advance.

Conventions (company settings, demo values): salary is paid on the last working day (Mon-Fri) of the
month; claims approved on or before `cutoff_day` are paid with that month's salary, later ones with
the next. Gross = basic + house rent (45% of basic) + utilities (10% of basic). Provident fund: the
employee and the employer each contribute `pf_rate` of basic every month.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Advance, Claim, Company, Payslip, User, Wallet

PKT = timezone(timedelta(hours=5))
APPROVED = ("auto_approved", "approved", "paid")
UNPAID_APPROVED = ("auto_approved", "approved")


def today() -> date:
    return datetime.now(PKT).date()


def pkt_date(ts: datetime) -> date:
    """Naive-UTC timestamp -> calendar date in Pakistan."""
    return (ts + timedelta(hours=5)).date()


def short_day(d: date) -> str:
    return f"{d.day} {d:%b}"


def nice_day(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def add_months(y: int, m: int, k: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + k
    return i // 12, i % 12 + 1


def last_working_day(y: int, m: int) -> date:
    d = date(y, m, monthrange(y, m)[1])
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def payday_on_or_after(t: date) -> date:
    pd = last_working_day(t.year, t.month)
    if t <= pd:
        return pd
    return last_working_day(*add_months(t.year, t.month, 1))


def previous_payday(pd: date) -> date:
    return last_working_day(*add_months(pd.year, pd.month, -1))


def pay_date_for(decided: date, cutoff_day: int) -> date:
    """Payday on which an approval made on `decided` is paid out."""
    if decided.day <= cutoff_day:
        return payday_on_or_after(date(decided.year, decided.month, 1))
    return last_working_day(*add_months(decided.year, decided.month, 1))


def next_cutoff(t: date, cutoff_day: int) -> date:
    if t.day <= cutoff_day:
        return date(t.year, t.month, cutoff_day)
    y, m = add_months(t.year, t.month, 1)
    return date(y, m, cutoff_day)


def salary_parts(gross: float) -> tuple[float, float, float]:
    basic = round(gross / 1.55)
    house = round(basic * 0.45)
    return basic, house, round(gross - basic - house)


def wallet_window(period: str, t: date) -> tuple[date, date]:
    if period == "monthly":
        y, m = add_months(t.year, t.month, 1)
        return date(t.year, t.month, 1), date(y, m, 1)
    return date(t.year, 1, 1), date(t.year + 1, 1, 1)


def wallets_for(db: Session, company_id: int) -> list[Wallet]:
    return list(db.scalars(select(Wallet).where(Wallet.company_id == company_id).order_by(Wallet.id)))


def user_claims(db: Session, user: User) -> list[Claim]:
    """The employee's claims that count against allowances or pay: approved, paid or in review."""
    return list(db.scalars(select(Claim).where(Claim.user_id == user.id, Claim.status.in_(APPROVED + ("in_review",)))))


def user_advances(db: Session, user: User) -> list[Advance]:
    return list(db.scalars(select(Advance).where(Advance.user_id == user.id).order_by(Advance.requested_at.desc())))


# The functions below accept rows the caller already loaded (claims, advances, wallets, payslips) so that one
# page does not query the same tables several times: every query is a network round trip to the database.

def wallet_balances(db: Session, user: User, t: date | None = None, claims: list[Claim] | None = None,
                    wallets: list[Wallet] | None = None) -> list[dict]:
    t = t or today()
    claims = user_claims(db, user) if claims is None else claims
    out = []
    for w in wallets_for(db, user.company_id) if wallets is None else wallets:
        start, end = wallet_window(w.period, t)
        limit = float(w.limits.get(user.grade, 0))
        used = pending = 0.0
        n = 0
        for c in claims:
            if c.wallet_id != w.id or c.submitted_at is None or not (start <= pkt_date(c.submitted_at) < end):
                continue
            if c.status == "in_review":
                pending += c.amount_pkr or 0
            else:
                used += c.amount_pkr or 0
                n += 1
        left = max(0.0, limit - used - pending)
        # at the current pace of approved spending, when would this wallet run out?
        elapsed = (t - start).days + 1
        runs_out = None
        if used > 0 and left > 0:
            d = t + timedelta(days=int(left / (used / elapsed)))
            runs_out = d.isoformat() if d < end else None
        out.append({"id": w.id, "code": w.code, "name": w.name, "period": w.period, "description": w.description,
                    "auto_approve": w.auto_approve, "per_claim_cap": w.per_claim_cap,
                    "limit": limit, "used": round(used), "pending": round(pending), "left": round(left),
                    "resets_on": end.isoformat(), "days_to_reset": (end - t).days, "claims": n, "runs_out_on": runs_out})
    return out


def expected_pay(db: Session, user: User, company: Company, t: date | None = None, claims: list[Claim] | None = None,
                 advances: list[Advance] | None = None) -> dict:
    t = t or today()
    pd = payday_on_or_after(t)
    basic, house, util = salary_parts(user.monthly_gross)
    pf_emp = round(basic * company.pf_rate)
    if claims is None:
        reimb = list(db.scalars(select(Claim).where(Claim.user_id == user.id, Claim.status.in_(UNPAID_APPROVED),
                                                    Claim.pay_date == pd)))
    else:
        reimb = [c for c in claims if c.status in UNPAID_APPROVED and c.pay_date == pd]
    if advances is None:
        adv = list(db.scalars(select(Advance).where(Advance.user_id == user.id, Advance.status == "approved",
                                                    Advance.repay_date == pd)))
    else:
        adv = [a for a in advances if a.status == "approved" and a.repay_date == pd]
    reimb_total = round(sum(c.amount_pkr or 0 for c in reimb))
    adv_total = round(sum(a.amount for a in adv))
    start = previous_payday(pd) + timedelta(days=1)
    length = (pd - start).days + 1
    elapsed = min(length, max(0, (t - start).days + 1))
    return {"pay_date": pd.isoformat(), "days_left": (pd - t).days, "cycle_start": start.isoformat(),
            "cycle_progress": round(elapsed / length, 4),
            "gross": user.monthly_gross, "basic": basic, "house_rent": house, "utilities": util,
            "tax": user.tax_monthly, "pf_employee": pf_emp, "advance_repayment": adv_total,
            "reimbursements": reimb_total, "reimbursement_count": len(reimb),
            "net": round(user.monthly_gross - user.tax_monthly - pf_emp - adv_total + reimb_total)}


def advance_status(db: Session, user: User, company: Company, t: date | None = None, pay: dict | None = None,
                   advances: list[Advance] | None = None) -> dict:
    t = t or today()
    advs = user_advances(db, user) if advances is None else advances
    pay = expected_pay(db, user, company, t, advances=advs) if pay is None else pay
    base_net = user.monthly_gross - user.tax_monthly - pay["pf_employee"]
    earned = base_net * pay["cycle_progress"]
    cap = company.advance_share * earned
    outstanding = sum(a.amount for a in advs if a.status == "requested" or
                      (a.status == "approved" and a.repay_date and a.repay_date >= t))
    available = max(0, int((cap - outstanding) // 500 * 500))
    return {"earned_so_far": round(earned), "share": company.advance_share, "cap": round(cap),
            "outstanding": round(outstanding), "available": available, "repay_date": pay["pay_date"],
            "auto_approve": company.advance_auto_approve, "monthly_net": round(base_net),
            "history": [{"id": a.id, "amount": a.amount, "status": a.status, "reason": a.reason,
                         "requested_at": a.requested_at.isoformat() + "Z",
                         "repay_date": a.repay_date.isoformat() if a.repay_date else None, "note": a.note}
                        for a in advs]}


def payslips_for(db: Session, user: User) -> list[Payslip]:
    return list(db.scalars(select(Payslip).where(Payslip.user_id == user.id).order_by(Payslip.period)))


def pf_summary(db: Session, user: User, company: Company, slips: list[Payslip] | None = None) -> dict:
    slips = payslips_for(db, user) if slips is None else slips
    bal = user.pf_opening
    series = []
    emp_total = user.pf_opening / 2
    er_total = user.pf_opening / 2
    for s in slips:
        bal += s.pf_employee + s.pf_employer
        emp_total += s.pf_employee
        er_total += s.pf_employer
        series.append({"period": s.period, "balance": round(bal)})
    monthly = (slips[-1].pf_employee + slips[-1].pf_employer) if slips else 0
    r = company.pf_profit_rate / 12
    n = 60
    projection = bal * (1 + r) ** n + monthly * (((1 + r) ** n - 1) / r)
    growth = bal - series[-13]["balance"] if len(series) >= 13 else bal - user.pf_opening
    return {"balance": round(bal), "employee_total": round(emp_total), "employer_total": round(er_total),
            "monthly_contribution": round(monthly), "employer_match_monthly": round(slips[-1].pf_employer) if slips else 0,
            "growth_12m": round(growth), "series": series[-12:], "projection_5y": round(projection),
            "assumed_profit_rate": company.pf_profit_rate, "loan_eligible": round(0.8 * emp_total)}


def calendar(db: Session, user: User, company: Company, t: date | None = None, pay: dict | None = None,
             balances: list[dict] | None = None) -> list[dict]:
    """Upcoming money dates for this employee (next ~2 months)."""
    t = t or today()
    pay = expected_pay(db, user, company, t) if pay is None else pay
    balances = wallet_balances(db, user, t) if balances is None else balances
    pd = date.fromisoformat(pay["pay_date"])
    items = [{"date": next_cutoff(t, company.cutoff_day).isoformat(), "kind": "cutoff",
              "title": "Claim cut-off", "detail": f"Claims approved by now are paid on {nice_day(pd)}"},
             {"date": pd.isoformat(), "kind": "payday", "title": "Payday", "amount": pay["net"],
              "detail": "Expected take-home, including approved claims"}]
    if pay["advance_repayment"]:
        items.append({"date": pd.isoformat(), "kind": "advance", "title": "Advance deducted",
                      "amount": pay["advance_repayment"], "detail": "Interest-free, deducted from this salary"})
    seen = set()
    for w in balances:
        key = (w["resets_on"], w["period"])
        if w["days_to_reset"] <= 92 and key not in seen:
            seen.add(key)
            names = [x["name"] for x in balances if (x["resets_on"], x["period"]) == key]
            items.append({"date": w["resets_on"], "kind": "reset", "title": "Allowances reset",
                          "detail": ", ".join(names)})
    nxt = last_working_day(*add_months(pd.year, pd.month, 1))
    if (nxt - t).days <= 62:
        items.append({"date": nxt.isoformat(), "kind": "payday", "title": "Next payday", "detail": "Following month"})
    return sorted(items, key=lambda x: x["date"])
