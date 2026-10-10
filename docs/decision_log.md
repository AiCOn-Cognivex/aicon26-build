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

**Why the model matters (the before/after):** on real OCR (validation, n=100), with each extractor's
decision policy fitted on validation, the rules-only extractor auto-posts 36% of receipts (36/36 correct)
and gets all five amounts right on 65%; the trained CRF auto-posts 81% (80/81 correct) and gets 91% right.
Remove the model and about 45 percentage points of receipts go back to manual entry.
(`results/eval_{rules,crf}_validation_modeB.json`; history of these numbers in D12, D15, D16.)

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
Old model and the v1 feature code are in git history (commit 02cef9f); removed from the tree in D18.

### D16 · 10 Oct 01:00 · OCR improvements
Error analysis (CRF, validation, real OCR): 7 of 100 receipts had a needed amount that OCR never read
(accuracy ceiling about 93%). Failure types: amounts split by a space ("74." + "000"), amounts never
detected, digits misread. Settings were tuned on **200 TRAIN receipts** (gold-amount recall, i.e. how
many gold header amounts appear as a readable token): baseline 92.7%; + re-joining split amounts 93.6%;
+ angle classifier off 94.9% (the classifier sometimes flips upright text 180 degrees); lower text-score,
lower box threshold, larger unclip ratio, higher detection resolution: no gain beyond noise or slower;
contrast + sharpen preprocessing: worse (89.2%). Adopted: merge rule + classifier off.
**Validation confirmation:** 96.0% -> 99.1% (214 -> 221 of 223 amounts). OCR caches regenerated for all
splits. Same CRF, new OCR: posting-correct 83% -> 90%. Retrained on the new train OCR: **91%**; rules
baseline on the same OCR: 61% -> 65%. Re-fitting the policy (same pre-set rule: most coverage with >= 98%
on >= 20 auto-posts) now selects confidence >= 0.70 + absence check, no longer requiring a subtotal:
81% auto-posted, 80/81 correct (exact 95% CI 93.3%-100%). Safer point on the same curve: 0.80 -> 77%,
77/77. Kept the pre-set rule rather than switch after seeing results. Live OCR on Railway is still
10-14 s per receipt (text recognition dominates). Hassan must `git pull` before training LiLT (new OCR cache).

### D17 · 10 Oct 01:45 · Augmentation A (amount scaling) tried and rejected
Motivation: scaling every amount on a validation receipt by one factor (structure preserved) dropped
CRF total F1 0.965 -> 0.925, i.e. partial memorisation of amount values. Augmentation: 1-2 copies of
every training sequence with all amounts x2, x3, x10 or /10 (arithmetic and formats preserved;
`ml/augment.py`). Gates fixed in advance: (1) CV held-out loss/F1 not worse, (2) robustness to held-out
factors x4, x7, /100 improves, (3) validation real-OCR accuracy does not drop.
(1) With the original penalty, held-out loss got worse (0.241 -> 0.254 / 0.265): near-duplicate copies
weaken the effective regularisation. Scaling c1/c2 with the data size fixed it (2 copies, c1=1.5,
c2=0.3: loss 0.244, F1 0.921/0.872 vs 0.918/0.874). (2) Token F1 under scaling improved (e.g. /100: 0.910
-> 0.926) but posting-correct under scaling did not, and posting-correct on ordinary receipts fell
96% -> 93% (Mode A, paired). (3) Validation real OCR: posting-correct 91% -> 90%, fully-correct
21% -> 19%. **Rejected**; augmentation B (image augmentation + re-OCR) was gated on A and not run.
Likely reason: x10 / /10 creates implausible receipts, and real amount magnitudes carry signal (item
prices vs totals). Results stay in `results/crf_tuning_v2_aug*.json` and `results/robustness_crf.json`;
the code (`ml/augment.py`, `ml/robustness.py`) was removed in D18 and is in git history (commit 02cef9f).

