"""Tables. Money is in PKR (company currency), except claim.amount, which is in the receipt's currency."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    cutoff_day: Mapped[int] = mapped_column(Integer, default=25)       # claims approved by this day are paid this month
    fx_rates: Mapped[dict] = mapped_column(JSON, default=dict)          # fixed demo rates to PKR
    pf_rate: Mapped[float] = mapped_column(Float, default=0.0833)       # PF: employee and employer each, share of basic
    pf_profit_rate: Mapped[float] = mapped_column(Float, default=0.10)  # assumption used only for the projection
    advance_share: Mapped[float] = mapped_column(Float, default=0.5)    # advance cap: share of net pay earned so far
    advance_auto_approve: Mapped[bool] = mapped_column(Boolean, default=True)  # unused since D29: a finance manager decides


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="employee")  # employee | finance
    title: Mapped[str] = mapped_column(String(80), default="")
    department: Mapped[str] = mapped_column(String(80), default="")
    grade: Mapped[str] = mapped_column(String(8), default="G1")
    monthly_gross: Mapped[float] = mapped_column(Float, default=0)
    tax_monthly: Mapped[float] = mapped_column(Float, default=0)
    joined_on: Mapped[date] = mapped_column(Date)
    pf_opening: Mapped[float] = mapped_column(Float, default=0)        # PF balance before the seeded history
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    company: Mapped[Company] = relationship(lazy="joined", innerjoin=True)  # loaded with the user: one query, not two


class Wallet(Base):
    """An allowance policy, e.g. Fuel: PKR 30,000 a month for grade G2."""
    __tablename__ = "wallets"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(60))
    period: Mapped[str] = mapped_column(String(10))                   # monthly | annual
    limits: Mapped[dict] = mapped_column(JSON, default=dict)          # {grade: PKR}
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    per_claim_cap: Mapped[float] = mapped_column(Float, default=0)
    max_age_days: Mapped[int] = mapped_column(Integer, default=60)
    description: Mapped[str] = mapped_column(String(200), default="")


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[int | None] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    # draft -> auto_approved | in_review -> approved | rejected ; approved / auto_approved -> paid
    status: Mapped[str] = mapped_column(String(20), index=True, default="draft")
    merchant: Mapped[str | None] = mapped_column(String(120), nullable=True)
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_pkr: Mapped[float | None] = mapped_column(Float, nullable=True)
    fx_rate: Mapped[float] = mapped_column(Float, default=1.0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(80), default="")
    model_decision: Mapped[str] = mapped_column(String(20), default="")
    model_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    # model output: fields, words, reconciliation. Deferred: loaded only when a claim is opened, not in lists
    extraction: Mapped[dict] = mapped_column(JSON, default=dict, deferred=True)
    suggestions: Mapped[dict] = mapped_column(JSON, default=dict)      # date / merchant / wallet / currency + source
    flags: Mapped[list] = mapped_column(JSON, default=list)            # duplicate / anomaly findings
    reasons: Mapped[list] = mapped_column(JSON, default=list)          # why it went to review (empty if auto-approved)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    image_sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    image_dhash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    qr_payload: Mapped[str | None] = mapped_column(String(400), index=True, nullable=True)
    ai_fallback: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Gemini reading, if used
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # reviewer's correction = a label
    pay_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReceiptImage(Base):
    __tablename__ = "receipt_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), unique=True, index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)


class Advance(Base):
    """Salary advance on pay already earned this month: interest-free, deducted on payday."""
    __tablename__ = "advances"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="requested")  # requested | approved | rejected | repaid
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    repay_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Payslip(Base):
    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("user_id", "period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    pay_date: Mapped[date] = mapped_column(Date)
    basic: Mapped[float] = mapped_column(Float)
    house_rent: Mapped[float] = mapped_column(Float)
    utilities: Mapped[float] = mapped_column(Float)
    gross: Mapped[float] = mapped_column(Float)
    tax: Mapped[float] = mapped_column(Float)
    pf_employee: Mapped[float] = mapped_column(Float)
    pf_employer: Mapped[float] = mapped_column(Float)
    advance_repayment: Mapped[float] = mapped_column(Float, default=0)
    reimbursements: Mapped[float] = mapped_column(Float, default=0)
    net: Mapped[float] = mapped_column(Float)


class Event(Base):
    """Audit trail and activity feed: who did what, when, to which object."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)   # the employee it concerns
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
