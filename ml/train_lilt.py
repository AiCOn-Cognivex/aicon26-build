"""Fine-tune LiLT for CORD token classification (gold OCR words + boxes, train split only).

AdamW + linear warmup/decay, weight decay, dropout (model default 0.1), grad clipping,
early stopping on validation entity F1 (seqeval) with best-checkpoint restore, fixed seeds.
Every run is appended to results/experiments.csv.

Examples:
  python -m ml.train_lilt --bench                 # time 20 training steps, then exit
  python -m ml.train_lilt --epochs 30 --lr 5e-5   # full run (GPU: ~minutes, CPU: hours)
  python -m ml.train_lilt ... --push-to-hub AiCOn-Cognivex/cord-receipt-models
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from .dataset import gold_sequence, label_list, load_split, ROOT
from .layout import normalise_boxes
from .lilt_model import BASE_CHECKPOINT, chunk_words, encode, get_tokenizer


def set_seed(s):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    torch.cuda.manual_seed_all(s)


def build_examples(split, tok, l2i):
    exs, n_chunked = [], 0
    for rec in load_split(split):
        ws = gold_sequence(rec)
        texts = [w["text"] for w in ws]
        boxes = normalise_boxes(ws, rec["width"], rec["height"])
        labs = [l2i[w["label"]] for w in ws]
        chunks = chunk_words(tok, texts)
        n_chunked += len(chunks) > 1
        for s, e in chunks:
            enc = encode(tok, texts[s:e], boxes[s:e], labs[s:e])
            enc["doc"] = rec["id"]
            exs.append(enc)
    return exs, n_chunked


def collate(batch, pad_id):
    L = max(len(b["input_ids"]) for b in batch)
    def pad(key, val):
        return torch.tensor([b[key] + [val] * (L - len(b[key])) for b in batch])
    return {
        "input_ids": pad("input_ids", pad_id), "attention_mask": pad("attention_mask", 0),
        "bbox": torch.tensor([b["bbox"] + [[0, 0, 0, 0]] * (L - len(b["bbox"])) for b in batch]),
        "labels": pad("labels", -100),
    }


@torch.no_grad()
def evaluate(model, exs, labels, device, pad_id, bs=16):
    from seqeval.metrics import f1_score
    model.eval()
    y_true, y_pred = [], []
    for i in range(0, len(exs), bs):
        b = collate(exs[i:i + bs], pad_id)
        b = {k: v.to(device) for k, v in b.items()}
        logits = model(input_ids=b["input_ids"], attention_mask=b["attention_mask"], bbox=b["bbox"]).logits
        pred = logits.argmax(-1).cpu().numpy()
        gold = b["labels"].cpu().numpy()
        for p, g in zip(pred, gold):
            m = g != -100
            y_true.append([labels[x] for x in g[m]])
            y_pred.append([labels[x] for x in p[m]])
    model.train()
    return f1_score(y_true, y_pred)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--wd", type=float, default=0.01)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--warmup", type=float, default=0.1)
    ap.add_argument("--patience", type=int, default=6)
    ap.add_argument("--freeze-layers", type=int, default=0, help="freeze embeddings + first N encoder layers")
    ap.add_argument("--max-train", type=int, default=0, help="use only the first N train chunks (learning curve)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "ml" / "artifacts" / "lilt"))
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--push-to-hub", default="")
    a = ap.parse_args()

    from transformers import LiltForTokenClassification, get_linear_schedule_with_warmup
    set_seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    labels = label_list()
    l2i = {l: i for i, l in enumerate(labels)}
    tok = get_tokenizer()
    train, n_ch = build_examples("train", tok, l2i)
    val, _ = build_examples("validation", tok, l2i)
    if a.max_train:
        train = train[: a.max_train]
    print(f"device={device} labels={len(labels)} train_chunks={len(train)} (docs split: {n_ch}) val_chunks={len(val)}")

    model = LiltForTokenClassification.from_pretrained(
        BASE_CHECKPOINT, num_labels=len(labels), id2label=dict(enumerate(labels)), label2id=l2i).to(device)
    if a.freeze_layers:
        for p in model.lilt.embeddings.parameters():
            p.requires_grad = False
        for p in model.lilt.layout_embeddings.parameters():
            p.requires_grad = False
        for layer in model.lilt.encoder.layer[: a.freeze_layers]:
            for p in layer.parameters():
                p.requires_grad = False
    no_decay = ("bias", "LayerNorm.weight", "layer_norm")
    params = [
        {"params": [p for n, p in model.named_parameters() if p.requires_grad and not any(x in n for x in no_decay)], "weight_decay": a.wd},
        {"params": [p for n, p in model.named_parameters() if p.requires_grad and any(x in n for x in no_decay)], "weight_decay": 0.0},
    ]
    opt = torch.optim.AdamW(params, lr=a.lr)
    steps_per_epoch = (len(train) + a.batch - 1) // a.batch
    sched = get_linear_schedule_with_warmup(opt, int(a.warmup * steps_per_epoch * a.epochs), steps_per_epoch * a.epochs)
    use_amp = device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    pad_id = tok.pad_token_id
    out = Path(a.out)
    best_dir = out.with_name(out.name + "_best_tmp")
    best_f1, best_ep, bad, t_start = -1.0, 0, 0, time.time()
    model.train()
    history = []
    for ep in range(1, a.epochs + 1):
        rng = random.Random(a.seed + ep)
        order = list(range(len(train)))
        rng.shuffle(order)
        t_ep, loss_sum = time.time(), 0.0
        for st in range(steps_per_epoch):
            b = collate([train[i] for i in order[st * a.batch:(st + 1) * a.batch]], pad_id)
            b = {k: v.to(device) for k, v in b.items()}
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                loss = model(**b).loss
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            opt.zero_grad(set_to_none=True)
            sched.step()
            loss_sum += loss.item()
            if a.bench and st + 1 == 20:
                dt = (time.time() - t_ep) / 20
                print(f"BENCH {dt:.2f}s/step batch={a.batch} -> {dt * steps_per_epoch / 60:.1f} min/epoch on {device}")
                return
        f1 = evaluate(model, val, labels, device, pad_id)
        history.append({"epoch": ep, "train_loss": loss_sum / steps_per_epoch, "val_f1": f1, "epoch_s": time.time() - t_ep})
        print(f"epoch {ep} loss={loss_sum / steps_per_epoch:.4f} val_entity_f1={f1:.4f} ({time.time() - t_ep:.0f}s)", flush=True)
        if f1 > best_f1:
            best_f1, best_ep, bad = f1, ep, 0
            if best_dir.exists():
                shutil.rmtree(best_dir)
            model.save_pretrained(best_dir)
        else:
            bad += 1
            if bad >= a.patience:
                print(f"early stop at epoch {ep} (best {best_ep})")
                break

    # restore best checkpoint as the final artifact
    if out.exists():
        shutil.rmtree(out)
    shutil.move(str(best_dir), str(out))
    tok.save_pretrained(out)
    (out / "labels.json").write_text(json.dumps(labels))
    meta = {"base": BASE_CHECKPOINT, "args": vars(a), "best_epoch": best_ep, "best_val_entity_f1": best_f1,
            "history": history, "device": device, "train_time_s": round(time.time() - t_start),
            "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
            "label_map": json.loads((ROOT / "data" / "label_map.json").read_text())}
    (out / "train_meta.json").write_text(json.dumps(meta, indent=1))

    exp = ROOT / "results" / "experiments.csv"
    new = not exp.exists()
    with open(exp, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "model", "lr", "weight_decay", "batch", "epochs_max", "epochs_run", "best_epoch",
                        "freeze_layers", "max_train", "seed", "val_entity_f1", "train_time_s", "device"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), "lilt-roberta-en-base", a.lr, a.wd, a.batch, a.epochs,
                    len(history), best_ep, a.freeze_layers, a.max_train, a.seed, round(best_f1, 4),
                    meta["train_time_s"], meta["gpu"] or device])
    print(f"saved {out} best_epoch={best_ep} val_entity_f1={best_f1:.4f}")

    if a.push_to_hub:
        from huggingface_hub import HfApi
        api = HfApi(token=os.getenv("HF_TOKEN"))
        api.create_repo(a.push_to_hub, exist_ok=True, repo_type="model")
        api.upload_folder(folder_path=str(out), path_in_repo="lilt", repo_id=a.push_to_hub)
        print(f"uploaded to https://huggingface.co/{a.push_to_hub}")


if __name__ == "__main__":
    main()