### D18 · 10 Oct 03:00 · Codebase audit before the product build
Goal: keep only what the live product and Hassan's training need. Removed: augmentation code and flags
(D17), Tesseract engine (benchmark only, never in the image; its numbers stay in `results/ocr_benchmark.json`),
CRF feature set v1 and the `--features` switch (production uses v2), ablation pickles `crf_v1.pkl` /
`crf_gold.pkl`, the unused item-sum reconciliation switch, the optional SQLite prediction log, the HF Space
deploy script (402), unused training deps (pandas, lightgbm, accelerate, pytesseract). `python -m ml.train_crf`
now reproduces production by default (gold + OCR words, c1=0.5, c2=0.1).
Fixes: (1) `.gitignore` rule `lib/` also ignored `frontend/src/lib/`, so a fresh clone of the repo could not
build the frontend (the live site was deployed from a laptop); now tracked. (2) `/extract` ran OCR on the
event loop, so every other request waited ~10 s behind it; OCR now runs in a worker thread, one at a time.
(3) ONNX Runtime starts one busy-waiting thread per visible core; in a container capped at ~1 vCPU these
threads compete. Thread count now follows the container CPU quota (`OCR_THREADS` overrides). Laptop,
15 validation receipts: default 0.76 s, 1 thread 1.10 s, 2 threads 0.78 s, identical OCR output in all cases.
**Regression check:** rules and CRF, Mode A and B on validation, and end-to-end `predict()` on 6 images:
identical metrics and outputs before and after the audit.
**Live result (Railway, same 3 demo receipts, 02:2x vs 02:3x):** OCR 9.9-14.8 s -> **0.4-0.7 s**; the
container's quota is 2 CPUs (`/health` shows `ocr_threads: 2`); decisions unchanged (AUTO, AUTO, REVIEW).

### D19 · 10 Oct 03:00-07:30 · Pivot to an employee finance app; architecture
Team decision (Mohid): judges look for a full-stack product with SDG impact and meaningful AI, not a model
demo. Product: employee finance app (payday, allowance wallets, claims, salary advance, provident fund,
payslips) with our receipt model inside the reimbursement flow; finance console for review, payroll export,
policy. Attendance left out (HR module, no link to the model). Plan: `docs/product_plan.md`.
Choices: FastAPI + SQLAlchemy on the existing Railway service; Postgres on Neon (free, always on) with a
SQLite fallback; OAuth2 password flow with bcrypt hashes and HS256 JWT, two roles, login throttling;
receipt images stored in the database. **Auto-approval = model AUTO_POST AND amount not edited AND wallet
allows instant approval AND within balance and per-claim cap AND no duplicate AND receipt not older than the
wallet limit.** Instant approval is on for Meals only, because the model is validated on restaurant/cafe
receipts (CORD); fuel, medical and others always go to a person. Duplicates: exact image hash, 64-bit
difference hash (near-identical photo), same tax-invoice QR payload (FBR/PRA QR on Pakistani receipts,
decoded with OpenCV), same amount + date. Optional Gemini fallback reads receipts the model is unsure about
or that are not restaurant receipts; its readings are labelled and always go to a person. Seeded demo
claims with images use CORD validation receipts that are NOT among the public demo samples, and their
outcome is decided by the same engine. Tests: `backend/tests` (auth, roles, claim flow, duplicates,
advances, payroll, policy, demo reset).
Incident: first Railway deploy crashed (SQLite file not writable in the image; then Git Bash rewrote
`/tmp/cognivex.db` to a Windows path when setting the variable). Fixed with `SQLITE_PATH=/tmp/cognivex.db`
set from PowerShell and in the Dockerfile; API down about 10 minutes (07:00-07:10).
Second incident (10:31-10:45): after switching to Neon Postgres, the demo seed failed because the image
difference hash could overflow to a 17-character negative hex string; SQLite accepted it, Postgres enforces
VARCHAR(16). Fixed (Python ints, 64-bit mask), test added, event titles capped at their column length, and a
seed failure can no longer stop the API from starting. Live on Postgres since 10:45: health, sign-in, dashboard,
scan -> auto-approve, finance queue and role checks all pass.

