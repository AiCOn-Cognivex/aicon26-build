# Decision log

Plain-language record of every AI/data decision, the evidence behind it, and what each part does.
Numbers come from files in `results/` (validation split unless stated). Times are PKT.

## How the system works (say this to a judge)

1. **OCR (RapidOCR).** Reads the photo and returns words with their positions on the page.
2. **Token tagger (the trained model).** Looks at every word, what it looks like and where it sits,
   and labels it: "this is the total", "this is an item name", "this is the tax", or "nothing".
3. **Field assembly.** Joins the labelled words into fields (total, subtotal, tax, service charge,
   discount) and line items (name, quantity, price). One shared money parser turns "25.000",
   "25,000" and "Rp 25.000,-" into the same number.
4. **Arithmetic check (reconciliation).** Does subtotal + tax + service - discount equal the total?
   It never changes a number; it only reports which rule failed.
5. **Decision.** AUTO-POST only if a total was found, the arithmetic reconciles, and every field is
   confident enough; otherwise HUMAN REVIEW with the reasons. The policy is tuned on validation data.

**Why the model matters (the before/after):** with the same decision rules, the rules-only
extractor auto-posts 34% of validation receipts, the trained CRF auto-posts 53%, both with no wrong
auto-posts on validation (real OCR). Remove the model and 19 percentage points of receipts go back
to manual entry. (`results/eval_{rules,crf}_validation_modeB.json`; 52% before the D15 tuning)

## Decisions

### D1 · 20:35 Fri · Repo audit
The README described a pre-event skeleton (FastAPI, stub predict, LLM wrapper, deploy configs).
The repository contained only README, LICENSE and .gitignore, so **all code was written during the
event**. The README disclosure was corrected accordingly.

### D2 · Dataset: CORD v2, official 800/100/100 split, unchanged
Licence CC-BY-4.0 (Hugging Face dataset card, checked 9 Oct). Profile: `results/data_profile.md`.
- 1 train record with a box slightly outside the image: logged, kept.
- 6 gold header values are "-" (no amount): treated as absent.
- Rare categories (<10 train entities) merged into their section's `.etc` label or `O` (fitted on
  train only; `data/LABELS.md`). Key accounting categories are never merged.
- **17 identical word sequences appear across splits** (templated receipts, e.g. same shop and
  order). We did not change the official split; the test report includes a de-duplicated subset.

### D3 · Money parser
Indonesian receipts use "." and "," as thousands separators. Rule: the last separator is a decimal
point only if followed by 1-2 digits; ",-" means ",00". Verified on every train gold amount shape.

### D4 · Reconciliation tolerance (chosen on TRAIN gold only)
On train gold, `subtotal + tax + service - discount = total` holds exactly for 581 receipts, within
rounding for more, and some receipts print tax as **included** (subtotal = total). We accept either
convention, with a tolerance of min(50 IDR, 1% of the amount): 13 of 522 checkable train receipts
still fail on gold. `sum(line items) = subtotal` fails on 9% of train gold, so it is **off**.

### D5 · OCR engine: RapidOCR
Validation, first 30 receipts (`results/ocr_benchmark.json`): RapidOCR found 97% of gold header
amounts vs 28% for Tesseract 5 (psm 4); 1.0 s vs 0.5 s per receipt; ~115 MB RAM; pip-only (ONNX),
so it deploys anywhere. Full validation: 94% key-amount recall.

### D6 · Rung 0: rules baseline
Keyword + regex rules (TOTAL, SUBTOTAL, PB1/PPN/TAX, SERVICE, DISC), right-most amount on the line.
This is how template tools work today, and it is our "before".

### D7 · Rung 1: CRF
A CRF labels each word from hand-made features (word shape, money pattern, position on page,
keywords on the line, neighbouring words) and learns which label sequences make sense.
c1/c2 chosen on validation entity F1 from 3 settings (`results/experiments.csv`). Trains in ~80 s.

### D8 · Bug found by error analysis: label words leaking into amounts
CORD marks printed label words ("PB1:", "Tax (10%)") with `is_key=1` inside the value line. They
were first labelled as part of the value, so "PB1: 5,409" was parsed as 15,409. Fix: key words are
labelled `O`, and a field's amount is its last numeric token. CRF Mode A posting-correct went 58% -> 87%.

### D9 · Train on what the model sees: OCR words with projected labels
Real OCR splits and merges words differently from the gold annotation. We ran RapidOCR on the train
images and gave each OCR word the label of the gold word it overlaps most (>= 50% of its area). The
CRF trained on gold + OCR words: Mode B posting-correct 73% -> 79%, Mode A about flat
(87% -> 89% posting-correct, fully-correct 76% -> 73%). Kept, because Mode B is the real app.

### D10 · OCR normaliser and lenient line-item metric
OCR glues quantities onto names ("1EGG"); we split a leading 1-2 digit quantity off (same for all
rungs). Strict line-item match needs exact names, which OCR misspellings break, so we also report a
**lenient** line-item F1 (price exact, name >= 80% similar). Both are reported; strict is primary.

