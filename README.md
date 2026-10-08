# AICON'26 Build With AI — Team Cognivex

> AI-powered MVP built during the AICON'26 Build With AI hackathon.
> Domain: _TBA at the event_ · Problem: _TBA_

## Team

| Member | Role |
| --- | --- |
| Mohid Fida | Full stack: frontend, backend, deployment |
| Hassan | AI/ML: models, training, inference |
| Abdullah | Data, domain research, testing, pitch |

## Pipeline

```
Problem → Data/Input → AI Component → Solution/Output → Impact
```

_Architecture diagram and details added during the build._

## Repository structure

| Folder | Contents | Owner |
| --- | --- | --- |
| `frontend/` | Next.js app (deployed on Vercel) | Mohid |
| `backend/` | FastAPI service (deployed on Railway) | Mohid |
| `ml/` | Model loading, `predict()`, notebooks | Hassan |
| `data/` | Data cleaning scripts, synthetic data generators | Abdullah |
| `docs/` | Slides, notes, disclosures | Abdullah |

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

## Disclosure of pre-existing resources

In line with Rule 5 of the AICON'26 rulebook, everything below existed before the build period. All project-specific code was written during the event.

**Pre-event boilerplate (written by the team before AICON'26):**
- Repository structure, `.gitignore`, `.env.example`
- Generic FastAPI skeleton (`/health` endpoint, stub `predict()`, LLM fallback wrapper, predictions logging table)
- Deployment configuration for Vercel and Railway
- `setup_models.py` script that downloads public pretrained models

**Public models used:**
- _List added during the build (e.g. MobileNetV2 ImageNet weights via torchvision)_

**Public datasets used:**
- _List added during the build, with source and licence_

**APIs and services:**
- _List added during the build (e.g. Gemini API, Groq, Supabase)_

**AI coding assistants:** Claude Code, Antigravity, GitHub Copilot.

## Licence

MIT. See [LICENSE](LICENSE).