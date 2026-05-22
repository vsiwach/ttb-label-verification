# COLA Dataset — Download & Verify-Against-It

How to pull real COLA data at scale and run the app against it to measure accuracy, not just
eyeball a few labels.

---

## 1. Where to download the dataset

There are two real sources. **For an evaluation set, COLA Cloud is by far the easiest** because it
bundles the label images *with* the data and OCR'd text in one CSV.

### Option A — COLA Cloud (recommended for eval; CC0, no signup)
- Site: https://colacloud.us  ·  Docs: https://docs.colacloud.us
- **Free sample pack: ~1,000 recent COLA records with label images + extracted barcodes, CSV, ~500 KB, CC0-licensed, refreshed daily.** This is the ideal eval seed — perfect size, real images, no scraping.
- Full corpus (for reference): 2.9M+ applications since 2005, 5M+ label images, OCR text, barcodes, product categorization. Larger pulls are a paid product.
- Why it's good for us: it already has the application fields **and** OCR'd label text, so you get ground truth for fields the COLA *form* omits (ABV, net contents — recall the Jim Beam finding).

### Option B — Official TTB Open Data (sanctioned, data-only)
- TTB Open Data: https://www.ttb.gov/data
- Public COLA Registry "Search and Download" (CSV extract of search results — TTB ID, permit, serial, brand, class/type, origin, status, dates): https://catalog.data.gov/dataset/ttb-public-cola-registry-search-and-download-extract-data-about-colas-that-meet-specified--cafd3
- This gives the **data** fields and the TTB IDs; **images are not bundled** — you fetch each label per-COLA from its detail page (`publicViewAttachment.do`) for the sampled IDs. Use this if you want the official source or a custom stratified pull by class/type + origin.

> Note: I can't download these for you (they're bulk public datasets and I can't scrape), but both are free and direct — the harness below consumes whichever you choose.

---

## 2. Assemble a stratified eval set

Don't just grab 1,000 random rows — stratify so every category in `TEST_PLAN.md §B` is represented:
a bourbon, a scotch (import), a vodka, a table wine, a sparkling, an IPA, a seltzer/FMB, an import
tequila, an import wine, a liqueur, a cider, a sake. Aim for ~50–200 labeled cases to start.

- From COLA Cloud's sample CSV: filter rows by `class_type` / `origin` to cover the categories.
- From the official registry: run Advanced Search per category — select **Class/Type codes** (e.g., `101` bourbon, `81` table white wine, `154` scotch, `977/978` tequila) and **Origin codes** (domestic states vs import countries) with a date range, download the CSV, then fetch those TTB IDs' images.
- For a hard image-quality slice, filter **Received Code** to paper (`002`/`003`): those are scanned labels — lower-res, skewed — ideal for stressing the image-quality gate. Electronic (`001`) gives clean baselines.

Two ground-truth caveats baked into the harness:
- The COLA **form lacks ABV and net contents** — use COLA Cloud's OCR text (or the label image) as ground truth for those two fields, not the form.
- Every COLA in the registry is **approved** ⇒ compliant. So the real set measures **extraction accuracy** and **false-positive rate** (approved labels must auto-pass). It does **not** test violation detection — that's what the `synthetic/` set and `TEST_PLAN.md §C` are for.

### Creating realistic rejection cases from real labels
Because the registry only publishes *approved* labels, generate negatives by **mutating** real ones —
this gives you both approved (pass) and rejected (fail) cases on genuine artwork:
- Change the **application data** (e.g., declared net contents 750 mL → label still says 700 mL) → forces a field **flag**.
- Edit the **label image's warning** (title-case it, shrink it, paraphrase it) → forces a warning **flag**.
- **Crop out** the warning → tests **missing**.
Tag each mutated row with `expected_outcome = needs-review` in the CSV; leave untouched approved rows as `auto-pass`. The harness then validates both directions.

---

## 3. The verification harness

