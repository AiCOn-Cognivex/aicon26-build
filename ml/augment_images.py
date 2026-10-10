"""Image augmentation for training (augmentation B, D21) and the robustness stress test.

  python -m ml.augment_images --copies 2 --workers 4         # train + validation, 2 degraded copies each
  python -m ml.augment_images --stress                       # validation at fixed degradation levels
Each degraded copy is re-OCR'd with the production OCR and cached in data/cache/aug/ (gitignored):
{"id", "width", "height", "rot": degrees, "words"}. Labels are projected from gold onto the OCR words of the
copy (gold boxes rotated with the image), so a copy belongs to its source receipt and, in CV, only to the
training folds of that receipt (ml/cv.py --aug). Validation copies are never used to score anything except
the stress test. Test images are never touched here.
Degradations (photometric unless stated): blur, JPEG compression, Gaussian noise, brightness/contrast,
a soft shadow gradient, downscale-upscale, and a small rotation (geometric, up to +-3 degrees).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .dataset import ROOT, image_path, load_split

AUG = ROOT / "data" / "cache" / "aug"


def degrade(img: Image.Image, rng: random.Random, ops: dict | None = None) -> tuple[Image.Image, float]:
    """Random mix of 2-4 degradations (or the fixed `ops`). Returns (image, rotation in degrees)."""
    img = img.convert("RGB")
    if ops is None:
        names = ["blur", "jpeg", "noise", "light", "shadow", "scale", "rot"]
        ops = {n: None for n in rng.sample(names, rng.randint(2, 4))}
    rot = 0.0
    for name, v in ops.items():
        if name == "blur":
            img = img.filter(ImageFilter.GaussianBlur(v if v is not None else rng.uniform(0.6, 1.6)))
        elif name == "jpeg":
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=int(v if v is not None else rng.randint(15, 45)))
            img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        elif name == "noise":
            a = np.asarray(img).astype(np.float32)
            a += np.random.default_rng(rng.randrange(1 << 30)).normal(0, v if v is not None else rng.uniform(4, 12), a.shape)
            img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        elif name == "light":
            b, c = (v, v) if v is not None else (rng.uniform(0.7, 1.25), rng.uniform(0.6, 1.2))
            img = ImageEnhance.Contrast(ImageEnhance.Brightness(img).enhance(b)).enhance(c)
        elif name == "shadow":
            a = np.asarray(img).astype(np.float32)
            w = a.shape[1]
            depth = v if v is not None else rng.uniform(0.25, 0.55)
            ramp = np.linspace(1 - depth, 1, w) if rng.random() < 0.5 else np.linspace(1, 1 - depth, w)
            img = Image.fromarray(np.clip(a * ramp[None, :, None], 0, 255).astype(np.uint8))
        elif name == "scale":
            s = v if v is not None else rng.uniform(0.4, 0.75)
            w, h = img.size
            img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR).resize((w, h), Image.BILINEAR)
        elif name == "rot":
            rot = v if v is not None else rng.uniform(-3, 3)
            img = img.rotate(rot, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
    return img, rot


def rotate_box(box, deg, W, H):
    """Axis-aligned box of `box` after PIL's rotate(deg) about the image centre (expand=False)."""
    import math
    t = math.radians(deg)
    cx, cy = W / 2, H / 2
    xs, ys = [], []
    for x, y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
        dx, dy = x - cx, y - cy  # PIL rotates counter-clockwise on screen (y down)
        xs.append(cx + dx * math.cos(t) + dy * math.sin(t))
        ys.append(cy - dx * math.sin(t) + dy * math.cos(t))
    return [min(xs), min(ys), max(xs), max(ys)]


def _ocr(img):
    from .ocr import load_image, run_ocr
    buf = io.BytesIO()
    img.save(buf, "PNG")
    im = load_image(buf.getvalue())
    return im.width, im.height, run_ocr(im)


def _job(args):
    rec, copy, ops, seed_tag = args
    rng = random.Random(f"{rec['id']}-{copy}-{seed_tag}")
    img = Image.open(image_path(rec))
    img, rot = degrade(img, rng, ops)
    W, H, words = _ocr(img)
    return {"id": rec["id"], "width": W, "height": H, "rot": rot, "src_size": list(img.size), "words": words}


def _run_batch(pool, path, jobs, label):
    """OCR `jobs`, appending each result to `path` as it finishes; ids already in `path` are skipped,
    so a crashed run resumes where it stopped."""
    from .progress import Progress
    AUG.mkdir(parents=True, exist_ok=True)
    have = set()
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    have.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    pass  # a line cut off by the crash: that receipt is redone
    todo = [j for j in jobs if j[0]["id"] not in have]
    if not todo:
        print(f"[{label}] already complete ({len(have)})", flush=True)
        return
    good = [l for l in open(path, encoding="utf-8")] if path.exists() else []
    with open(path, "w", encoding="utf-8") as f:  # rewrite only complete lines, then append
        for l in good:
            try:
                json.loads(l)
                f.write(l if l.endswith("\n") else l + "\n")
            except json.JSONDecodeError:
                pass
        prog = Progress(len(jobs), label, done=len(jobs) - len(todo))
        for row in pool.imap_unordered(_job, todo, chunksize=2):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            prog.step()


STRESS = {  # fixed levels for the robustness stress test on validation images
    "blur_1.5": {"blur": 1.5}, "blur_2.5": {"blur": 2.5},
    "jpeg_25": {"jpeg": 25}, "jpeg_10": {"jpeg": 10},
    "noise_10": {"noise": 10}, "noise_20": {"noise": 20},
    "scale_0.5": {"scale": 0.5}, "scale_0.35": {"scale": 0.35},
    "dark_0.6": {"light": 0.6}, "shadow_0.5": {"shadow": 0.5},
    "rot_3": {"rot": 3.0}, "rot_6": {"rot": 6.0},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copies", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--levels", nargs="*", default=None, help="stress levels to run (default: all)")
    ap.add_argument("--splits", nargs="*", default=["train", "validation"])
    a = ap.parse_args()
    os.environ.setdefault("OCR_THREADS", "2")
    with Pool(a.workers) as pool:
        if a.stress:
            recs = load_split("validation")
            for name in a.levels or STRESS:
                _run_batch(pool, AUG / f"stress_validation_{name}.jsonl", [(r, 0, STRESS[name], name) for r in recs],
                           f"stress {name}")
            return
        for split in a.splits:
            recs = load_split(split)
            for c in range(1, a.copies + 1):
                _run_batch(pool, AUG / f"ocr_rapidocr_{split}_aug{c}.jsonl", [(r, c, None, "aug") for r in recs],
                           f"{split} copy {c}")


if __name__ == "__main__":
    main()