### D11 · Metric revision 1 (after validation error analysis, before any test evaluation)
3 of 4 "wrong" CRF auto-posts were gold "0" (e.g. "Service 0") vs not extracted. Posting 0 and
posting nothing give the same ledger entry, so **an amount of 0 now counts as absent**, for all
rungs. Effect (validation Mode B posting-correct): CRF 79% -> 83%, rules 57% -> 61%.

### D12 · Calibration and the auto-post policy (validation only)
- Temperature scaling of CRF marginals: T = 1.1; token ECE 0.0097 -> 0.0093 (already calibrated).
  Field-level ECE is 0.08: the tagger cannot see OCR misreads.
- Policy search (`ml/calibrate.py`): maximise auto-post coverage with >= 98% correctness on at least
  20 auto-posted validation receipts. Switches tried: require reconciliation, OCR confidence,
  absence check, 15 thresholds. Chosen for the CRF: **require the arithmetic to reconcile; no extra
  confidence floor** (any threshold above 0 only removed correct receipts on validation).
- Result: 52/52 auto-posted correct (Mode B). **Honest limit:** with 52 receipts the exact 95%
  interval is 93.2%-100%, so validation cannot prove 98%. The single test-set run is the check.

### D13 · Hosting
Measured peak RAM serving 10 receipts: CRF + OCR 228 MB; LiLT + OCR 1,040 MB (INT8 dynamic
quantisation after loading did not lower the peak: 1,056 MB). Railway: Free 0.5 GB, Trial 1 GB
(docs, 9 Oct). First decision: a free Hugging Face Docker Space. Creating it failed with HTTP 402:
Docker Spaces on free CPU now need HF PRO. Final decision (Mohid): **backend on Railway serving the
CRF** (live: 250 MB RAM, about 10 s per receipt, OCR dominates), frontend on Vercel. If LiLT wins
on validation it is reported in Results and runs live in the local fallback. Cached demo examples
and a results snapshot ship with the frontend for offline demos.

### D14 · Rung 2: LiLT on a GPU machine
LiLT (`SCUT-DLVCLab/lilt-roberta-en-base`, MIT) reads each word with its box, so it learns layout
("the number at the right end of the TOTAL line") instead of hand-written features. LayoutLMv3 was
rejected: its weights are licensed non-commercial. CPU benchmark on the laptop: 19.3 min/epoch, too
slow for 15-30 epochs, so training runs on a separate GPU PC (`docs/gpu_training.md`). Same data,
same early stopping on validation entity F1, same evaluation.

### D15 · 10 Oct 00:00 · CRF over/underfitting diagnosis and tuning
**Diagnosis** (`results/fit_report_crf.json`): train entity F1 0.992 vs validation 0.931; token loss
(NLL) 0.046 vs 0.215 (4.7x) = **overfitting / high variance**.
**Regularisation grid** (`results/crf_tuning_v1.json`, 16 settings of c1 (L1) x c2 (L2), 4-fold CV on
train split by receipt, never validation): stronger penalties shrink the train/held-out F1 gap from
0.105 to 0.034, but held-out F1 stays flat (0.90-0.92 gold words, 0.86-0.87 OCR words) and drops at
the strongest settings (underfitting). **Learning curve** (validation F1 0.843 / 0.845 / 0.904 / 0.928
at 100 / 200 / 400 / 800 train receipts, still rising): the model is data-limited, so the penalty
alone cannot fix it.
**Features v2** (targeting the "wrong number picked" errors): amount rank on the receipt, value
repeated elsewhere, magnitude, relative size, position among amounts on the line, keywords on the next
line. Same CV: lower held-out loss at all 4 settings tried (by 0.010-0.012) and +0.2 to +0.4 F1 on OCR
words (`results/crf_tuning_v2_*.json`). Chosen by the script's criterion (best CV held-out F1):
**v2, c1=0.5, c2=0.1**.
**Before -> after on validation** (same decision layer, re-fitted on validation):
Mode A posting-correct 91% -> 95%, fully-correct 74% -> 78%, auto-posted 57% (56/57 correct) ->
60% (60/60); token F1 0.931 -> 0.934; token ECE after temperature 0.0093 -> 0.0049; raw field ECE
0.080 -> 0.043. **Mode B (real OCR, the live app): posting-correct unchanged at 83%**, auto-posted
52% -> 53% (all correct). Root cause on real OCR: "wrong number picked" fell 6 -> 4, but 9 errors
are amounts OCR never read and 9 are amounts the model missed; real-OCR accuracy is now limited by
OCR and data, not by CRF settings. Next levers: LiLT (pretrained, so less data-hungry), and OCR.
Old model kept as `ml/artifacts/crf_v1.pkl`.

## Definitions (fixed before reporting; see `ml/metrics.py`)
- Field exact match: both absent, or both present with equal parsed amounts (0 = absent, D11).
- Correct line item: same normalised name, quantity and price. Lenient: price exact, name >= 80% similar.
- Posting-correct receipt: all 5 header fields right. Fully-correct: plus every line item.
- STP rate: share of receipts auto-posted. Auto-post correctness: posting-correct share of those.