`eval/run_eval.py` (starter included) does this for each record:

1. Build `applicationData` from the dataset row (brand, class/type, ABV, net contents, bottler, beverage type, origin).
2. POST the label image + `applicationData` to the running backend's `POST /api/verify`.
3. Parse the `VerificationResult` and score it.

**Where 100% applies (important — we are not training a model).** The system has two layers and
they have different accuracy ceilings:

- **Rules engine (deterministic):** given correctly-extracted fields, the verdict is provably correct
  from 27 CFR. This **must be 100%** — proven by the backend's rules-engine unit tests (golden field
  inputs, no image) and reflected in the **synthetic** results below.
- **AI extraction (reads the image):** not deterministic, **not 100%**. End-to-end accuracy is bounded
  by how well the model reads real artwork; the human-in-the-loop is the backstop.

So don't expect 100% end-to-end on real photos — expect 100% on the rules engine + clean synthetic
labels, and a high extraction rate + near-zero false positives on real approved labels.

It computes and reports:

| Metric | Layer | Target |
|---|---|---|
| **Rules-engine unit tests** | rules engine (deterministic) | **100%** |
| **Synthetic: cases passed** (group + per-field + warning all correct) | rules engine on clean labels | **100%** |
| **Verdict accuracy** (got group == `expected_outcome`) | end-to-end | 100% on approved + mutated set, modulo extraction |
| **Field extraction accuracy** (extracted == ground truth) | extraction | ≥ 90% |
| **Auto-pass rate (approved real set)** | end-to-end | ≥ 95% (false-positive guard) |
| **Warning false-flag rate** (approved wrongly flagged) | end-to-end | < 3% |
| **Latency P95** | system | ≤ 5 s |

It writes `eval/report.md` + `eval/report.json` with the aggregate metrics and a list of every miss
(image, field, expected vs got) so you can see exactly where extraction or the rules engine slips.

### How to run
1. Start the backend (mock or cloud mode).
2. Put the dataset CSV + images where the script expects (see config at the top of `run_eval.py`).
3. `python eval/run_eval.py --api http://localhost:8000/api --csv data/cola_sample.csv --images data/images`
4. Open `eval/report.md`.

Run it on both sets: the **real** COLA sample (extraction + false positives) and the **synthetic**
fixtures (violation recall). Together they prove the system works on real applications *and* catches
the problems it's supposed to.

### A note on terms
COLA Cloud's CC0 subsets are free to use. If you fetch images directly from the official registry,
keep request volume modest and respect TTB's terms — the sanctioned bulk export is the Search-and-Download CSV.

---

## 4. Claude Code prompt to finish & run the harness

`eval/run_eval.py` is a working starter but needs its CSV column names mapped to whatever dataset
you downloaded. Paste this into Claude Code:

