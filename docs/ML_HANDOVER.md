# ML handover for Hassan

Status as of **Sat 10 Oct, 00:30 PKT** (CRF tuned, see section 4b). Submission deadline: **Sat 10 Oct evening**.
Every number below comes from a file in `results/` (validation split, n=100 receipts, unless stated).
The test split has **not** been touched yet. It gets evaluated exactly once, at the end.

---

## 1. TL;DR

- We read a receipt photo, extract the amounts (total, subtotal, tax, service charge, discount) and line
  items, and decide **AUTO-POST** (safe to put in the ledger without a person) or **HUMAN REVIEW**.
- A trained **CRF** is live today. On real photos, with the same decision rules, it auto-posts **53%** of
  validation receipts with **0 wrong auto-posts**. The rules-only baseline auto-posts **34%**. That
  difference is our "the model matters" story.
- **Your job:** train **LiLT** (layout-aware transformer) on the GPU, try to beat the CRF on validation
  (real OCR), and hand over the best checkpoint. Commands: `docs/gpu_training.md`.
- **Where the CRF loses accuracy:** 16 of 25 wrong amounts are model errors (OCR read the number but the
  model missed it or picked the wrong one), and 9 are OCR errors. A stronger model has real room to help.

---

## 2. The system in 60 seconds (frontend + backend)

```
Browser (Vercel, Next.js)  --POST image-->  FastAPI on Railway  -->  ml/predict.py: predict(image_bytes)
https://cognivex-aicon.vercel.app            https://api-production-8136.up.railway.app
```

- **Frontend** (`frontend/`): 4 tabs.
  - *Extract & Decide*: upload a photo and see the boxes, fields, confidence, arithmetic check, decision and a mock ledger entry.
  - *Batch Demo*: 8 pre-computed validation receipts that work even if the API is down.
  - *Results*: reads the metric JSON files from the API and shows a rules-vs-model comparison.
  - *Impact Simulator*: clearly labelled SIMULATED.
  - It never computes ML itself; it only displays what the API returns.
- **Backend** (`backend/app/main.py`) has four endpoints:
  - `GET /health`: model name and decision policy.
  - `POST /extract`: image in, JSON out.
  - `GET /results`: all `results/*.json` files.
  - `GET /demo-examples`
- **The contract between ML and the app** is `ml/predict.py`. As long as `predict()` returns the same JSON
  keys, you can swap models without touching the frontend or backend.
- **Which model is served:** env var `MODEL_KIND` (`rules` | `crf` | `lilt` | `auto`).
  - Railway runs `crf`. The LiLT server needs about 1.05 GB RAM, which is more than Railway's limit.
  - If LiLT wins, it runs live from a laptop (local fallback), and its numbers appear in the Results tab.

---

## 3. Every AI/ML step, in order

| # | Step | What it does | Code |
|---|---|---|---|
| 1 | **OCR** | RapidOCR (PaddleOCR det+rec models on ONNX Runtime) returns text lines with boxes. Lines are split into words with proportional boxes. Image long side capped at 1600 px. | `ml/ocr.py` |
| 2 | **OCR normaliser** | Splits a quantity glued to a name ("1EGG" → "1", "EGG"). Same for every model. | `ml/ocr.py: normalise_words` |
| 3 | **Reading order** | Clusters words into visual lines (by vertical centre), then sorts left to right. Same for gold and OCR words. | `ml/layout.py` |
| 4 | **Token tagger** | Labels each word with a CORD category in BIO format (47 labels = 23 categories × B/I + O). Three interchangeable rungs (below). | `ml/taggers.py` |
| 5 | **Field assembly** | Joins B/I runs into entities. Amount = last numeric token of the entity. If a field has several candidates, the most confident wins. Items: name/qty/price grouped in reading order. | `ml/fields.py: assemble` |
| 6 | **Confidence** | Field confidence = **minimum** token probability inside the field (one doubtful token makes the field doubtful). Temperature scaling is applied to the probabilities first. | `ml/fields.py`, `ml/calibrate.py` |
| 7 | **Money parser** | One parser everywhere. "25.000", "25,000", "Rp 25.000,-" and "25.000,00" all become 25000. | `ml/money.py` |
| 8 | **Reconciliation** | Checks subtotal + tax + service − discount = total, also accepting tax-inclusive receipts. Tolerance min(50 IDR, 1%), chosen on **train** gold. It never edits numbers; it only reports which rule failed. | `ml/decision.py: reconcile` |
| 9 | **Decision policy** | AUTO-POST needs a total + arithmetic PASS + every field ≥ threshold. Policy fitted on **validation** (`ml/calibrate.py`), saved to `ml/artifacts/policy_<model>.json`. | `ml/decision.py: decide` |

