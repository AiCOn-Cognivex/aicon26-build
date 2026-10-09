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

## Experimenting (Hassan)

After `scripts/gpu_train.*` has run once, the venv exists. Activate it in each new terminal:
```powershell
Set-ExecutionPolicy -Scope Process Bypass; .\.venv\Scripts\Activate.ps1     # Windows
source .venv/bin/activate                                                   # Linux/WSL
```

**Train variants** (each into its own folder; every run is appended to `results/experiments.csv`):
```bash
python -m ml.train_lilt --bench --batch 8                                              # speed check
python -m ml.train_lilt --epochs 30 --lr 5e-5 --source both --out ml/artifacts/lilt              # main
python -m ml.train_lilt --epochs 30 --lr 3e-5 --source both --out ml/artifacts/lilt_lr3e-5      # learning rate
python -m ml.train_lilt --epochs 30 --lr 8e-5 --source both --out ml/artifacts/lilt_lr8e-5
python -m ml.train_lilt --epochs 30 --lr 5e-5 --source gold --out ml/artifacts/lilt_gold        # data ablation
python -m ml.train_lilt --epochs 30 --lr 5e-5 --source both --freeze-layers 6 --out ml/artifacts/lilt_freeze6
python -m ml.train_lilt --epochs 30 --lr 5e-5 --source both --max-train 400 --out ml/artifacts/lilt_n400   # learning curve (1600 = all)
python -m ml.train_lilt --epochs 30 --lr 5e-5 --source both --wd 0.05 --out ml/artifacts/lilt_wd05
```
Only tune: learning rate, epochs, weight decay, freezing (and the data source ablation).
Early stopping (patience 6) on validation entity F1 is automatic; the best epoch is restored.

**Evaluate a variant on VALIDATION** (no images needed: uses the committed OCR cache):
```powershell
$env:LILT_DIR="ml/artifacts/lilt_lr3e-5"          # Linux: export LILT_DIR=ml/artifacts/lilt_lr3e-5
python -m ml.evaluate --model lilt --split validation --mode A    # gold OCR
python -m ml.evaluate --model lilt --split validation --mode B    # real OCR (what the app does)
python -m ml.calibrate --model lilt                               # decision policy + STP at 98%
```
Compare with the CRF line in the README (validation Mode B: posting-correct 83%, STP 52% with 52/52 correct).
**Pick the winner by validation Mode B** (posting-correct, then STP). Never touch the test split:
`ml.evaluate --split test` refuses without `--final`, and the one test run is done at the end on the laptop.

**Hand over the winner**
```bash
python scripts/upload_artifacts.py --repo <hf-user>/cord-receipt-models --path ml/artifacts/<winner> --as lilt
git add results/experiments.csv && git commit -m "LiLT experiments" && git push
git checkout -- results/ ml/artifacts/ 2>/dev/null; git status   # do NOT push other results/*.json or policy files
```
Tell Mohid the winner's folder name and its validation numbers; the laptop re-runs calibration + evaluation
with the downloaded model so all committed results come from one place.
