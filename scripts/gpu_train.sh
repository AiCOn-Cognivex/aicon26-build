#!/usr/bin/env bash
# Train LiLT on an NVIDIA GPU machine (Linux / WSL / Git Bash). See docs/gpu_training.md.
# Usage: HF_TOKEN=hf_xxx MODEL_REPO=ORG/cord-receipt-models bash scripts/gpu_train.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PY:-python3}
if [ ! -d .venv ]; then $PY -m venv .venv; fi
if [ -f .venv/bin/activate ]; then source .venv/bin/activate; else source .venv/Scripts/activate; fi
python -m pip install -q --upgrade pip
# CUDA build of torch: cu126 works with recent drivers (check `nvidia-smi`; use cu118 for old drivers)
python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null || \
  pip install -q torch==2.14.1 --index-url https://download.pytorch.org/whl/${CUDA_TAG:-cu126}
pip install -q -r ml/requirements-train.txt
python -c "import torch; print('cuda:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

python -m ml.train_lilt --bench --batch 8
# main run: gold + real-OCR words, early stopping on validation entity F1
python -m ml.train_lilt --epochs ${EPOCHS:-30} --lr ${LR:-5e-5} --batch 8 --source both --out ml/artifacts/lilt 2>&1 | tee lilt_train.log
# ablation (optional, ~same time): gold words only
if [ "${ABLATION:-1}" = "1" ]; then
  python -m ml.train_lilt --epochs ${EPOCHS:-30} --lr ${LR:-5e-5} --batch 8 --source gold --out ml/artifacts/lilt_gold 2>&1 | tee lilt_gold_train.log
fi

if [ -n "${MODEL_REPO:-}" ]; then
  python scripts/upload_artifacts.py --repo "$MODEL_REPO" --path ml/artifacts/lilt --as lilt
  [ -d ml/artifacts/lilt_gold ] && python scripts/upload_artifacts.py --repo "$MODEL_REPO" --path ml/artifacts/lilt_gold --as lilt_gold
fi
echo "DONE. Now: git add results/experiments.csv && git commit -m 'LiLT training runs' && git push"
