"""Settings from environment variables (never commit real values; see .env.example)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Postgres in production (Neon); a local SQLite file when unset (demo data is re-seeded on start)
DATABASE_URL = os.getenv("DATABASE_URL", "")
SQLITE_PATH = os.getenv("SQLITE_PATH", str(ROOT / "backend" / "local.db"))

# Unset -> random per process (fine locally; tokens then expire on every restart)
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_TTL_MIN = int(os.getenv("JWT_TTL_MIN", "720"))

# Optional LLM fallback reader for receipt types our model was not trained on
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")  # stable GA model (Sep 2026); pin, not "-latest"

SEED_DEMO = os.getenv("SEED_DEMO", "1") == "1"
# Public password of the seeded test accounts (shown on the login page; demo data only)
DEMO_PASSWORD = "Demo@2026"