### The three model rungs

| Rung | Model | Input features | Training |
|---|---|---|---|
| 0 | **Rules** ("before") | Keywords (TOTAL, SUBTOTAL, PB1/PPN/TAX, SERVICE, DISC), right-most amount on the line | none |
| 1 | **CRF** (live) | Word shape, money pattern, x/y position, keywords on the line and the line above, ±2 neighbouring words | sklearn-crfsuite, L-BFGS, c1/c2 picked on validation, about 80 s on CPU |
| 2 | **LiLT** (`SCUT-DLVCLab/lilt-roberta-en-base`, MIT) | Word tokens + bounding boxes (0-1000 normalised) | AdamW, linear warmup/decay, wd 0.01, grad clip 1.0, fp16 on GPU, early stopping on validation entity F1 (patience 6), best checkpoint restored, seed 42 |

### Training data (the important trick)
- **Gold words:** CORD's own word boxes with labels. Printed label words like "TOTAL" or "PB1:" are tagged `O`,
  because CORD marks them `is_key=1`. This was a real bug: fixing it took CRF posting-correct from 58% to 87% in Mode A.
- **OCR words with projected labels** (`ml/project_labels.py`): we ran RapidOCR on all 800 train images. Each
  OCR word takes the label of the gold word it overlaps most (at least 50% of its area). The model therefore also learns
  from real OCR splits and merges. `--source both` (gold + OCR) is the default. For the CRF it raised real-OCR
  posting-correct from 73% to 79%.
- Rare categories (fewer than 10 train entities) are merged (`data/LABELS.md`). The official 800/100/100 split is unchanged.
- No images are needed to train: `data/processed/*.jsonl` (annotations) and `data/cache/*.jsonl` (OCR) are in git.

---

## 4. Current model stats

**Mode A** = CORD's gold OCR words (isolates the tagger). **Mode B** = real OCR on the photo (what the app does).
Definitions: `ml/metrics.py`. An amount of 0 counts as absent (same ledger entry).

| Metric (validation) | Rules A | CRF A | Rules B | **CRF B (live)** |
|---|---|---|---|---|
| Token entity F1 (seqeval) | 0.611 | **0.934** | — | — |
| Key-field exact match (5 fields) | 0.914 | 0.972 | 0.878 | 0.952 |
| Posting-correct receipts (all 5 amounts right) | 71% | 95% | 61% | **83%** |
| Fully-correct receipts (+ every line item exact) | 32% | 78% | 14% | 20% |
| Line-item F1 strict / lenient name | 0.53 / 0.74 | 0.82 / 0.90 | 0.24 / 0.67 | 0.32 / 0.73 |
| **Auto-posted (STP)** | 42% | 60% | 34% | **53%** |
| **Correct among auto-posted** | 100% | 100% (60/60) | 100% (34/34) | **100% (53/53)** |

- **Calibration (CRF):** temperature 1.1. Token ECE 0.0144 → 0.0049. Field-level ECE 0.043 raw, 0.053 after
  temperature (the tagger cannot see OCR misreads; the decision does not rely on a confidence floor).
- **Chosen CRF policy:** require the arithmetic to PASS; confidence threshold 0. Any higher threshold only removed
  correct receipts on validation. Exact 95% CI for 53/53 is **93.3%–100%**, so 100 validation receipts cannot prove 98%.
- **LiLT so far:** only a 16-example smoke test (meaningless numbers). The CPU benchmark is 19 min/epoch, which is why it trains on the GPU.
- **OCR (validation):** RapidOCR finds 94% of gold header amounts (97% on the first 30). Tesseract finds 28% (first 30).
- **Speed and memory:**

  | | CRF server | LiLT server |
  |---|---|---|
  | Peak RAM | 228 MB (250 MB on Railway) | ~1,040 MB |
  | Model time per receipt | ~3 ms (tagging) | ~0.6 s laptop CPU (incl. OCR) |
  | OCR time per receipt | 1.8 s on the laptop, 8–12 s on Railway | same |

- Full log of runs: `results/experiments.csv`.

### 4b. CRF over/underfitting work (10 Oct, 00:00; details in `docs/decision_log.md` D15)
- **Diagnosis:** train F1 0.992 vs validation 0.931, token loss 0.046 vs 0.215. That's **overfitting** (high variance).
- **c1/c2 grid, 4-fold CV on train** (`results/crf_tuning_v1.json`): stronger penalties cut the gap from 0.105 to 0.034,
  but held-out F1 stays flat (and drops when the penalty is too strong, i.e. underfitting).