### D20 · 10 Oct 11:10-11:30 · Improvement round v2 (Hassan): honest CV harness and failure taxonomy
Work on branch `improve/v2`; `main` tagged `pre-improve-baseline`. The validation numbers reproduce exactly
(CRF Mode B 91%, STP 81% with 80/81; Mode A 95%; rules Mode B 65%). The test split is still untouched
(no `results/test_metrics.json`; its OCR cache exists but no test metric was ever computed).
**New protocol** (`ml/cv.py`): group-aware 5-fold cross-validation over train + validation (900 receipts).
Groups = identical word sequences + near-duplicate templates (Jaccard >= 0.5 on distinctive words, i.e. words
on <= 3% of receipts): 676 groups, 332 receipts share a group, largest 12; 5 folds of 180
(`results/cv/cv_groups.json`). Each fold trains like production (gold + projected real-OCR words) and predicts its
held-out receipts; out-of-fold (OOF) predictions are cached so decoding and policies are tuned without
retraining. A change is adopted only if a paired cluster bootstrap (resampling groups) puts the 95% CI of
the gain above 0. Every run is logged to `results/cv/tuning_cv.json`.
**Baseline (production settings), OOF:** Mode B posting-correct **78.0%** (fold mean 78.0 +- 2.4), Mode A
88.2%, token F1 0.919; the 100 validation receipts inside CV score 88% (vs 91% for the model trained on all of
train). The deployed policy (confidence >= 0.70 + absence check) on OOF auto-posts 70.9% with **94.4%** correct
(602/638), vs 80/81 on validation (`results/cv/policy_cv_base_assemble.json`). Re-selecting the policy honestly
(chosen on 4 folds, applied to the 5th) reaches 96.8% (393/406) at 45% coverage when aiming for 98%.
**Reading:** the official validation split is optimistic for receipts from unseen shops/templates
(templated receipts score 84% OOF vs 74% for singletons). Validation numbers in the README remain labelled
as validation; the single test run is the independent check.
**Failure taxonomy** (`ml/taxonomy.py`, `results/cv/failure_taxonomy.json`; OOF Mode B, 198 of 900 receipts
wrong, 294 wrong fields): role confusion between header amounts 93 (e.g. subtotal tagged as total when they are
equal), gold amount tagged as a non-header label 67 (subtotal as an item price on one-item receipts, total as
the cash amount when paid exactly), OCR digit misread 31, missed field 26, amount never detected by OCR 23,
spurious field 21, wrong candidate kept 6, split amount 2. About 75% of wrong fields are model/assembly
errors, 19% OCR. By field: total 100, subtotal 79, tax 45, discount 26, service 19. Line items: wrong
quantity on 308 receipts (mostly a printed "1"/"2" that OCR drops or glues to the name), name spelling
(>= 0.8 similar) 333. Validation alone has only 9 failures (role confusion 4, non-header 3, OCR misread 2).
Next: attack role confusion with arithmetic-constrained decoding (cheap, no retraining).

### D21 · 10 Oct 11:30-12:00 · P1: constrained decoding, quantity default, parser repair, receipt confidence
All numbers are OOF over 900 receipts, real OCR, unless stated; gains are vs the D20 baseline with a paired
cluster bootstrap (`results/cv/`).
**Adopted**
- **Arithmetic-constrained decoding** (`ml/decode.py`): per field, the top-3 money tokens by the CRF's
  marginal probability plus "absent"; all joint assignments are scored by the sum of log-probabilities +
  lam x (arithmetic PASS +1 / not checkable 0 / FAIL -1, same rule as the decision layer). Nested selection
  (lam chosen on 4 folds, scored on the 5th) picked **lam = 1.5 in all 5 folds**: posting-correct
  78.0% -> 83.7% (+5.7 points, 95% CI +3.9 to +7.5; 59 receipts fixed, 8 broken). Plain per-field argmax
  (lam = 0) is worse than the CRF's Viterbi (-2.8), so the arithmetic term is what helps.
- **Money parser repair** of OCR letter/digit confusion inside amounts ("RP3O.OOO" -> 30000; only tokens
  made of digits, separators and O/o/D/Q/l/I/|). No gold value changes on train/validation. +2 receipts.
  Decoding stack total: **83.9%** (+5.9, CI +4.1 to +7.8; 61 fixed, 8 broken).
