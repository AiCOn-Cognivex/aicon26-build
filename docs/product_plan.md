# Product plan: employee finance app (proposal, Sat 10 Oct)

> **Later changes (D28-D29):** salary advances are requests that a finance manager or higher approves; Ask Repay
> (optional Gemini assistant for the employee's own pay questions) was added; finance pages live under `/finance/*`
> (this plan says `/admin`); claim pages are `/app/claims/view?id=` and `/finance/review/view?id=`.

Status: **built and deployed (10 Oct, 07:30)**, P0 and most P1 features. Not built: E7 push alerts (in-app tips only), LLM policy assistant, fuel-price check, anomaly scoring beyond the two rules in `backend/app/services/approval.py`. The receipt model (CRF, live on
Railway) is reused unchanged as the engine of the reimbursement feature.

## 1. The problem and the pitch in one paragraph
Employees pay work costs out of their own pocket (fuel, client meals, medicine under a medical
allowance). They hand in paper slips and wait weeks: slips get lost, claims are retyped by finance,
and employees don't know how much allowance they have left or what their next salary will be.
Lower-paid field staff feel this most, and an empty wallet before payday often means borrowing
from someone outside the company. **Our app** gives each employee one place to see their money from
work (next payday, allowance balances, claims, advances). Reimbursement becomes "snap the receipt,
get approved": our model reads the receipt and checks the arithmetic, and only claims it is sure
about are auto-approved. Everything else goes to a person with the reasons attached.

SDG fit (Abdullah to support every number with a cited source; we do not invent statistics):
- **SDG 8, Decent Work** (8.5 fair pay, 8.10 access to financial services): reimbursement on time,
  plus interest-free salary advances instead of informal loans.
- **SDG 10, Reduced Inequalities**: out-of-pocket work costs weigh most on the lowest-paid.
- **SDG 16.5 / 16.6, Accountable institutions**: every claim has an audit trail, duplicate detection
  and stated reasons.

Not an ERP: we don't run payroll, HR or accounting. We read from payroll (salary, payday) and write
back one thing, the approved reimbursements and advances for the pay run (CSV export).

## 2. Users
| Role | Who | Main job in the app |
|---|---|---|
| Employee | e.g. a field sales officer | See money, submit claims, request an advance |
| Finance (approver + admin) | finance / HR officer | Review flagged claims, set allowance policy, export to payroll |
| (roadmap) Line manager | team lead | First-level approval: multi-step approvals are out of MVP |

## 3. Features
**P0 = must ship today. P1 = only if P0 is done and deployed. Roadmap = the pitch's "next" slide.**

### Employee
| # | Feature | Pri | Notes |
|---|---|---|---|
| E1 | **Payday card**: "Payday in 12 days (Fri 31 Oct)", expected net pay with breakdown | P0 | gross − tax − deductions − advance repayment + approved claims (cut-off on the 25th) |
| E2 | **Allowance wallets**: limit, used, pending, left, reset date | P0 | Medical (annual), Fuel (monthly), Meals & client (monthly), Mobile/Internet (monthly), Learning (annual) |
| E3 | **Snap a claim (AI)**: photo/upload, then fields prefilled with per-field confidence, then the employee confirms, then the decision | P0 | phone camera opens directly (`capture="environment"`) |
| E4 | **My claims** with a status timeline: submitted, auto-approved / in review, approved / rejected, paid on payday | P0 | reasons shown in plain language |
| E5 | **Salary advance (earned wage access)**: up to 50% of salary earned so far this month, interest-free, repaid on payday | P1 | the SDG headline feature; finance approves |
| E6 | Payslips (history + this month's preview) and "what changed vs last month" | P1 | seeded payslips |
| E7 | Alerts: "PKR 12,000 medical left, resets 1 Jan", "claim needs a clearer photo" | P1 | derived, no push service |
| E8 | Salary certificate on demand (printable page) | P1 | often needed for bank loans and visas; HR usually takes days |
| E9 | Wallet forecast: "at this pace your fuel wallet runs out on the 22nd" | P1 | simple projection |

### Finance
| # | Feature | Pri | Notes |
|---|---|---|---|
| F1 | **Review queue**: receipt image with extracted fields, confidences, the model's reasons, duplicate warnings, employee edits; approve / reject with a note | P0 | |
| F2 | **Payroll export**: CSV of approved claims and advances per employee for the pay run | P0 | how we fit into existing payroll |
| F3 | Overview: claims this period, % auto-approved, time to approval, amount by wallet | P0 | computed from the DB; labelled **demo data** |
| F4 | Allowance policy editor: limits per wallet and grade, auto-approve on/off per wallet, per-claim cap | P1 | seeded values are visible in P0 |
| F5 | Audit log per claim (who did what, when) | P0 | stored as claim events; also feeds E4 |

### Deliberately out (say so in Q&A)
- **Attendance / leave:** no. It's an HR module, needs anti-spoofing (geofence, device trust) to mean
  anything, and has no link to our model. Roadmap: attendance-aware advances for daily-wage workers.
- Payroll calculation, tax filing, bank payouts, multi-company onboarding/SSO, native mobile app.

### Roadmap slide
Native mobile app (React Native / Expo on the same API: camera-first capture, offline queue, push
notifications); instant payouts through Raast; manager approval chains; payroll/HRIS API integrations;
LiLT transformer model; fine-tuning on consented fuel / pharmacy / Pakistani receipts; Urdu UI.

## 4. Where the AI is (and where it is not)
| Component | What it is | Honest label |
|---|---|---|
| Receipt reading | RapidOCR + CRF tagger (Rung 1), per-field confidence, temperature-calibrated | ML model, measured |
| Arithmetic check | subtotal + tax + service − discount = total | rule |
| **Auto-approval engine** | model decision combined with company policy (below) | model + rules |
| Duplicate detection | exact image hash, perceptual hash (near-identical photo), same amount + date + employee | image fingerprinting, not ML |
| Wallet suggestion | keywords in the receipt text (restaurant → Meals, fuel words → Fuel, pharmacy → Medical) | rules |
| Unusual amount flag | claim far above this employee's usual amount for that wallet | statistics |
| Optional extra (only if time) | LLM "can I claim this?" assistant over the policy text | labelled extra, off the critical path |

**Auto-approve only if ALL hold (server-side), otherwise review with every failed reason listed:**
1. Model says AUTO_POST (all fields ≥ 0.70 confidence, arithmetic not failing, nothing likely missed).
2. The employee did not change the total the model read.
3. The wallet has auto-approve on. **MVP: Meals only**, because the model is trained and validated on
   restaurant/café receipts (CORD). Fuel and medical are untested receipt types, so they always go
   to a person until we measure the model on them.
4. Amount ≤ wallet balance left and ≤ per-claim cap (e.g. PKR 5,000).
5. Not a duplicate; receipt date not in the future and not older than 60 days.

Measured so far (validation, real OCR): 81% of receipts auto-posted, 80 of 81 correct. The test set
is evaluated once before the pitch. **Out of distribution:** the model has never seen a petrol slip or a
Pakistani receipt. Rule 3 keeps these safe. Hassan's optional OOD check (section 8) measures it.

**Dates and merchants:** CORD has no date or merchant labels, so the model cannot read them. The
claim form takes the date (prefilled by a date regex when one is found, labelled as such) and an
optional merchant.

**Currency:** company currency PKR. CORD demo receipts are Indonesian rupiah, so the demo story is
a client visit to Jakarta: claim currency IDR, converted at a fixed rate shown as "demo rate".

## 5. Architecture and deployment
```
Phone / laptop browser
   │  Next.js 15 on Vercel (existing project; mobile-first, installable PWA)
   ▼
FastAPI on Railway (existing service; same Docker image)
   ├─ /extract, /results, /health          (existing model API)
   ├─ /auth, /me, /claims, /advances, /admin/*   (new)
   └─ SQLAlchemy ──► Postgres on Neon (free tier)    [local dev: SQLite file, automatic]
```
- **Database: Postgres on Neon free tier.**
  - Neon free tier: always on, 0.5 GB, no credit burn.
  - Railway Postgres would use the free plan's small monthly credit next to the API.
  - SQLite on Railway is wiped on every deploy.
  - Supabase adds a second auth system and row-level security to learn on deadline day, while our
    approval rules must live in the API anyway.
- Receipt images: stored in Postgres (JPEG ≤ 1600 px, about 200 KB), about 2,000 claims in 0.5 GB. Roadmap: object storage.
- Auth: email + password (bcrypt), JWT bearer token, two roles. The login page has
  "Try as employee" / "Try as finance" buttons for judges (seeded demo accounts).
- Secrets: `DATABASE_URL`, `JWT_SECRET` live only in Railway variables. Nothing new on Vercel
  except the same `NEXT_PUBLIC_API_URL`.
- RAM: CRF + OCR measured at 250 MB on Railway; the DB driver adds tens of MB, still under 512 MB.

### Data model
| Table | Key columns |
|---|---|
| companies | name, currency, payday rule, claim cut-off day, fx_rates (demo) |
| users | company, email, name, password_hash, role (employee/finance), grade, department, monthly_gross |
| wallets (allowance policies) | company, code, name, period (monthly/annual), limit per grade, auto_approve, per_claim_cap, max_receipt_age_days |
| claims | user, wallet, status, merchant, receipt_date, currency, amount, amount_pkr, fx_rate, edited_fields, model_name, model_decision, model_reasons, extraction (JSON), image_sha256, image_dhash, decided_by, reviewer_note, payroll_period |
| receipt_images | claim, jpeg bytes, width, height |
| claim_events | claim, ts, actor, event, detail (the audit trail and timeline) |
| advances | user, amount, status, requested_at, decided_by, repay_period |
| payslips | user, period, gross, tax, deductions, reimbursements, advance_repayment, net, paid_on (seeded) |

### API (new)
`POST /auth/login` · `GET /me/dashboard` (payday, wallets, alerts) · `POST /claims/scan` (image →
stored + extraction draft) · `POST /claims/{id}/submit` (confirmed fields → decision) · `GET /claims` ·
`GET /claims/{id}` · `POST /advances` · `GET /payslips` · `GET /admin/queue` ·
`POST /admin/claims/{id}/decide` · `GET /admin/overview` · `GET /admin/payroll.csv` · `GET/PUT /admin/wallets`

## 6. Frontend pages
`/login` · `/app` dashboard · `/app/claims/new` (camera → review fields → submit) · `/app/claims` and
`/app/claims/[id]` · `/app/advance` · `/app/payslips` · `/admin` overview · `/admin/review` and
`/admin/review/[id]` · `/admin/payroll` · `/model` (the existing Results page: public "how the AI works and how
we measured it"). The current `/batch` page is dropped; `/impact` is rewritten with honest numbers.

## 7. Demo (5 minutes, Sun 11:34)
1. Problem, one slide (30 s).
2. Employee on a phone: payday card and wallets (30 s).
3. Snap a meal receipt: fields with confidence, **auto-approved** with the reason (60 s).
4. Upload a fuel slip: **sent to review** with plain reasons (30 s).
5. Finance: review queue, approve, payroll CSV (45 s).
6. Salary advance request (30 s).
7. Evidence: validation and one-time test-set numbers, what we tried and rejected (45 s).
8. Roadmap (30 s).

## 8. Who does what today
- **Claude + Mohid:** backend (DB, auth, claims, approval engine, seed data, tests), frontend pages,
  deploy, one-time test-set evaluation, model card. Mohid: create the Neon project, phone testing,
  record a backup demo video.
- **Hassan (optional, valuable):** OOD check: 15-20 receipts (fuel, pharmacy, restaurant; Pakistani)
  with personal data blurred, **never used for training**. Report how many the model auto-posts and
  whether those are correct. LiLT training continues if already running.
- **Abdullah:** problem research with cited sources, personas, slides, demo script rehearsal,
  mobile-app mockup for the roadmap slide.

## 9. Risks
| Risk | Mitigation |
|---|---|
| Not enough time | Build P0 end to end and deploy first; P1 only after a working deploy |
| Wrong auto-approval on unfamiliar receipts | auto-approve only Meals (validated); caps; duplicate check; human review |
| Railway sleeps or is slow live | warm up before presenting; OCR thread fix; local fallback; backup video |
| Seeded data mistaken for real impact | every seeded number labelled "demo data"; model numbers come only from results files |
