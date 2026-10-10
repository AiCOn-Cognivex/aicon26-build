"""Demo company "Northwind Traders (Demo)": fictional employees, 12 months of payslips, provident fund,
claims and advances, all relative to today. Everything here is DEMO DATA and is labelled so in the UI.

Current-month claims with images use real CORD v2 validation receipts (CC-BY-4.0) and the model's real
output (backend/seed_assets, see make_seed_assets.py); their outcome is decided by the same approval
engine as live claims. Older claims have no image ("archived").
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import utcnow
from .models import Advance, Claim, Company, Payslip, ReceiptImage, User, Wallet
from .security import hash_password
from .services import payroll as P
from .services.approval import image_flags, review_reasons, submit_flags
from .services.common import log_event
from .services.payroll import nice_day
from .services.receipts import dhash, sha256

ASSETS = config.ROOT / "backend" / "seed_assets"

PEOPLE = [  # email, name, role, title, department, grade, gross, tax, joined, pf_opening
    ("ayesha@northwind.example", "Ayesha Khan", "employee", "Field Sales Executive", "Sales", "G2", 185000, 11800, date(2022, 3, 1), 380000),
    ("sara@northwind.example", "Sara Malik", "finance", "Finance Officer", "Finance", "G2", 210000, 15500, date(2021, 8, 16), 520000),
    ("bilal@northwind.example", "Bilal Ahmed", "employee", "Customer Support Officer", "Operations", "G1", 95000, 1200, date(2024, 1, 8), 60000),
    ("hamza@northwind.example", "Hamza Siddiqui", "employee", "Regional Sales Manager", "Sales", "G3", 420000, 61000, date(2019, 5, 2), 1650000),
    ("fatima@northwind.example", "Fatima Noor", "employee", "Logistics Coordinator", "Supply Chain", "G1", 82000, 600, date(2023, 6, 12), 120000),
    ("omar@northwind.example", "Omar Farooq", "finance", "Finance Manager", "Finance", "G3", 360000, 48000, date(2018, 2, 5), 1900000),
]
WALLETS = [  # code, name, period, limits, auto_approve, cap, max_age, description
    ("meals", "Meals & client", "monthly", {"G1": 12000, "G2": 20000, "G3": 35000}, True, 10000, 60, "Client meals and working lunches"),
    ("fuel", "Fuel", "monthly", {"G1": 15000, "G2": 30000, "G3": 50000}, False, 12000, 45, "Fuel for field visits"),
    ("medical", "Medical (OPD)", "annual", {"G1": 60000, "G2": 90000, "G3": 150000}, False, 25000, 90, "Doctor, pharmacy and lab tests"),
    ("mobile", "Mobile & internet", "monthly", {"G1": 2500, "G2": 4000, "G3": 8000}, False, 8000, 60, "Mobile and home internet bills"),
    ("learning", "Learning", "annual", {"G1": 25000, "G2": 50000, "G3": 100000}, False, 50000, 120, "Courses, books and certifications"),
]
MERCHANTS = {
    "meals": ["Blue Lantern Cafe", "Spice Route Kitchen", "Hilltop Grill", "Daily Brew Coffee", "Riverside Dhaba"],
    "fuel": ["Highway Fuel Point", "City Fuel Station", "Motorway Service Area"],
    "medical": ["CareWell Pharmacy", "City Diagnostic Lab", "Family Clinic"],
    "mobile": ["Mobile bill", "Home internet bill"],
    "learning": ["Online course", "Book Corner"],
}
# current-month claims with real receipt images: (employee, asset, wallet, days ago, note)
IMAGE_CLAIMS = [
    ("ayesha@northwind.example", "test_11.jpg", "meals", 3, "Client dinner, Jakarta visit"),
    ("ayesha@northwind.example", "test_7.jpg", "meals", 0, "Team lunch with distributor, Jakarta"),
    ("bilal@northwind.example", "test_12.jpg", "meals", 1, "Lunch during vendor training"),
    ("hamza@northwind.example", "test_13.jpg", "meals", 2, "Dinner with regional distributors, Jakarta"),
    ("hamza@northwind.example", "test_15.jpg", "meals", 5, "Client lunch, Jakarta"),
    ("fatima@northwind.example", "test_14.jpg", "meals", 4, "Working lunch at supplier site"),
    ("sara@northwind.example", "test_16.jpg", "meals", 6, "Audit team lunch"),
]


def utc(d: date, hour: int, minute: int = 0) -> datetime:
    """A Pakistan-time wall clock -> naive UTC."""
    return datetime(d.year, d.month, d.day, hour, minute) - timedelta(hours=5)


def seed_demo(db: Session) -> bool:
    if db.scalar(select(Company)):
        return False
    rng = random.Random(7)
    t = P.today()
    co = Company(name="Northwind Traders (Demo)", currency="PKR", cutoff_day=25,
                 fx_rates={"IDR": 0.017, "USD": 280.0}, pf_rate=0.0833, pf_profit_rate=0.10,
                 advance_share=0.5, advance_auto_approve=True)
    db.add(co)
    db.flush()
    pw = hash_password(config.DEMO_PASSWORD)
    users = {}
    for email, name, role, title, dept, grade, gross, tax, joined, pf in PEOPLE:
        u = User(company_id=co.id, email=email, name=name, password_hash=pw, role=role, title=title, department=dept,
                 grade=grade, monthly_gross=gross, tax_monthly=tax, joined_on=joined, pf_opening=pf)
        db.add(u)
        users[email] = u
    wallets = {}
    for code, name, period, limits, auto, cap, age, desc in WALLETS:
        w = Wallet(company_id=co.id, code=code, name=name, period=period, limits=limits, auto_approve=auto,
                   per_claim_cap=cap, max_age_days=age, description=desc)
        db.add(w)
        wallets[code] = w
    db.flush()
    sara = users["sara@northwind.example"]

    # ---- 12 months of history: paid claims, advances, payslips ----
    months = [P.add_months(t.year, t.month, -k) for k in range(12, 0, -1)]
    increment_from = (t.year if t.month >= 7 else t.year - 1, 7)  # annual increment each July
    grade_scale = {"G1": 0.7, "G2": 1.0, "G3": 1.6}
    history = []  # inserted in one batch below: one flush per claim cost ~1,000 database round trips on a reset
    for email, u in users.items():
        s = grade_scale[u.grade]
        field = u.department in ("Sales", "Supply Chain")
        for y, m in months:
            plan = [("meals", rng.randint(1, 2), (1500, 6000)), ("mobile", 1, (1800, 3800))]
            if field:
                plan.append(("fuel", rng.randint(1, 3), (3000, 9000)))
            if rng.random() < 0.25:
                plan.append(("medical", 1, (2000, 12000)))
            if rng.random() < 0.08:
                plan.append(("learning", 1, (8000, 20000)))
            for code, n, (lo, hi) in plan:
                w = wallets[code]
                for _ in range(n):
                    amt = round(rng.uniform(lo, hi) * (s if code != "mobile" else 1) / 50) * 50
                    amt = min(amt, w.limits[u.grade] * (1 if w.period == "monthly" else 0.4))
                    day = rng.randint(2, 21)
                    rdate = date(y, m, day)
                    sub = utc(rdate, rng.randint(9, 20), rng.randint(0, 59))
                    auto = code == "meals" and rng.random() < 0.85
                    dec = sub + (timedelta(seconds=2) if auto else timedelta(hours=rng.randint(2, 40)))
                    pay = P.pay_date_for(P.pkt_date(dec), co.cutoff_day)
                    c = Claim(company_id=co.id, user_id=u.id, wallet_id=w.id, status="paid",
                              merchant=rng.choice(MERCHANTS[code]), receipt_date=rdate, currency="PKR", amount=amt,
                              amount_pkr=amt, fx_rate=1.0, model_name="CRF (token + layout features)" if code == "meals" else "",
                              model_decision="AUTO_POST" if auto else "HUMAN_REVIEW", model_total=amt,
                              reasons=[] if auto else [f"{w.name} claims are always checked by a person" if not w.auto_approve
                                                       else "Model not sure: low confidence on total"],
                              created_at=sub, submitted_at=sub, decided_at=dec,
                              decided_by_id=None if auto else sara.id, pay_date=pay, paid_at=utc(pay, 10))
                    if c.user_id == sara.id and not auto:
                        c.decided_by_id = users["omar@northwind.example"].id  # nobody approves their own claim
                    db.add(c)
                    history.append((c, u, w, auto, amt, sub, dec, pay))
    db.flush()
    for c, u, w, auto, amt, sub, dec, pay in history:
        log_event(db, company_id=co.id, user_id=u.id, actor_id=u.id, kind="claim_submitted",
                  title=f"{w.name} claim submitted", amount=amt, ref_type="claim", ref_id=c.id, ts=sub)
        log_event(db, company_id=co.id, user_id=u.id, actor_id=c.decided_by_id,
                  kind="claim_auto_approved" if auto else "claim_approved",
                  title=f"{w.name} claim {'auto-approved' if auto else 'approved'}: paid on {nice_day(pay)}",
                  amount=amt, ref_type="claim", ref_id=c.id, ts=dec)
        log_event(db, company_id=co.id, user_id=u.id, kind="claim_paid", title=f"{w.name} claim reimbursed with salary",
                  amount=amt, ref_type="claim", ref_id=c.id, ts=utc(pay, 10))
    # one rejected duplicate last month (Bilal) and one repaid advance (Ayesha, 4 months ago)
    bilal, ayesha = users["bilal@northwind.example"], users["ayesha@northwind.example"]
    ly, lm = P.add_months(t.year, t.month, -1)
    rej_day = date(ly, lm, 14)
    rej = Claim(company_id=co.id, user_id=bilal.id, wallet_id=wallets["meals"].id, status="rejected",
                merchant="Hilltop Grill", receipt_date=rej_day, currency="PKR", amount=4200, amount_pkr=4200,
                model_decision="AUTO_POST", model_total=4200, flags=[{"type": "same_amount_date", "severity": "high",
                "message": "Same amount and date as an earlier claim"}],
                reasons=["Possible duplicate: Same amount and date as an earlier claim"],
                created_at=utc(rej_day, 18), submitted_at=utc(rej_day, 18), decided_at=utc(rej_day + timedelta(days=1), 11),
                decided_by_id=sara.id, reviewer_note="Same bill was claimed on the 12th. Rejected as a duplicate.")
    db.add(rej)
    db.flush()
    log_event(db, company_id=co.id, user_id=bilal.id, actor_id=bilal.id, kind="claim_submitted",
              title="Meals & client claim submitted", amount=4200, ref_type="claim", ref_id=rej.id, ts=rej.submitted_at)
    log_event(db, company_id=co.id, user_id=bilal.id, actor_id=sara.id, kind="claim_rejected",
              title="Meals & client claim rejected: same bill was claimed on the 12th", amount=4200, ref_type="claim", ref_id=rej.id,
              ts=rej.decided_at)
    ay, am = P.add_months(t.year, t.month, -4)
    adv_pay = P.last_working_day(ay, am)
    adv = Advance(user_id=ayesha.id, amount=25000, reason="School fees", status="repaid",
                  requested_at=utc(date(ay, am, 12), 9), decided_at=utc(date(ay, am, 12), 9), repay_date=adv_pay)
    db.add(adv)
    db.flush()
    log_event(db, company_id=co.id, user_id=ayesha.id, kind="advance_approved",
              title=f"Advance approved: deducted on {nice_day(adv_pay)}, no interest", amount=25000,
              ref_type="advance", ref_id=adv.id, ts=adv.requested_at)
    log_event(db, company_id=co.id, user_id=ayesha.id, kind="advance_repaid", title="Advance deducted from salary",
              amount=25000, ref_type="advance", ref_id=adv.id, ts=utc(adv_pay, 10))
    db.flush()

    # payslips (consistent with the claims and advances above)
    claims = [h[0] for h in history]  # the paid claims (the rejected one is not paid)
    for u in users.values():
        for y, m in months:
            pd = P.last_working_day(y, m)
            gross = u.monthly_gross if (y, m) >= increment_from else round(u.monthly_gross / 1.10, -2)
            tax = u.tax_monthly if (y, m) >= increment_from else round(u.tax_monthly / 1.15, -1)
            basic, house, util = P.salary_parts(gross)
            pf = round(basic * co.pf_rate)
            reimb = round(sum(c.amount_pkr for c in claims if c.user_id == u.id and c.pay_date == pd))
            adv_amt = 25000 if (u is ayesha and pd == adv_pay) else 0
            db.add(Payslip(user_id=u.id, period=f"{y:04d}-{m:02d}", pay_date=pd, basic=basic, house_rent=house,
                           utilities=util, gross=gross, tax=tax, pf_employee=pf, pf_employer=pf,
                           advance_repayment=adv_amt, reimbursements=reimb, net=round(gross - tax - pf - adv_amt + reimb)))
            log_event(db, company_id=co.id, user_id=u.id, kind="salary_credited", title=f"Salary for {pd.strftime('%B')} credited",
                      amount=round(gross - tax - pf - adv_amt + reimb), ref_type="payslip", ts=utc(pd, 10, 5))
            log_event(db, company_id=co.id, user_id=u.id, kind="pf_contribution",
                      title="Provident fund: your share + employer match", amount=2 * pf, ref_type="pf", ts=utc(pd, 10, 6))

    # ---- this month ----
    cur_pay = P.payday_on_or_after(t)
    adv2 = Advance(user_id=bilal.id, amount=15000, reason="Medical bills at home", status="approved",
                   requested_at=utc(t - timedelta(days=2), 13), decided_at=utc(t - timedelta(days=2), 13), repay_date=cur_pay)
    db.add(adv2)
    db.flush()
    log_event(db, company_id=co.id, user_id=bilal.id, kind="advance_approved",
              title=f"Advance approved: deducted on {nice_day(cur_pay)}, no interest", amount=15000,
              ref_type="advance", ref_id=adv2.id, ts=adv2.requested_at)
    # manual approvals without images (fuel / medical are always reviewed)
    month_start = date(t.year, t.month, 1)
    for email, code, amt, merchant in [("ayesha@northwind.example", "fuel", 8200, "Highway Fuel Point"),
                                       ("ayesha@northwind.example", "medical", 7800, "CareWell Pharmacy"),
                                       ("hamza@northwind.example", "fuel", 14500, "Motorway Service Area"),
                                       ("fatima@northwind.example", "fuel", 5400, "City Fuel Station")]:
        u, w = users[email], wallets[code]
        rdate = max(month_start, t - timedelta(days=rng.randint(4, 8)))
        sub = utc(rdate, 17, 30)
        dec = sub + timedelta(hours=rng.randint(3, 20))
        c = Claim(company_id=co.id, user_id=u.id, wallet_id=w.id, status="approved", merchant=merchant, receipt_date=rdate,
                  currency="PKR", amount=amt, amount_pkr=amt, model_decision="HUMAN_REVIEW", model_total=amt,
                  reasons=[f"{w.name} claims are always checked by a person (our model is validated on restaurant receipts only)"]
                  + ([f"Above the auto-approve limit of Rs {w.per_claim_cap:,.0f} per claim"] if amt > w.per_claim_cap else []),
                  created_at=sub, submitted_at=sub, decided_at=dec, decided_by_id=sara.id,
                  pay_date=P.pay_date_for(P.pkt_date(dec), co.cutoff_day))
        db.add(c)
        db.flush()
        log_event(db, company_id=co.id, user_id=u.id, actor_id=u.id, kind="claim_submitted",
                  title=f"{w.name} claim submitted", amount=amt, ref_type="claim", ref_id=c.id, ts=sub)
        log_event(db, company_id=co.id, user_id=u.id, kind="claim_in_review", title=f"{w.name} claim sent to finance for review",
                  amount=amt, ref_type="claim", ref_id=c.id, ts=sub + timedelta(seconds=2), detail={"reasons": c.reasons})
        log_event(db, company_id=co.id, user_id=u.id, actor_id=sara.id, kind="claim_approved",
                  title=f"{w.name} claim approved: paid on {nice_day(c.pay_date)}", amount=amt, ref_type="claim", ref_id=c.id, ts=dec)
    db.flush()
    # claims with real receipt images, decided by the live approval engine
    extractions = {e["file"]: e for e in json.loads((ASSETS / "extractions.json").read_text(encoding="utf-8"))}
    for email, fname, code, days_ago, note in IMAGE_CLAIMS:
        u, w, e = users[email], wallets[code], extractions[fname]
        data = (ASSETS / fname).read_bytes()
        img = Image.open(ASSETS / fname)
        total = e["fields"]["total"]
        when = t - timedelta(days=days_ago)
        sub = utcnow() - timedelta(hours=2) if days_ago == 0 else utc(when, 13, 15)
        c = Claim(company_id=co.id, user_id=u.id, wallet_id=w.id, status="draft", merchant=None, receipt_date=when,
                  currency="IDR", amount=total["value"], fx_rate=co.fx_rates["IDR"],
                  amount_pkr=round(total["value"] * co.fx_rates["IDR"], 2), note=note, model_name=e["model"],
                  model_decision=e["decision"], model_total=total["value"],
                  extraction={k: e[k] for k in ("fields", "line_items", "reconciliation", "decision", "reasons", "words", "image_size")},
                  suggestions={"amount": total["value"], "amount_source": "model", "amount_confidence": total["confidence"],
                               "currency": "IDR", "currency_source": "rules", "wallet": code, "wallet_source": "rules"},
                  image_sha256=sha256(data), image_dhash=dhash(img), created_at=sub, submitted_at=sub)
        db.add(c)
        db.flush()
        db.add(ReceiptImage(claim_id=c.id, data=data, width=img.width, height=img.height))
        c.flags = image_flags(db, c) + submit_flags(db, c, w)
        c.reasons = review_reasons(db, c, u, w, co, t)
        log_event(db, company_id=co.id, user_id=u.id, actor_id=u.id, kind="claim_submitted",
                  title=f"{w.name} claim submitted", amount=c.amount_pkr, ref_type="claim", ref_id=c.id, ts=sub)
        if c.reasons:
            c.status = "in_review"
            log_event(db, company_id=co.id, user_id=u.id, kind="claim_in_review", title=f"{w.name} claim sent to finance for review",
                      amount=c.amount_pkr, ref_type="claim", ref_id=c.id, ts=sub + timedelta(seconds=3),
                      detail={"reasons": c.reasons})
        else:
            c.status, c.decided_at = "auto_approved", sub + timedelta(seconds=3)
            c.pay_date = P.pay_date_for(when, co.cutoff_day)
            log_event(db, company_id=co.id, user_id=u.id, kind="claim_auto_approved",
                      title=f"{w.name} claim auto-approved: paid on {nice_day(c.pay_date)}", amount=c.amount_pkr,
                      ref_type="claim", ref_id=c.id, ts=c.decided_at)
        db.flush()
    db.commit()
    return True
