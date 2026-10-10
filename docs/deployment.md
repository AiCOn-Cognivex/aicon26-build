# Deployment

| Part | Host | URL |
|---|---|---|
| Frontend (Next.js) | Vercel, project `m0hid1/cognivex-aicon`, root `frontend/` | https://cognivex-aicon.vercel.app |
| Backend (FastAPI + RapidOCR + CRF) | Railway, project `cognivex-api`, service `api` (Dockerfile) | https://api-production-8136.up.railway.app |
| Model artifacts | Hugging Face model repo (public) | see README |

No ML or OCR runs on Vercel. Secrets are never committed: `.env` is gitignored, tokens live in the
HF / Vercel dashboards or in `hf auth login`.

## Why Railway with the CRF
Measured peak RSS while serving 10 validation receipts (real OCR): CRF + RapidOCR 228 MB,
LiLT + RapidOCR 1,040 MB. Railway allows 0.5 GB (Free) / 1 GB (Trial) per service
(docs.railway.com, 9 Oct 2026), so the live API serves the CRF (250 MB measured on Railway).
Hugging Face Docker Spaces were the first choice for LiLT, but creating one returned HTTP 402:
Docker Spaces on free CPU now require HF PRO. To serve LiLT live: build with
`--build-arg WITH_LILT=1` on a host with >= 2 GB RAM (e.g. Railway Hobby).

Measured live (10 Oct, 02:35 PKT, after the OCR thread fix, D18): `/health` reports `ocr_threads: 2`;
`/extract` OCR 0.4-0.7 s per receipt (was 9.9-14.8 s on the same 3 receipts before the fix); CORS header
returned for the Vercel origin.

## Environment variables

**Backend (Railway service variables)**
| Name | Example | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | `https://cognivex-aicon.vercel.app,http://localhost:3000` | CORS allow-list |
| `MODEL_KIND` | `crf` | `rules`, `crf`, `lilt`, or `auto` (best artifact present) |
| `MODEL_REPO` | `<hf-user>/cord-receipt-models` | public model repo pulled at image build |
| `OCR_THREADS` | `1` | optional; default = container CPU quota (shown in `/health`) |
| `DATABASE_URL` | `postgresql://...neon.tech/...?sslmode=require` | Postgres (Neon free tier). Unset: SQLite at `SQLITE_PATH`, re-seeded on every restart |
| `SQLITE_PATH` | `/tmp/cognivex.db` | SQLite fallback file (must be writable; set from PowerShell, Git Bash rewrites `/tmp` paths) |
| `JWT_SECRET` | long random string | signs session tokens; set via `railway variable set JWT_SECRET --stdin` |
| `GEMINI_API_KEY` | (secret) | optional fallback reader for receipt types our model was not trained on; never auto-approves |
| `GEMINI_MODEL` | `gemini-2.5-flash` | model name available to the key |
| `SEED_DEMO` | `1` | seed the fictional demo company on an empty database; enables `/admin/demo/reset` |

**Frontend (Vercel project env, Production)**
| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api-production-8136.up.railway.app` |

`NEXT_PUBLIC_*` values are baked in at build time: after changing it, redeploy (`vercel --prod`).

## Deploy steps
```bash
# backend (from the repo root; `railway login` once)
railway init --name cognivex-api
railway add --service api --variables "ALLOWED_ORIGINS=https://cognivex-aicon.vercel.app,http://localhost:3000" --variables "MODEL_KIND=crf"
railway up --service api --ci          # uploads git-tracked files, builds the Dockerfile
railway domain --service api           # public URL
# frontend
cd frontend
vercel env add NEXT_PUBLIC_API_URL production     # paste the Railway URL
vercel --prod --yes
```

## Cold starts
Railway keeps the service running (no sleep by default); a redeploy or crash restart takes about
30 s. The frontend handles it: on page load it polls `/health` every 3 s for up to
120 s and shows "Waking up the server... Ns". If the API never answers, the Batch Demo and Results
tabs still work from the snapshot bundled in `frontend/public/demo/`.
**Before the presentation:** open the site 5 minutes early and run one receipt so OCR models are loaded (first request is the slowest).

## Local fallback for the live demo (two commands)
From the repo root, in two terminals (the venv must exist: `py -3.13 -m venv .venv` and
`.venv\Scripts\pip install -r backend\requirements.txt` (plus `backend\requirements-lilt.txt` to serve
LiLT), and `cd frontend && npm install` once):
```powershell
.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000
cd frontend; npm run build; npx next start -p 3000      # NEXT_PUBLIC_API_URL defaults to http://localhost:8000
```
Open http://localhost:3000. With no internet at all, everything works except fonts are system fonts anyway.
