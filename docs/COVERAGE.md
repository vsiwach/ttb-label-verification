# Coverage Matrix — Handled vs Flagged for Human Review

> **Reading this document:** the rules engine has two responsibilities:
> (1) **decide** what it has high confidence about — auditable, citable
> verdicts; (2) **route the rest to human review** with an explicit reason
> and the regulation citation. This file enumerates which cases land in
> which bucket. Anything not listed as "handled" is flagged for review,
> never silently auto-passed.

The deterministic 27 CFR rules engine is exhaustively unit-tested
(62 tests in `backend/tests/`). It is the legal core. The cloud / mock /
on-prem inference adapter ONLY reads the label and reports observations;
every match / likely / flag decision and every Government Warning verdict
happens in the engine.

---

## Verdict bucketing (mirrors the frontend's `groupFor()`)

| Bucket | Meaning | Triggers |
|---|---|---|
| **`auto-pass`** | All checks confidently match. Agent can sign off without opening. | every field `match` + warning verbatim + `casingBoldOk` + `present` |
| **`needs-confirm`** (amber) | One or more fields had a *non-substantive* difference. Quick agent confirmation. | any field `likely`, OR any field `match` produced from a low-confidence extraction |
| **`needs-review`** (red) | A substantive issue is present, OR a mandatory element is missing/non-verbatim. Full agent review required. | any field `flag`, OR warning missing, OR warning not verbatim |

The engine is **conservative by design**: when in doubt, it routes up
(auto-pass → needs-confirm → needs-review), never down. A field can only
be `match` when the engine has high-confidence evidence; anything else is
at least `likely`.

---

## A. Field matching (3-state)

### Handled with verdict (no human review needed when `match`)

| Case | Verdict | How |
|---|---|---|
| Identical printed text | `match` | strict-normalized equality (whitespace + smart-quotes + Unicode) |
| Smart quotes / typographic punctuation | `match` | `’ → '`, `“” → "`, `– — → -` before comparison |
| Casing differences (e.g. `STONE'S THROW` vs `Stone's Throw`) | `likely` | strict-equal fails; loose-equal (case-folded) succeeds |
| Punctuation-only deltas (`12 FL OZ` vs `12 FL. OZ.`) | `likely` | trailing-punctuation strip + loose equality |
| State name vs abbreviation in addresses | `likely` | similarity threshold ≥ 0.85 after normalization |
| Net contents: same volume in different unit display | `match` | parse both sides to mL; within 5% = match (e.g. `1 PINT (16 FL OZ)` vs `1 pints`) |
| Net contents: substantive size mismatch (>5% delta) | `flag` | parses succeed but volumes differ |
| Alcohol content: same % in different formats | `match` | parse to numeric %; within 0.1% = match (`% Alc./Vol.` vs `% ABV` vs `Proof`) |
| Alcohol content: substantive ABV mismatch | `flag` | parses succeed but % differs by >0.1 |
| Class & type: COLA umbrella code (`beer`, `table red wine`) vs specific designation (`Pilsner`, `Cabernet Sauvignon`) | `match` | umbrella-class lookup table (~40 codes) |
| Class & type: substantive mismatch | `flag` | not strict-equal, no umbrella, no similarity ≥ 0.85 |
| Brand: completely different name | `flag` | strict + loose unequal, containment requires ≥60% length match, similarity < 0.85 |
| Brand: brand name embedded in longer fanciful text | `flag` (tightened) | short declared inside long unrelated extracted is substantive content difference |
| Country of origin with `Product of / Imported from / Made in / Bottled in / Distilled in` prefix | `match` | prefix strip + case-fold |

### Always flagged for human review

| Case | Status | Why |
|---|---|---|
| Low extractor confidence (< 0.60) on a "match" | demoted to `likely` | low-confidence reads can match by coincidence; human confirms |
| Field declared but not visible on this image | `likely` (with explicit note) | multi-image COLA reality; field may be on another panel |
| Field declared empty (COLA form gap, e.g. bottler line) | `match` (with transparent note) | no ground truth to compare against — the LABEL content is shown for the agent to verify against the form |

---

## B. Mandatory fields per beverage type

| Beverage | Required by 27 CFR | Engine behavior |
|---|---|---|
| **Spirits** (§5.63) | Brand, Class/type, Alcohol content, Net contents, Bottler name/address | All 5 verified |
| **Wine** (§4.32) | Brand, Class/type, Alcohol content, Net contents, Bottler name/address | All 5 verified |
| **Beer / malt** (§7.63) | Brand, Class/type, Net contents, Bottler name/address (ABV **optional**) | 4 fields verified; ABV checked only when class type indicates added flavors |
| **Hard seltzer / flavored malt** (§7.63 + added-flavors rule) | as Beer **plus** Alcohol content | Auto-detected from class type tokens (`seltzer`, `hard seltzer`, `flavored malt`, `flavored beer`, `fruit beer`, `spiked`, `ready to drink`, `rtd`) |
| **Imports (any beverage type)** | as base + Country of origin | Triggered when `applicationData.countryOfOrigin` is set |
| **Plain beer with no ABV on the label** | not a violation | Engine correctly omits the ABV check; matches TTB practice |

---

## C. Government Warning (27 CFR 16.21 / 16.22)

### Handled deterministically

