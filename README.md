# AICON'26 Build With AI — Team Cognivex

> AI-powered receipt and invoice processing for finance teams.
> Domain: Financial Operations · Problem: manual receipt data entry is slow and error-prone, and unsafe to automate without knowing when the extraction can be trusted.

## What it does

Upload a receipt image. The system runs OCR, extracts key accounting fields (total, subtotal, tax, discount, service charge, line items) with a trained model, checks the arithmetic, estimates per-field confidence, and decides **AUTO-POST** or **HUMAN REVIEW**.

Before/after: a rules-only extractor (current practice) vs a learned model plus a calibrated decision layer. Numbers are in `results/` and shown in the app's Results tab. _Results added during the build._

## Team

| Member | Role |
| --- | --- |
| Mohid Fida | Full stack: frontend, backend, deployment |
| Hassan | AI/ML: models, training, inference |
| Abdullah | Data, domain research, testing, pitch |

## Pipeline

Receipt image → OCR → learned token classifier → field parsing → arithmetic reconciliation → calibrated confidence → AUTO-POST / HUMAN REVIEW → ledger entry

_Architecture diagram added during the build._

## Repository structure

| Folder | Contents | Owner |
| --- | --- | --- |
| `frontend/` | Next.js app (Vercel) | Mohid |
| `backend/` | FastAPI service | Mohid |
| `ml/` | Model loading, `predict()`, training, notebooks | Hassan |
| `data/` | Data cleaning scripts, label mapping | Abdullah |
| `results/` | Metrics, experiment logs, figures (generated, never hand-written) | Hassan |
| `docs/` | Slides, demo script, decision log, deployment notes, disclosures | Abdullah |

## Live links

- Frontend: _TBA_
- Backend API: _TBA_ (health check at `/health`)

## Running locally

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp ../.env.example ../.env      # then fill in your keys
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Results

_Filled from `results/` after the final single test-set evaluation. Gold-OCR and real-OCR results are reported separately. Impact figures in the app are simulated, not measured._

## Limitations

- Trained on CORD v2 (Indonesian receipts). Performance on Pakistani receipts may differ substantially.
- The 98% auto-post correctness target is reported only as far as the validation data supports it.
- _More added during the build._

## Disclosure of pre-existing resources

In line with Rule 5 of the AICON'26 rulebook, everything below existed before the build period. All project-specific code was written during the event.

**Pre-event boilerplate (written by the team before AICON'26):**
- Repository structure, `.gitignore`, `.env.example`
- Generic FastAPI skeleton (`/health` endpoint, stub `predict()`, LLM fallback wrapper, predictions logging table)
- Deployment configuration for Vercel and Railway
- `setup_models.py` script that downloads public pretrained models

**Public models used:**
- _List added during the build, with checkpoint name and licence_

**Public datasets used:**
- CORD v2 (`naver-clova-ix/cord-v2`), official train/validation/test split. _Licence verified and noted during the build._

**Libraries and OCR engines:**
- _List added during the build_

**APIs and services:**
- _List added during the build_

**AI coding assistants:** Claude Code, Antigravity, GitHub Copilot.

## Licence

MIT. See [LICENSE](LICENSE).