```
You are setting up and running an end-to-end evaluation of the TTB Label Verification backend
against REAL COLA applications + labels, plus the synthetic fixtures. Read test/EVALUATION.md,
test/TEST_PLAN.md, and test/eval/run_eval.py first. Work step by step; explain briefly as you go.

STEP 1 — Download a real COLA dataset into test/eval/data/
- Preferred: the COLA Cloud FREE sample (CC0, ~1,000 recent COLAs WITH label images + OCR text)
  from https://colacloud.us . Save the CSV to test/eval/data/cola_sample.csv and images to
  test/eval/data/images/. If the download needs a manual click/login or the URL isn't directly
  fetchable, STOP and tell me the exact file to download and where to put it.
- Alternative (official): the TTB data.gov "Public COLA Registry Search and Download" CSV
  (https://catalog.data.gov/dataset/ttb-public-cola-registry-search-and-download-extract-data-about-colas-that-meet-specified--cafd3)
  for the data fields, then fetch each sampled TTB ID's label image from its public detail page.
  Keep request volume modest, add a delay between requests, and respect TTB's terms.

STEP 2 — Build a stratified subset (~50-100 records)
Cover the categories in TEST_PLAN.md §B using the dataset's class/type + origin columns: a bourbon,
a scotch (import), a vodka, a table wine, a sparkling, an IPA, a flavored-malt/seltzer, an import
tequila, an import wine, a liqueur, a cider, a sake. Include a few PAPER-received (scanned) labels
to stress image quality. Save the chosen subset so the run is reproducible.
Then create ~5-10 REJECTION cases by mutating copies of approved labels — title-case the warning,
shrink it, paraphrase it, crop it out, or change the declared net contents — and tag those rows
`expected_outcome=needs-review`; leave untouched approved rows as `auto-pass`. The set now has both
APPROVED (must pass) and REJECTED (must fail) cases.

STEP 3 — Wire up run_eval.py
Inspect cola_sample.csv's real column names and update the COL mapping + derive_beverage() to match.
The COLA FORM lacks ABV and net contents — if the dataset has OCR'd label text, parse ABV
("NN% Alc./Vol.") and net contents ("NNN mL" / "NN FL OZ") from it for ground truth; otherwise leave
them blank and exclude them from extraction scoring. Add `requests` to dev/test deps; keep it light.

STEP 4 — Run it (backend up in CLOUD mode for real extraction)
- Real:      python test/eval/run_eval.py --api http://localhost:8000/api --csv test/eval/data/cola_sample.csv --images test/eval/data/images --limit 100
- Synthetic: python test/eval/run_eval.py --api http://localhost:8000/api --synthetic test/synthetic
Show me test/eval/report.md for both.

STEP 5 — Report & iterate against the targets in EVALUATION.md §3
First, run the backend's RULES-ENGINE UNIT TESTS (golden field inputs, no image) and confirm they
are 100% — that layer is deterministic and MUST be 100% since we don't train it. Then report the
end-to-end metrics: field extraction accuracy, verdict accuracy on the approved+rejected set,
auto-pass rate on the approved subset (false-positive guard), warning false-flag rate, latency P95,
and the synthetic group/field/warning accuracy + cases-passed. List the top extraction misses
(image, field, expected vs got). For any target not met, propose and APPLY a fix — usually to the
extraction PROMPT (field localization, exact warning transcription) or the RULES ENGINE (normalization
thresholds, font-size measurement) — then re-run until: rules-engine tests 100%, synthetic cases 100%,
approved auto-pass >= 95%, field extraction >= 90%, P95 <= 5s. End-to-end won't be 100% on real photos
(extraction is AI-bounded) — that's expected; the rules engine and synthetic set are where 100% lives.

STEP 6 — Integrate the harness into the system (make it first-class, not a one-off script)
- Add `requests` and `pytest` to the backend's dev/test dependencies.
- Add a pytest wrapper (e.g., backend test_eval_synthetic.py) that boots the backend in MOCK mode,
  runs the synthetic eval (test/eval/run_eval.py --synthetic test/synthetic), and ASSERTS the result
  is 100% (cases_passed == n; group + per-field + warning all correct). This runs in the normal
  `pytest` suite and in CI — it's the integration gate.
- Keep the RULES-ENGINE unit tests (golden field inputs, no image) as the deterministic 100% gate.
- Add convenience commands (Makefile targets or npm scripts) and document them in the README:
    eval-synth  -> synthetic mode, no API key, must be 100% (CI gate)
    eval-real   -> real mode against test/eval/data, prints the accuracy report (NOT a hard gate,
                   since end-to-end is extraction-bounded)
- The real-data run is an accuracy *report* you re-run when tuning, not a pass/fail CI gate.

Notes: real COLAs are MULTI-IMAGE (front/back/neck) — the Government Warning is usually on the BACK,
so verify the warning against the back image; do NOT flag a missing ABV on a plain beer; treat
allergen / Alcohol-Facts / cancer content as informational, never a rejection.
```
