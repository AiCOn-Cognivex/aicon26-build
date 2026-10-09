"""FastAPI service: receipt image -> fields + AUTO_POST / HUMAN_REVIEW decision.

Env vars (all optional):
  ALLOWED_ORIGINS   comma-separated CORS origins (default "*")
  MODEL_KIND        rules | crf | lilt | auto (default auto = best artifact present)
  MODEL_DIR         where artifacts live (default ml/artifacts)
  OCR_THREADS       ONNX Runtime threads for OCR (default: the container's CPU quota)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml import predict as ml_predict  # noqa: E402
from ml.ocr import ocr_threads  # noqa: E402

log = logging.getLogger("uvicorn.error")
RESULTS = ROOT / "results"
DEMO = ROOT / "results" / "demo_examples.json"
MAX_BYTES = 8 * 1024 * 1024
STARTED = time.time()
# One OCR at a time: two in parallel only share the same CPU, and each adds ~100 MB of RAM
_ocr_slot = asyncio.Semaphore(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        ml_predict.warmup()
        log.info("model ready: %s", ml_predict.tagger()[0])
    except Exception as e:  # app must still start (rules fallback inside predict)
        log.exception("warmup failed: %s", e)
    yield


app = FastAPI(title="Cognivex receipt extraction API", version="1.1.0", lifespan=lifespan)
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    name, rung, _, _ = ml_predict.tagger()
    return {"status": "ok", "model": name, "rung": rung, "ocr_threads": ocr_threads(),
            "policy": ml_predict.policy(), "uptime_s": round(time.time() - STARTED, 1)}


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "image larger than 8 MB")
    try:
        async with _ocr_slot:  # OCR runs in a worker thread so other requests are not blocked
            return await run_in_threadpool(ml_predict.predict, data)
    except Exception as e:
        log.exception("extract failed")
        raise HTTPException(422, f"could not process image: {type(e).__name__}") from e


@app.get("/results")
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
