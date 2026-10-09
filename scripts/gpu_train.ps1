# Train LiLT on an NVIDIA GPU Windows machine. See docs/gpu_training.md.
# Usage (PowerShell, from the repo root):
#   $env:HF_TOKEN="hf_xxx"; $env:MODEL_REPO="ORG/cord-receipt-models"; .\scripts\gpu_train.ps1
$ErrorActionPreference = "Continue"  # native tools write warnings to stderr; we check exit codes instead
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .venv)) { py -3 -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -q --upgrade pip
$cudaTag = if ($env:CUDA_TAG) { $env:CUDA_TAG } else { "cu126" }
& $py -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>$null
if ($LASTEXITCODE -ne 0) { & $py -m pip install -q torch==2.14.1 --index-url "https://download.pytorch.org/whl/$cudaTag" }
& $py -m pip install -q -r ml/requirements-train.txt
& $py -c "import torch; print('cuda:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

$epochs = if ($env:EPOCHS) { $env:EPOCHS } else { "30" }
$lr = if ($env:LR) { $env:LR } else { "5e-5" }
& $py -m ml.train_lilt --bench --batch 8
& $py -m ml.train_lilt --epochs $epochs --lr $lr --batch 8 --source both --out ml/artifacts/lilt 2>&1 | Tee-Object lilt_train.log
if (-not (Test-Path ml/artifacts/lilt/labels.json)) { Write-Host "TRAINING FAILED - see lilt_train.log"; exit 1 }
if ($env:ABLATION -ne "0") {
  & $py -m ml.train_lilt --epochs $epochs --lr $lr --batch 8 --source gold --out ml/artifacts/lilt_gold 2>&1 | Tee-Object lilt_gold_train.log
}
if ($env:MODEL_REPO) {
  & $py scripts/upload_artifacts.py --repo $env:MODEL_REPO --path ml/artifacts/lilt --as lilt
  if (Test-Path ml/artifacts/lilt_gold) { & $py scripts/upload_artifacts.py --repo $env:MODEL_REPO --path ml/artifacts/lilt_gold --as lilt_gold }
}
Write-Host "DONE. Now: git add results/experiments.csv; git commit -m 'LiLT training runs'; git push"
