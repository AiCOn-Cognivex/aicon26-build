// Shapes returned by the finance API (backend/app/routers).
import type { OcrWord } from "./types";

export type WalletBal = {
  id: number;
  code: string;
  name: string;
  period: "monthly" | "annual";
  description: string;
  auto_approve: boolean;
  per_claim_cap: number;
  limit: number;
  used: number;
  pending: number;
  left: number;
  resets_on: string;
  days_to_reset: number;
  claims: number;
  runs_out_on: string | null;
};

export type Pay = {
  pay_date: string;
  days_left: number;
  cycle_start: string;
  cycle_progress: number;
  gross: number;
  basic: number;
  house_rent: number;
  utilities: number;
  tax: number;
  pf_employee: number;
  advance_repayment: number;
  reimbursements: number;
  reimbursement_count: number;
  net: number;
};

export type Paycheck = { period: string; pay_date: string; net: number; salary: number; reimbursements: number; gross: number };

export type PF = {
  balance: number;
  employee_total: number;
  employer_total: number;
  monthly_contribution: number;
  employer_match_monthly: number;
  growth_12m: number;
  series: { period: string; balance: number }[];
  projection_5y: number;
  assumed_profit_rate: number;
  loan_eligible: number;
};

export type AdvanceSt = {
  earned_so_far: number;
  share: number;
  cap: number;
  outstanding: number;
  available: number;
  repay_date: string;
  auto_approve: boolean;
  monthly_net: number;
  history?: { id: number; amount: number; status: string; reason: string; requested_at: string; repay_date: string | null; note: string | null }[];
};

export type Flag = { type: string; severity: "high" | "medium"; message: string; claim_id?: number };

export type ClaimRow = {
  id: number;
  status: "draft" | "auto_approved" | "in_review" | "approved" | "rejected" | "paid";
  wallet: { code: string; name: string } | null;
  merchant: string | null;
  receipt_date: string | null;
  currency: string;
  amount: number | null;
  amount_pkr: number | null;
  fx_rate: number;
  model_decision: string;
  model_total: number | null;
  reasons: string[];
  flags: Flag[];
  edited: boolean;
  has_image: boolean;
  created_at: string;
  submitted_at: string | null;
  decided_at: string | null;
  pay_date: string | null;
  paid_at: string | null;
  reviewer_note: string | null;
  corrected_amount: number | null;
  note: string | null;
  ai_fallback_used: boolean;
  employee?: { id: number; name: string; title: string; grade: string; department: string };
  waiting_hours?: number;
};

export type Extraction = {
  fields: Record<string, { text: string; value: number | null; confidence: number; ocr_confidence?: number } | null>;
  line_items: unknown[];
  reconciliation: { status: "PASS" | "FAIL" | "NOT_CHECKABLE"; checks: { rule: string; expected: number; actual: number; ok: boolean }[] };
  decision: string;
  reasons: string[];
  words: OcrWord[];
  image_size: [number, number];
  timings_ms?: Record<string, number>;
};

export type Suggestions = {
  amount: number | null;
  amount_source: "model" | "gemini" | null;
  amount_confidence: number | null;
  date?: string | null;
  date_source?: string | null;
  merchant?: string | null;
  merchant_source?: string | null;
  wallet: string | null;
  wallet_source: string | null;
  wallet_keywords?: string[];
  currency: string;
  currency_source: string;
};

export type ClaimFull = ClaimRow & {
  extraction: Extraction;
  suggestions: Suggestions;
  ai_fallback: Record<string, unknown> | null;
  qr_payload: string | null;
  model_name: string;
  timeline?: EventRow[];
  decided_by?: string | null;
};

export type EventRow = {
  id: number;
  ts: string;
  kind: string;
  title: string;
  amount: number | null;
  ref_type: string | null;
  ref_id: number | null;
  detail: Record<string, unknown>;
  actor: string | null;
  employee?: string;
};

export type CalItem = { date: string; kind: string; title: string; detail?: string; amount?: number };

export type Dashboard = {
  user: { name: string; title: string; grade: string; department: string };
  company: { name: string; currency: string };
  today: string;
  payday: Pay;
  cutoff: { date: string; days_left: number };
  wallets: WalletBal[];
  allowance_totals: { limit: number; used: number; pending: number; left: number };
  paychecks: Paycheck[];
  pf: PF;
  advance: AdvanceSt;
  open_claims: ClaimRow[];
  activity: EventRow[];
  calendar: CalItem[];
  nudges: { kind: string; text: string }[];
};
