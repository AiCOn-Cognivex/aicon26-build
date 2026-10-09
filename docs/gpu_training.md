# Training LiLT on the GPU machine

Everything except LiLT fine-tuning runs on a normal laptop. LiLT is the one heavy step:
on a laptop CPU (i7-1165G7) one epoch takes about 19 minutes (measured with `python -m ml.train_lilt --bench`),
and it needs 15-30 epochs. On a modest NVIDIA GPU the whole run is expected to take minutes.

The repo already contains everything training needs: the processed CORD v2 annotations
(`data/processed/`) and the cached real-OCR words for the train split (`data/cache/`).
No dataset download and no OCR is needed on the GPU machine.

## What you need
- An NVIDIA GPU with a recent driver (`nvidia-smi` must work). 4 GB VRAM is enough at batch size 8.
- Python 3.10-3.13 and git.
- Optional, to publish the model: a Hugging Face account and a **write** token (https://huggingface.co/settings/tokens).

## Steps

```bash
git clone https://github.com/AiCOn-Cognivex/aicon26-build
cd aicon26-build
```

**Linux / WSL / Git Bash**
```bash
HF_TOKEN=hf_xxx MODEL_REPO=<hf-user-or-org>/cord-receipt-models bash scripts/gpu_train.sh
```

**Windows PowerShell**
```powershell
$env:HF_TOKEN="hf_xxx"; $env:MODEL_REPO="<hf-user-or-org>/cord-receipt-models"
.\scripts\gpu_train.ps1
```

The script:
1. creates `.venv`, installs the CUDA build of torch (set `CUDA_TAG=cu118` for old drivers) and `ml/requirements-train.txt`;
2. prints `BENCH ... min/epoch` (sanity check that the GPU is used: you should see `device=cuda`);
3. trains the main model (`--source both`: CORD gold words + real-OCR words, max 30 epochs, early stopping
   on validation entity F1, best checkpoint restored) into `ml/artifacts/lilt/`;
4. trains the ablation model (`--source gold`) into `ml/artifacts/lilt_gold/` (skip with `ABLATION=0`);
5. uploads both folders to the HF model repo if `MODEL_REPO` is set.

Then push the experiment log so the run is traceable:
```bash
git add results/experiments.csv && git commit -m "LiLT training runs" && git push
```

## If something goes wrong
- `device=cpu` in the log: torch is the CPU build. `pip uninstall torch` and re-run (or set `CUDA_TAG`).
- CUDA out of memory: `--batch 4`.
- No HF account: zip `ml/artifacts/lilt` (about 500 MB) and copy it to the laptop into the same path.

## What happens next (on the laptop)
`python setup_models.py --repo <MODEL_REPO>` downloads the model; then `python -m ml.calibrate --model lilt`
fits the temperature and decision threshold on validation, and `python -m ml.evaluate` scores it in both modes.
