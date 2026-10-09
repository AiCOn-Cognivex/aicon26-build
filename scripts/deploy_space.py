"""Create/update the Hugging Face Docker Space that serves the backend API.

  python scripts/deploy_space.py --space USER/cognivex-receipt-api \
      --origins https://cognivex-aicon.vercel.app [--model-repo USER/cord-receipt-models]
Needs `hf auth login` (write token). Uploads only what the API needs (no training data).
Small artifacts in ml/artifacts (CRF, policies) are uploaded directly; LiLT is pulled at build time
from --model-repo by setup_models.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]

SPACE_README = """---
title: Cognivex Receipt API
emoji: 🧾
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Receipt extraction + AUTO-POST / HUMAN REVIEW decision API
---

Backend API for Team Cognivex (AICON'26). Source: https://github.com/AiCOn-Cognivex/aicon26-build

Endpoints: `GET /health`, `POST /extract` (multipart `file`), `GET /results`, `GET /demo-examples`.
Model trained on CORD v2 (CC-BY-4.0). OCR: RapidOCR (Apache-2.0).
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True)
    ap.add_argument("--origins", default="*")
    ap.add_argument("--model-repo", default="")
    ap.add_argument("--model-kind", default="auto")
    a = ap.parse_args()
    api = HfApi()
    api.create_repo(a.space, repo_type="space", space_sdk="docker", exist_ok=True)
    api.add_space_variable(a.space, "ALLOWED_ORIGINS", a.origins)
    api.add_space_variable(a.space, "MODEL_KIND", a.model_kind)
    if a.model_repo:
        api.add_space_variable(a.space, "MODEL_REPO", a.model_repo)
    (ROOT / "scripts" / ".space_readme.md").write_text(SPACE_README, encoding="utf-8")
    api.upload_file(path_or_fileobj=str(ROOT / "scripts" / ".space_readme.md"), path_in_repo="README.md",
                    repo_id=a.space, repo_type="space")
    api.upload_folder(
        folder_path=str(ROOT), repo_id=a.space, repo_type="space",
        allow_patterns=["Dockerfile", ".dockerignore", "setup_models.py", "backend/**", "ml/*.py",
                        "ml/artifacts/*.pkl", "ml/artifacts/*.json", "results/*.json", "results/*.md",
                        "results/demo_images/*", "data/label_map.json"],
        ignore_patterns=["**/__pycache__/**", "ml/artifacts/crf_gold.pkl"],
        commit_message="Deploy API",
    )
    host = a.space.replace("/", "-").replace("_", "-").lower()
    print(f"Space: https://huggingface.co/spaces/{a.space}")
    print(f"API:   https://{host}.hf.space/health")


if __name__ == "__main__":
    main()