- **Missing item quantity defaults to 1** (flagged `qty_imputed`): OCR often drops a lone printed "1".
  Strict line-item F1 0.243 -> 0.407, fully-correct 16.4% -> 26.9% (+9.4 alone, CI +6.5 to +12.5).
  Honest cost: with CORD's gold words (Mode A, validation) fully-correct falls 78% -> 74%, because gold
  words keep every printed quantity and some items really have none. Kept, because real OCR is the app.
- **Receipt-level confidence** (`ml/confidence.py`, served by `ml/receipt_conf.py`): a logistic model on
  OOF predictions gives P(all five amounts right) from min field confidence, assignment posterior,
  arithmetic status, absence and OCR confidence, decoder agreement, field count. Calibrated (receipt ECE
  0.021, Brier 0.074). Policy = total found AND no arithmetic FAIL AND P >= threshold. Nested estimate
  (model and threshold chosen on 4 folds, applied to the 5th), target 98%: **58.9% auto-posted, 519/530
  correct (97.9%, exact CI 96.3-99.0%)**. Same protocol for the threshold policies: production policy
  (0.70 + absence) 70.9% at **94.4%** (602/638); best re-selected threshold policy with the new decoder
  53.3% at 97.5%. A 99% target is not reachable on unseen receipts with any policy tried (best: 37.7% at
  97.6%); remaining confident errors are mostly tax-included receipts (the arithmetic cannot see the tax),
  discounts printed outside the identity, and a few gold-label errors (e.g. train_191 tax "30.273 200").
- Validation (official split, production CRF trained on train, new policy): posting-correct 90% (was 91%,
  one receipt), auto-posted 75% with 75/75 correct (was 81%, 80/81), fully-correct 31% (was 21%), strict
  line-item F1 0.522 (was 0.345). Caveat: the receipt model was fitted on OOF predictions that include the
  validation receipts, so these validation STP numbers are not independent; the nested CV and the test run are.
**Rejected (logged in `results/cv/tuning_cv.json`)**
- CRF features v3 (OCR-robust keywords, nearest word left on the same physical row, amount position from
  the bottom, keyword lines sharing the value): +0.6 with Viterbi (CI -1.1 to +2.1), +0.3 with the new
  decoder (CI -1.0 to +1.6). Mode A 88.2% -> 90.0% but not the app's mode. Production keeps v2 (simpler).
- 500 L-BFGS iterations instead of 200: identical OOF (1 receipt better, 1 worse), 2.7x slower: the CRF has
  converged at 200.
- Deskewing word centres before line grouping: label and amount on the same visual line 75.2% -> 76.8% of
  gold header amounts; too small to justify retraining every rung now.
- Tax-included rate check (tax = total/11): only 9 of 800 train receipts are tax-included with a printed tax.
- Receipt-confidence model without the hard rules: 46.8% at 97.4% (it auto-posted a receipt with no total).
Tuning outputs moved to `results/cv/` so the app's `/results` payload is unchanged.

### D22 · 10 Oct 12:00-13:05 · P2: image augmentation, stress test, deskew
(PC crashed at 12:15 while 4 OCR workers and 5 CV trainers ran together; nothing committed was lost. Jobs
now run one at a time, and the augmentation OCR is resumable with a progress/ETA log.)
- **Augmentation B, rejected.** One degraded copy per receipt (2-4 of: blur, JPEG, noise, brightness/contrast,
  shadow, downscale, rotation up to 3 degrees with gold boxes rotated), re-OCR'd and labelled by projection
  (`ml/augment_images.py`; copies only in the training folds of their source receipt). Degraded copies keep
  68% labelled tokens (clean 69%) but only 87% of gold amounts are readable (clean 96%). OOF with the new
  decoder: 83.9% -> 84.4% (+0.6, CI -0.5 to +1.6, 12 fixed / 7 broken). On the stress test a train-only model
  with the copies was 0-6 points better per level, but that was not paired-tested and the clean gain is noise;
  training data triples. Not adopted.
