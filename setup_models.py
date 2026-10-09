"""Download trained artifacts (CRF, LiLT, decision policy) from the public HF Hub model repo.

  python setup_models.py                       # uses MODEL_REPO env var
  python setup_models.py --repo ORG/NAME
Artifacts land in ml/artifacts/ (gitignored). Public repo -> no token needed.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "ml" / "artifacts"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.getenv("MODEL_REPO", ""))
    ap.add_argument("--revision", default=os.getenv("MODEL_REVISION", "main"))
    a = ap.parse_args()
    if not a.repo:
        print("MODEL_REPO not set: the API will use whatever is in ml/artifacts (rules baseline if empty).")
        return 0
    from huggingface_hub import snapshot_download
    ART.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(repo_id=a.repo, revision=a.revision, local_dir=str(ART),
                             token=os.getenv("HF_TOKEN") or None)
    print(f"downloaded {a.repo}@{a.revision} -> {path}")
    for p in sorted(ART.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(ART)}  {p.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
