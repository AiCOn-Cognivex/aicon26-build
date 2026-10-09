# Backend image (FastAPI + RapidOCR + model). Runs on Railway or any Docker host (PORT env var).
# Build with --build-arg WITH_LILT=1 to include torch/transformers for the LiLT model (~1.05 GB RAM).
# Official python image via the AWS ECR Public mirror (Docker Hub rate-limited the Railway builder: 429)
FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 OMP_NUM_THREADS=2
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
WORKDIR /app
ARG WITH_LILT=0
COPY backend/requirements.txt backend/requirements-lilt.txt backend/
RUN pip install -r backend/requirements.txt && \
    if [ "$WITH_LILT" = "1" ]; then pip install -r backend/requirements-lilt.txt; fi

COPY --chown=user ml ml
COPY --chown=user backend backend
COPY --chown=user results results
COPY --chown=user data/label_map.json data/label_map.json
COPY --chown=user setup_models.py .

USER user
ARG MODEL_REPO=""
ENV MODEL_REPO=${MODEL_REPO}
# Bake any hub-hosted model into the image so cold starts don't download it
RUN python setup_models.py
# Load RapidOCR once at build time (fails the build early if OCR deps are broken)
RUN python -c "from rapidocr_onnxruntime import RapidOCR; RapidOCR()"

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
