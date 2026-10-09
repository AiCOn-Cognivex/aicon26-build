# Backend image (FastAPI + RapidOCR + model). Works on Hugging Face Docker Spaces (port 7860)
# and on Railway/any Docker host (PORT env var).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces run as uid 1000
RUN useradd -m -u 1000 user
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY --chown=user ml ml
COPY --chown=user backend backend
COPY --chown=user results results
COPY --chown=user data/label_map.json data/label_map.json
COPY --chown=user setup_models.py .

USER user
ARG MODEL_REPO=""
ENV MODEL_REPO=${MODEL_REPO}
# Bake the model into the image so cold starts don't download it
RUN python setup_models.py
# Pre-download RapidOCR's bundled models check + warm import
RUN python -c "from rapidocr_onnxruntime import RapidOCR; RapidOCR()"

ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