- **Robustness stress test** (`ml/stress.py`, `results/cv/robustness_images_crf_*.json`): every validation image
  degraded at 8 fixed levels, production OCR + model + policy. Posting-correct before deskew: clean 90%, blur
  1.5/2.5 85%/65%, JPEG q10 66%, noise 20 52%, downscale 0.35 80%, shadow 93%, **rotation 3/6 degrees
  64%/45%**; auto-post correctness stayed >= 94% except rotation 6 degrees (16/20). Rotation was the weak spot.
- **Deskew at inference, adopted** (`ml/layout.py`): the tilt is estimated from the OCR word boxes (projection
  profile, +-5.7 degrees) and word centres are straightened before line grouping, only when the tilt is >= 1.5
  degrees. No re-OCR, < 5 ms. Training keeps the plain grouping (validated setting). Clean OOF: 83.9% -> 83.9%
  (9 fixed / 9 broken); Viterbi-only 78.0% -> 79.4%. Stress, paired: rotation 3 degrees 64% -> 78%
  (+14, CI +6 to +22), rotation 6 degrees 45% -> 54% (+9, CI +2 to +17), auto-posts at 6 degrees 34/38
  correct; all other levels unchanged (CIs include 0). Deskew in training too, with no minimum angle,
  was rejected: -1.2 OOF (CI -2.5 to 0.0), it fired on 40% of receipts with ~1 degree tilt.
  Caveat: the decision to look at rotation came from this stress test on validation images; clean CV only
  establishes that deskew does not hurt.

### D23 · 10 Oct 12:45-13:15 · Freeze, final model, the one test-set run
Team decisions (Hassan): final CRF trained on **train + validation** (900 receipts; the CRF is data-limited), the
**v2 safe policy**, and the test set evaluated once after the freeze.
- Receipt-confidence model refitted on the OOF predictions of the exact production configuration (deskew at
  inference): nested estimate **64.6% auto-posted, 567/581 correct (97.6%, exact CI 96.0-98.7%)**, receipt ECE
  0.026; threshold 0.9331 (`results/cv/confidence_deskew_infer.json`, `results/threshold_curve_crf.json`).
- Validation numbers in the README come from the train-only CRF (`ml/artifacts/crf_train_only.pkl`, local) so they
  stay comparable; after retraining, validation is in-sample.
- Frozen at commit 1858835 (model, OCR settings, deskew, decoder, policy). Then `python -m ml.final_test
  --final-model crf --confirm`, once (`results/test_metrics.json`, commit 5d6ca49).
- **Test, real OCR (n=100):** CRF posting-correct **81%**, auto-posted **58% with 56/58 correct** (exact CI
  88.1-99.6%), fully-correct 17%, line-item F1 0.33 / 0.65; rules 55%, 30% auto-posted (29/30). Gold words: CRF 94%,
  86% auto-posted (85/86). Without 7 receipts duplicating train/validation text: 79.6%, 51/53. Unseen templates
  (64 receipts): 76.6%, 30/31. **This agrees with the CV estimate (83.9%, 97.6%) and not with the earlier
  validation figures (91%, 80/81)**, which the CV had already flagged as optimistic (D20).
- Not done in this round: LiLT (no GPU here). The test set is now used, so a later LiLT can only be reported with
  CV/validation numbers, labelled as such.
- App consequence (for Mohid): the app's sample receipts and seeded claims are validation receipts, which the
  final model has now seen. Proposed: regenerate demo examples from test receipts (`python -m ml.build_demo
  --split test`), point the scan page's samples at them, and rebuild `backend/seed_assets` the same way.

## Definitions (fixed before reporting; see `ml/metrics.py`)
- Field exact match: both absent, or both present with equal parsed amounts (0 = absent, D11).
- Correct line item: same normalised name, quantity and price. Lenient: price exact, name >= 80% similar.
- Posting-correct receipt: all 5 header fields right. Fully-correct: plus every line item.
- STP rate: share of receipts auto-posted. Auto-post correctness: posting-correct share of those.
