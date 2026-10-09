"""Rung 2: LiLT (Language-independent Layout Transformer, SCUT-DLVCLab/lilt-roberta-en-base, MIT).

LiLT reads each word together with its position on the page (bounding box), so it can learn
that "the number at the right end of the line that starts with TOTAL" is the total, rather than
relying on hand-written rules. We fine-tune it to tag every word with a CORD category.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from .layout import normalise_boxes, reading_order

BASE_CHECKPOINT = "SCUT-DLVCLab/lilt-roberta-en-base"
MAX_LEN = 512


def get_tokenizer(name_or_path: str = BASE_CHECKPOINT):
    # The checkpoint's tokenizer_config points at LayoutLMv3Tokenizer (which insists on boxes);
    # LiLT-roberta uses the plain RoBERTa BPE vocab, so load that directly. Boxes are added in encode().
    from transformers import RobertaTokenizerFast
    return RobertaTokenizerFast.from_pretrained(name_or_path, add_prefix_space=True)


def chunk_words(tokenizer, texts: list[str], max_len: int = MAX_LEN) -> list[tuple[int, int]]:
    """Split a word list into [start, end) ranges whose sub-token count fits in max_len."""
    lens = [max(1, len(tokenizer.tokenize(" " + t))) for t in texts]
    chunks, start, cur = [], 0, 0
    for i, n in enumerate(lens):
        if cur + n > max_len - 2 and i > start:
            chunks.append((start, i))
            start, cur = i, 0
        cur += n
    chunks.append((start, len(texts)))
    return chunks


def encode(tokenizer, texts, boxes, word_labels=None, max_len: int = MAX_LEN):
    """Words + 0-1000 boxes (+ optional label ids) -> model inputs; label on first sub-token only."""
    enc = tokenizer(texts, is_split_into_words=True, truncation=True, max_length=max_len)
    wids = enc.word_ids()
    bbox, labels, prev = [], [], None
    for wid in wids:
        if wid is None:
            bbox.append([0, 0, 0, 0])
            labels.append(-100)
        else:
            bbox.append(boxes[wid])
            labels.append(word_labels[wid] if (word_labels is not None and wid != prev) else -100)
        prev = wid
    out = {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"], "bbox": bbox}
    if word_labels is not None:
        out["labels"] = labels
    out["word_ids"] = wids
    return out


class LiltTagger:
    def __init__(self, model, tokenizer, labels: list[str], temperature: float = 1.0):
        self.model, self.tok, self.labels, self.T = model.eval(), tokenizer, labels, temperature

    @classmethod
    def load(cls, path: Path) -> "LiltTagger":
        from transformers import LiltForTokenClassification
        path = Path(path)
        torch.set_num_threads(max(1, torch.get_num_threads()))
        model = LiltForTokenClassification.from_pretrained(path)
        tok = get_tokenizer(str(path))
        labels = json.loads((path / "labels.json").read_text())
        return cls(model, tok, labels, 1.0)  # temperature set by taggers.load()

    @torch.inference_mode()
    def word_logits(self, ws: list[dict], width: float, height: float) -> np.ndarray:
        """Raw (uncalibrated) logits per word, shape [n_words, n_labels]."""
        texts = [w["text"] for w in ws]
        boxes = normalise_boxes(ws, width, height)
        out = np.zeros((len(ws), len(self.labels)), dtype=np.float32)
        for s, e in chunk_words(self.tok, texts):
            enc = encode(self.tok, texts[s:e], boxes[s:e])
            logits = self.model(input_ids=torch.tensor([enc["input_ids"]]),
                                attention_mask=torch.tensor([enc["attention_mask"]]),
                                bbox=torch.tensor([enc["bbox"]])).logits[0].numpy()
            seen = set()
            for ti, wid in enumerate(enc["word_ids"]):
                if wid is not None and wid not in seen:
                    seen.add(wid)
                    out[s + wid] = logits[ti]
        return out

    def tag(self, words: list[dict], width: float, height: float) -> list[dict]:
        ws = reading_order(words)
        if not ws:
            return []
        logits = self.word_logits(ws, width, height) / self.T
        p = np.exp(logits - logits.max(1, keepdims=True))
        p /= p.sum(1, keepdims=True)
        for w, row in zip(ws, p):
            k = int(row.argmax())
            w["label"], w["prob"] = self.labels[k], float(row[k])
            w["probs"] = {l: float(v) for l, v in zip(self.labels, row) if v > 1e-6}
        return _fix_bio(ws)


def _fix_bio(ws):
    """An I- tag that does not continue the same category becomes B- (standard BIO repair)."""
    prev = "O"
    for w in ws:
        lab = w["label"]
        if lab.startswith("I-") and prev[2:] != lab[2:]:
            w["label"] = "B-" + lab[2:]
        prev = w["label"]
    return ws
