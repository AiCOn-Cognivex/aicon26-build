# CLAUDE.md: project context for AI coding sessions

Team Cognivex, AICON'26 "Build With AI". **Submission: Sat 10 Oct 2026 evening. Pitch: Sun 11 Oct, 11:34-11:39 PKT (5 min, live demo).**
Mohid = full stack and deploy (usually the person in the session), Hassan = AI/ML (LiLT on a GPU PC), Abdullah = data and pitch.

## What this is
**Cognivex Pay**: an employee finance web app (domain: finance, SDG 8). Employees see their next payday and take-home,
allowance wallets, provident fund, payslips and an interest-free salary advance, and claim receipts by photo. Our
receipt model (OCR + CRF tagger + calibrated decision) reads each receipt. A claim is auto-approved only if the model is
confident AND every policy check passes; otherwise finance reviews it. Finance has a queue, payroll CSV export and an
allowance policy editor. Not an ERP: no attendance, no payroll engine.

- Live: https://cognivex-aicon.vercel.app (frontend) · https://api-production-8136.up.railway.app (API, `/health`)
- Test logins (fictional demo company): `ayesha@northwind.example` (employee), `sara@northwind.example` (finance), password `Demo@2026`
- Read first: `README.md`, `docs/product_plan.md`, `docs/decision_log.md` (D1-D20+, why every choice was made), `docs/ML_HANDOVER.md`

## Repo map
- `ml/`: OCR (`ocr.py`), taggers (`rules_baseline.py`, `crf_model.py`, `lilt_model.py`), `fields.py`, `decision.py`,
  `predict.py` (the contract `predict(image_bytes) -> dict`), evaluation/calibration scripts. Artifacts in `ml/artifacts/`.
- `backend/app/`: FastAPI. `main.py`, `config.py`, `db.py`, `models.py`, `security.py` (OAuth2 password flow, bcrypt, JWT, roles),
  `seed.py` (demo company), `routers/` (auth, me, claims, advances, admin), `services/` (payroll maths, approval engine,
  receipt helpers incl. image hashes, QR, optional Gemini). Tests in `backend/tests/`.
- `frontend/src/`: Next.js 15 + Tailwind v4. `app/` (`/` sign-in, `/app/*` employee, `/finance/*` finance, `/model/*` public
  model pages, `/certificate`), `components/` (`ui.tsx`, `charts.tsx`, `shell.tsx`, `widgets.tsx`, `receipt.tsx`, `claimDetail.tsx`),
  `lib/` (`client.ts` authed API client, `auth.tsx`, `format.ts` incl. `APP_NAME`, `appTypes.ts`; `api.ts` is only for `/model`).
- `results/`: metric files written by scripts (never hand-written). `data/`: CORD prep, processed annotations, OCR cache.

## Commands (Windows; venv at `.venv`)
```powershell
.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000   # API: local SQLite + demo data, no setup
.venv\Scripts\python -m pytest backend\tests -q                   # API tests (must pass before any deploy)
cd frontend; npx tsc --noEmit; npx eslint src --quiet; npm run build # frontend checks
railway up --service api --ci          # deploy the API (git push does NOT deploy)
cd frontend; vercel --prod --yes       # deploy the frontend
python -m ml.evaluate --model crf --split validation --mode B        # model metrics
```

## Rules (do not break)
1. **Honest numbers.** Every model number comes from a file in `results/`. Never tune on the test split; the test set is
   evaluated exactly once (`ml.final_test`, refuses to overwrite). Seeded demo data is always labelled "Demo data". Don't invent statistics.
2. **Never break the live app.** Run the tests and builds before deploying, then verify live (`/health`, sign in, scan
   a sample receipt, finance queue). If a deploy breaks it, fix forward fast and log it in the decision log.
3. **No secrets in the repo.** `DATABASE_URL`, `JWT_SECRET`, `GEMINI_API_KEY` live only in Railway variables. Don't paste them in chat.
4. **Model scope.** The model is trained and validated on CORD v2 restaurant receipts. Instant approval stays Meals-only
   until another receipt type is measured. Pakistani receipts are evaluation-only unless the team decides otherwise.
5. **LLM features are optional and labelled.** Gemini is a fallback reader only and never auto-approves; it is off live.
6. **Commits:** short one-line messages, **no co-author / "Generated with" trailer**. Push to `main`.
7. Log every significant decision or incident in `docs/decision_log.md` (next number D27).

## Gotchas learned the hard way
- Postgres (Neon, live) enforces `VARCHAR(n)`; SQLite (local, tests) doesn't. Keep values within column sizes.
- Git Bash rewrites values starting with `/` (e.g. `/tmp/x`) into Windows paths: set such Railway variables from PowerShell.
- `NEXT_PUBLIC_API_URL` is baked in at build time; redeploy the frontend after changing it.
- Duplicate detection means a sample receipt can be claimed once. Finance overview -> **Reset demo data** restores the seed.
- Neon free tier sleeps after 5 min idle (first request +0.5-1 s). Railway runs in US West (sfo); Neon is in AWS us-west-2.
- OCR threads follow the container CPU quota (`ml/ocr.py`); this took live OCR from 10-15 s to under 1 s.
- `.gitignore` uses `/lib/` (root only) so `frontend/src/lib/` is tracked.
- `.railwayignore` keeps `railway up` small (no `data/`, `frontend/`, `results/cv/`); keep `data/label_map.json` (Dockerfile copies it).

## Design system
Tokens in `frontend/src/app/globals.css` (`@theme`): brand emerald `#0f7a55`, accent indigo `#5b6cf0` (a validated
two-series chart pair), soft canvas, 28px rounded cards (`.card`), pill buttons, Plus Jakarta Sans, lucide icons.
Prefer arcs, rings and rounded shapes over boxy layouts. Charts are custom SVG in `components/charts.tsx` with hover
tooltips. Text never uses series colours. Check every page at desktop width and at 390 px.

## Open work (as of 10 Oct, 13:15)
- ML v2 is on branch `improve/v2` (decision log D20-D23): constrained decoding, receipt-confidence policy, deskew,
  qty default, final CRF on train+val. **Test set has been evaluated once** (`results/test_metrics.json`): never re-run.
  Merge + deploy (Mohid): backend tests, `predict()` smoke test, `railway up`, then rebuild demo examples from TEST
  receipts (`python -m ml.build_demo --split test`), swap the scan-page samples and `backend/seed_assets` (validation
  receipts are now training data for the final model), redeploy the frontend, verify live.
- [x] Demo receipts swapped to CORD TEST receipts (scan samples, seeded claims, /model examples), D24.
- `MODEL_CARD.md`, `docs/slides_outline.md`, `docs/demo_script.md` (5 min), `docs/judge_qa.md`.
- Team decision on collecting 60-100 real Pakistani receipts as an evaluation set (dev/test halves, personal data blurred); no public labelled Pakistani receipt dataset was found. Outline in `docs/product_plan.md` section 8.
- LiLT not trained (cannot be served on Railway: about 1.05 GB RAM); if added, report CV/validation numbers only.
- Gemini key (parked). Optional: trim dashboard queries (1.2 s on Postgres vs 0.55 s on SQLite).
