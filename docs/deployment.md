# Deployment

| Part | Host | URL |
|---|---|---|
| Frontend (Next.js) | Vercel, project `m0hid1/cognivex-aicon`, root `frontend/` | https://cognivex-aicon.vercel.app |
| Backend (FastAPI + RapidOCR + model) | Hugging Face Docker Space (free CPU, 16 GB RAM) | see README "Live links" |
| Model artifacts | Hugging Face model repo (public) | see README |

No ML or OCR runs on Vercel. Secrets are never committed: `.env` is gitignored, tokens live in the
HF / Vercel dashboards or in `hf auth login`.

## Why a Hugging Face Space, not Railway
Measured peak RSS while serving 10 validation receipts (real OCR): CRF + RapidOCR 228 MB,
LiLT + RapidOCR 1,040 MB. Railway's Free plan allows 0.5 GB per service and the Trial 1 GB
(docs.railway.com, checked 9 Oct 2026), so the transformer would not fit. A free CPU Docker Space has
16 GB. The Dockerfile also runs on Railway or any Docker host (it reads `PORT`).

## Environment variables

**Backend (Space variables)**
| Name | Example | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | `https://cognivex-aicon.vercel.app,http://localhost:3000` | CORS allow-list |
| `MODEL_KIND` | `auto` | `rules`, `crf`, `lilt`, or `auto` (best artifact present) |
| `MODEL_REPO` | `<hf-user>/cord-receipt-models` | public model repo pulled at image build |
| `OCR_ENGINE` | `rapidocr` | `tesseract` also installed in the image |
| `PREDICTIONS_DB` | `/tmp/predictions.db` | optional SQLite prediction log; unset = off |

**Frontend (Vercel project env, Production)**
| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | the Space URL, e.g. `https://<hf-user>-cognivex-receipt-api.hf.space` |

`NEXT_PUBLIC_*` values are baked in at build time: after changing it, redeploy (`vercel --prod`).

## Deploy steps
```bash
# backend (needs `hf auth login` with a write token)
.venv/Scripts/python scripts/deploy_space.py --space <hf-user>/cognivex-receipt-api \
    --origins https://cognivex-aicon.vercel.app,http://localhost:3000 \
    --model-repo <hf-user>/cord-receipt-models
# frontend
cd frontend
vercel env add NEXT_PUBLIC_API_URL production     # paste the Space URL
vercel --prod --yes
```

## Cold starts
Free Spaces sleep after 48 h without traffic; the first request then rebuilds/starts the container
(about 1-2 minutes). The frontend handles it: on page load it polls `/health` every 3 s for up to
120 s and shows "Waking up the server... Ns". If the API never answers, the Batch Demo and Results
tabs still work from the snapshot bundled in `frontend/public/demo/`.
**Before the presentation:** open the site 5 minutes early so the Space is awake.

## Local fallback for the live demo (two commands)
From the repo root, in two terminals (the venv must exist: `py -3.13 -m venv .venv` and
`.venv\Scripts\pip install -r backend\requirements.txt`, and `cd frontend && npm install` once):
```powershell
.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000
cd frontend; npm run build; npx next start -p 3000      # NEXT_PUBLIC_API_URL defaults to http://localhost:8000
```
Open http://localhost:3000. With no internet at all, everything works except fonts are system fonts anyway.
