"""Upload trained artifacts to the public HF Hub model repo (needs HF_TOKEN with write access).

  python scripts/upload_artifacts.py --repo ORG/cord-receipt-models --path ml/artifacts/lilt --as lilt
  python scripts/upload_artifacts.py --repo ORG/cord-receipt-models --path ml/artifacts   # everything
"""
from __future__ import annotations

import argparse
import os

from huggingface_hub import HfApi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--path", default="ml/artifacts")
    ap.add_argument("--as", dest="dest", default="", help="folder name inside the repo (default: repo root)")
    a = ap.parse_args()
    api = HfApi(token=os.getenv("HF_TOKEN"))
    api.create_repo(a.repo, exist_ok=True, repo_type="model", private=False)
    if os.path.isdir(a.path):
        api.upload_folder(folder_path=a.path, path_in_repo=a.dest or ".", repo_id=a.repo,
                          ignore_patterns=["*_best_tmp/*", "*.tmp"])
    else:
        api.upload_file(path_or_fileobj=a.path, path_in_repo=a.dest or os.path.basename(a.path), repo_id=a.repo)
    print(f"uploaded {a.path} -> https://huggingface.co/{a.repo}/tree/main/{a.dest}")


if __name__ == "__main__":
    main()