- **Learning curve:** validation F1 0.843 → 0.928 from 100 to 800 receipts and still rising, so the model is **data-limited**.
- **Fix that worked:** features v2 (amount rank on the receipt, repeated values, magnitude, next-line keywords) plus c1=0.5, c2=0.1.
  Lower CV loss at every setting tried. Validation Mode A posting-correct 91% → 95%, auto-posted 57% → 60% with all correct.
- **Real OCR (Mode B) did not move** (83%). Of the 24 wrong amounts left, 9 are amounts OCR never read, 9 are model misses,
  4 are wrong numbers (down from 6), and 2 are spurious. **This is where LiLT should help most.**
- **For LiLT,** `train_lilt` now prints `train_loss` and `val_loss` every epoch. Train loss falling while val loss rises means overfitting:
  lower lr or epochs, raise `--wd`, or `--freeze-layers 6`. Both losses staying high means underfitting: raise lr or epochs.
  Early stopping already restores the best epoch.

---

## 5. Where the errors come from (CRF, validation, real OCR)

17 receipts are not posting-correct, with 25 wrong amounts in total:

| Root cause | Count | Fix lives in |
|---|---|---|
| OCR read the amount, but the **model missed it** | 9 | model |
| OCR read the amount, but the **model picked the wrong number** | 6 | model / field assembly |
| **OCR never read the correct amount** | 9 | OCR |
| Model invented a field that isn't there | 1 | model |

Wrong fields by type: total 9, subtotal 6, tax 6, service charge 3, discount 1.

**Why receipts go to HUMAN REVIEW** (48 of 100): **37 have no subtotal**, so the arithmetic can't be
checked; 6 fail the arithmetic; 5 have no total found. The decision layer is safe, but the *no-subtotal*
group is the biggest STP lever.

---

## 6. How to improve accuracy (in priority order)

Rules of the game: tune **only on validation**, never on test (`ml.evaluate --split test` refuses without `--final`).
Change only learning rate, epochs, weight decay, freezing, and the data source. Every run is logged to `results/experiments.csv`.
**Pick winners on validation Mode B** (posting-correct first, then STP).

1. **Train LiLT properly (the biggest model-side lever: 16 of 25 errors are model errors).**
   Start with `--epochs 30 --lr 5e-5 --source both`, then try lr 3e-5 / 8e-5, `--freeze-layers 6`, and `--wd 0.05`.
   Evaluate each variant with `LILT_DIR=... python -m ml.evaluate --model lilt --split validation --mode B`, then run `ml.calibrate`.
   If LiLT barely beats the CRF, that's a fine result: we say so and the decision layer carries the value.
2. **Ablations worth reporting** (cheap and judge-friendly):
   - `--source gold` vs `both`: does training on OCR noise help?
   - `--max-train 400` vs 1600 chunks: a learning curve.
   - `--freeze-layers 6` vs full fine-tune.
3. **"Wrong number picked" errors (6).** In `ml/fields.py: assemble`, when there are several total candidates, we keep the most
   confident. Try "most confident, ties → the bottom-most / largest amount" and measure on validation. Fix it in code
   for all rungs, not per receipt.
4. **No-subtotal receipts (37 reviews).** An experiment: when there is no subtotal, check
   `sum(line items) + tax + service − discount = total` instead. Careful: on **train gold** the item-sum rule
   fails 9% of the time (`results/data_profile.md`), so it may send wrong receipts to auto-post. It must earn its place on validation.
5. **OCR misses (9).** Options are a larger OCR model (PaddleOCR server weights), a higher detection resolution, or
   training on OCR output (already done). Every OCR change needs the OCR cache regenerated
   (`python -m ml.ocr_cache --split train|validation`) and **all rungs re-evaluated**. It also affects live speed (section 8).
6. **Line items (strict F1 0.32 on real OCR)** suffer mostly from OCR spelling ("HINERAL" vs "MINERAL"). The lenient
   metric (0.73) shows the tagging is mostly right. This is low priority, because posted amounts are what matters for the ledger.

---

## 7. How to test the model as a user (live site)

1. Open **https://cognivex-aicon.vercel.app** and wait for the badge at the top right to say **"API online"**.
2. Get a test image. The 8 demo receipts are public, so download one:
   `https://cognivex-aicon.vercel.app/demo/validation_3.jpg` (also `_0, _2, _4, _5, _7, _8, _11`).
   Any receipt photo works (keep it under 8 MB). Don't use personal receipts with names or card numbers.