| Check | Engine logic | Cite |
|---|---|---|
| **Presence** | `present` = false → `needs-review` with citation | 16.21 |
| **Verbatim wording** | Normalized text (whitespace collapse, line-break-hyphen reattach, OCR punctuation-spacing tightening) case-insensitively compared to the canonical text | 16.21 |
| **`GOVERNMENT WARNING` in all caps** | `casing_all_caps=False` → `casingBoldOk=False`, deviation type `casing` | 16.22 |
| **Body NOT bold** | `body_bold=True` → deviation type `casing` | 16.22 |
| **Type-size threshold by container** | `≤237 mL → 1 mm; ≤3 L → 2 mm; >3 L → 3 mm`. If measurable and below threshold → `fontSize` deviation; if **not measurable** → `fontSize=False` **with explicit "could not be measured; please confirm manually" note** (route to human review, not a hard reject) | 16.22 |
| **Contrast** | When the extractor reports `contrast_ok=False` → deviation type `contrast` | 16.22 |
| **Separate and apart** | When the extractor reports `separate_and_apart=False` → deviation type `separation` | 16.22 |
| **All-caps body** (printed verbatim) | Compliant — TTB requires fixed wording, not fixed case for the body | 16.21 |
| **OCR-introduced whitespace** (`"WARNING :"`, `"( 1 )"`) | Normalized away before comparison | — |

### Routed to human review (cannot resolve from a single image)

| Case | Behavior |
|---|---|
| **Bold weight of `GOVERNMENT WARNING` heading** | Not gated on (current model can't reliably detect bold from a single rendered image); the heading must be ALL CAPS, and the body must NOT be bold — those two are gated. The bold of the heading itself is **flagged for visual confirmation by the agent**. |
| **Exact font-size measurement in mm** | When unmeasurable, `fontSizeOk=False` with a "please confirm manually" deviation — explicit route to human review with the relevant threshold cited |
| **Very subtle spelling/punctuation errors** that survive OCR normalization (e.g. a single missing comma a TTB reviewer caught) | The verbatim check may pass; the engine cannot guarantee detection of single-character TTB findings. Agents reviewing the result still see the full detected text for comparison. |
| **Multi-image labels where the warning lives on a different panel than the one uploaded** | Use the back/strip image (build_dataset.py picks images whose OCR contains "GOVERNMENT WARNING"). When only one image is provided and the warning isn't on it, `present=False` → routed to `needs-review`. |

---

## D. Cases that are explicitly NOT in prototype scope

Documented here so the agent isn't surprised. These should be added to the engine before production, but the prototype routes them to human review by default.

| Case | Current behavior | Production path |
|---|---|---|
| Sulfite declaration (`CONTAINS SULFITES`) | Not extracted as a verified field; appears in the raw warning text. Not checked. | Add as a conditional field for wines ≥10 ppm SO₂ |
| `PHENYLKETONURICS: CONTAINS PHENYLALANINE` (aspartame) | Not checked | Add as a conditional disclosure |
| FD&C Yellow No. 5 disclosure | Not checked | Add as a conditional disclosure |
| Allergen declarations / Alcohol Facts panel / cancer-warning content | Informational only — **never a rejection** (matches TTB's current non-final rulemaking) | Stays informational |
| Distinctive liquor bottle approvals | Not specifically recognized; field-level rules still apply | Add bottle-shape flag |
| Certificate of Exemption (vs full COLA) | Not specifically detected; treated as a label approval | Recognize exemption rows |
| Pre-1999 data-only records (no image) | Image-pipeline 400 (corrupt image) — graceful but not contextual | Detect data-only and short-circuit with a clean message |
| Resubmission after rejection | No special handling; verified as normal | Add resubmission context lookup |

---

## E. Image-quality routing

| Condition | Engine response |
|---|---|
| Corrupt / unsupported file | 400 with plain-language error (rejected by image pipeline before extraction runs) |
| Sharpness + resolution score ≥ 0.55 | `legible=True`; processed normally |
| Score < 0.55 | `legible=False` with a "re-upload sharper / higher-resolution image" note |
| Mock mode with placeholder bytes | Skipped (lenient — for curl smoke-testing); cloud / on-prem are strict |

---

## F. Inference layer (the AI part) — what we trust vs verify

| Signal from model | How engine uses it |
|---|---|
| Field text values | Compared via the 3-state matcher; never trusted blindly |
| Per-field confidence scores | < 0.60 demotes "match" → "likely" so a confident-but-wrong extraction can't auto-pass |
| Warning text transcription | Engine does the verbatim comparison; model is told to NEVER auto-correct paraphrase |
| `casing_all_caps`, `body_bold`, `contrast_ok`, `separate_and_apart` | Gated booleans on the warning verdict |
| `heading_bold` | Recorded but NOT gated (bold can't be reliably detected from a single image) |
| `approx_font_mm` | When present → numeric threshold check; when `null` → `fontSizeOk=False` with explicit "please confirm" note |
| `image_quality.score` | Overridden by the server-side Pillow measurement when available |

---

## G. Test surface (where the 100% guarantee lives)

| Layer | Test | Result |
|---|---|---|
| Rules engine unit tests (golden inputs, no AI) | `cd backend && pytest` | **62/62 ✅** |
| Synthetic eval (9 fixtures via FastAPI, mock backend) | `make eval-synth` | **9/9 ✅** |

Both are deterministic. The synthetic eval is enforced as a `pytest` test
that boots its own backend (`backend/tests/test_eval_synthetic.py`).
This is the integration gate for CI.

The real-data accuracy report (`make eval-real`) is **not a hard gate** —
end-to-end accuracy is AI-bounded. See `test/eval/ANALYSIS.md` for the most
recent run and `test/EVALUATION.md` for the methodology.
