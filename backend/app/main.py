"""FastAPI service: the employee finance app API plus the receipt-extraction model endpoints.

Env vars (all optional, see .env.example):
  ALLOWED_ORIGINS   comma-separated CORS origins (default "*")
  DATABASE_URL      Postgres URL (unset: local SQLite file, demo data re-seeded when empty)
  JWT_SECRET        token signing key (unset: random per process)
  GEMINI_API_KEY    optional: Ask Repay assistant + fallback receipt reader (Gemini; never auto-approves)
  GEMINI_MODEL      default gemini-3.8-flash
  MODEL_KIND        rules | crf | lilt | auto (default auto = best artifact present)
  OCR_THREADS       ONNX Runtime threads for OCR (default: the container's CPU quota)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml import predict as ml_predict  # noqa: E402
from ml.ocr import ocr_threads  # noqa: E402

from . import config  # noqa: E402
from .db import IS_SQLITE, Base, SessionLocal, engine  # noqa: E402
from .routers import admin, advances, auth, claims, me  # noqa: E402
from .services.common import run_predict  # noqa: E402
from .services.receipts import gemini_available  # noqa: E402

log = logging.getLogger("uvicorn.error")
RESULTS = ROOT / "results"
DEMO = ROOT / "results" / "demo_examples.json"
MAX_BYTES = 8 * 1024 * 1024
STARTED = time.time()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    if config.SEED_DEMO:
        from .seed import seed_demo
        try:
            with SessionLocal() as db:
                if seed_demo(db):
                    log.info("seeded demo company")
        except Exception:  # never take the API down because of demo data
            log.exception("demo seed failed")
    try:
        ml_predict.warmup()
        log.info("model ready: %s", ml_predict.tagger()[0])
    except Exception as e:  # app must still start (rules fallback inside predict)
        log.exception("warmup failed: %s", e)
    yield


class ServerTiming:
    """Adds `Server-Timing: app;dur=<ms>`: time spent inside the API, separate from the network (curl -i, devtools)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()

        async def send_timed(msg):
            if msg["type"] == "http.response.start":
                dur = f"app;dur={(time.perf_counter() - t0) * 1000:.1f}".encode()
                msg["headers"] = [*msg.get("headers", []), (b"server-timing", dur)]
            await send(msg)
        await self.app(scope, receive, send_timed)


app = FastAPI(title="Repay employee finance API", version="2.0.0", lifespan=lifespan)
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(ServerTiming)
for r in (auth.router, me.router, claims.router, advances.router, admin.router):
    app.include_router(r)


@app.get("/health")
def health():
    name, rung, _, _ = ml_predict.tagger()
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok", "model": name, "rung": rung, "ocr_threads": ocr_threads(),
            "database": {"ok": db_ok, "kind": "sqlite" if IS_SQLITE else "postgres"},
            "gemini_fallback": gemini_available(), "policy": ml_predict.policy(),
            "uptime_s": round(time.time() - STARTED, 1)}


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    """Public model demo: receipt image -> fields + AUTO_POST / HUMAN_REVIEW (no account, nothing stored)."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "image larger than 8 MB")
    try:
        return await run_predict(data)
    except Exception as e:
        log.exception("extract failed")
        raise HTTPException(422, f"could not process image: {type(e).__name__}") from e


@app.get("/results")
@lru_cache(maxsize=1)  # the files are baked into the image: read them once
def results():
    """All metric files produced by the evaluation scripts (never hand-written)."""
    out = {}
    for p in sorted(RESULTS.glob("*.json")):
        if p.name in ("demo_examples.json", "data_quality.json"):
            continue
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            out[p.stem] = {"error": "unreadable"}
    return out


@app.get("/demo-examples")
@lru_cache(maxsize=1)
def demo_examples():
    if not DEMO.exists():
        return {"examples": []}
    return json.loads(DEMO.read_text(encoding="utf-8"))


@app.get("/demo-examples/{name}")
def demo_image(name: str):
    p = (RESULTS / "demo_images" / name).resolve()
    if p.parent != (RESULTS / "demo_images").resolve() or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)