3. On **Extract & Decide** click *Choose or capture receipt*, pick the file, then press *Extract & decide*.
   Expect **about 10-13 s** (OCR on Railway's free CPU).
4. Read the result:
   - **Decision banner + reasons.**
   - **Receipt with coloured boxes.** Hover a box to see the word, the predicted label and the probability.
   - **Key fields** with confidence bars.
   - **Reconciliation** (✓/✗ per rule).
   - **Mock journal entry.**
   - **Line items.**
5. What the **live site** returns for these JPGs (tuned CRF, checked 10 Oct 00:35, HTTP 200 in 10-13 s each):

   | Image | Decision | Why |
   |---|---|---|
   | validation_3 | AUTO-POST | total 28,000 = subtotal 28,000 + tax 0, so the arithmetic reconciles (gold agrees) |
   | validation_5 | HUMAN REVIEW | faded receipt: OCR read the tax 727 as "222" and the total 8,000 as "B:000"; the model took 222 as the total. No subtotal was found, so nothing can be checked, and it goes to review instead of posting a wrong total |
   | validation_0 | HUMAN REVIEW | total 45,500 read correctly, but there's no subtotal, so the arithmetic can't be checked |
   | validation_7 | HUMAN REVIEW | OCR read the total as "59,50" (gold 59,500); arithmetic fails, so the misread is caught |

   The demo JPGs are resized copies of the CORD PNGs, so the Batch Demo tab (computed from the PNG OCR) can show a
   different reason for the same receipt. The decisions are the same. It's a nice illustration of OCR sensitivity, and of the
   decision layer refusing to auto-post when it can't verify the numbers.
6. **Batch Demo** shows pre-computed results (instant, offline-safe). **Results** shows the rules-vs-model tables.
7. Without the UI (raw JSON):
   ```bash
   curl https://api-production-8136.up.railway.app/health
   curl -F "file=@validation_3.jpg" https://api-production-8136.up.railway.app/extract
   ```

---

## 8. Reducing live OCR time (currently 10–18 s per receipt on Railway)

OCR is about 98% of the server time (the CRF itself takes about 3 ms). Measured on the laptop, 30 validation receipts:

| Change | OCR time | Gold-amount recall | Notes |
|---|---|---|---|
| Current (1600 px, det + angle-cls + rec) | 1.04 s | 96.8% | baseline |
| **Turn off the angle classifier** (`use_cls=False`) | 0.86 s (**−17%**) | 96.8% | receipts are upright; cheapest win |
| Long side 1280 px | −16% | 96.8% | |
| Long side 1024 px | −27% | 96.8% | |
| Faster server CPU / more vCPUs | ~5× (laptop vs Railway) | same | Railway is ~5× slower than the laptop; a paid tier helps most |

How to ship a speed change safely:
1. Edit `ml/ocr.py`: pass `use_cls=False` in `rapidocr_words`, and/or change `max_side` in `load_image`.
2. Regenerate the OCR caches: `python -m ml.ocr_cache --split validation` (and `train` if the CRF/LiLT are retrained on it).
3. Re-run `ml.evaluate` (Mode B) and `ml.calibrate` for every rung, and confirm posting-correct and STP don't drop.
4. Commit, and Mohid redeploys (`railway up --service api --ci`).

All of this must happen **before** the single test-set run, because OCR settings count as frozen preprocessing.

---

## 9. Cheat sheet

```bash
python -m ml.train_lilt --epochs 30 --lr 5e-5 --source both --out ml/artifacts/lilt     # train (GPU)
LILT_DIR=ml/artifacts/lilt python -m ml.evaluate --model lilt --split validation --mode A
LILT_DIR=ml/artifacts/lilt python -m ml.evaluate --model lilt --split validation --mode B
LILT_DIR=ml/artifacts/lilt python -m ml.calibrate --model lilt
python -m ml.train_crf --source both            # CRF (CPU, ~4 min for the 3-setting grid)
python -m ml.evaluate --model crf --split validation --mode B
python scripts/upload_artifacts.py --repo <hf-user>/cord-receipt-models --path ml/artifacts/lilt --as lilt
```
Windows PowerShell: set variables with `$env:LILT_DIR="ml/artifacts/lilt"`. Full setup: `docs/gpu_training.md`.
Background on every decision: `docs/decision_log.md`.
