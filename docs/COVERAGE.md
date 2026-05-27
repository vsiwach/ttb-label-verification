# Coverage Matrix — Handled vs Flagged for Human Review

> **Reading this document:** the rules engine has two responsibilities:
> (1) **decide** what it has high confidence about — auditable, citable
> verdicts; (2) **route the rest to human review** with an explicit reason
> and the regulation citation. This file enumerates which cases land in
> which bucket. Anything not listed as "handled" is flagged for review,
> never silently auto-passed.

The deterministic 27 CFR rules engine is exhaustively unit-tested
(69 tests in `backend/tests/`). It is the legal core. The cloud / mock /
on-prem inference adapter ONLY reads the label and reports observations;
every match / likely / flag decision and every Government Warning verdict
happens in the engine.

---

## Severity model — not every difference is a violation

TTB itself doesn't treat every label-vs-application delta equally. The engine
classifies differences into three severities that drive the verdict bucket.
The classifier for each field is tuned to match TTB practice: graduated
tolerances calibrated to 27 CFR-stated allowances where they exist, or to
real-world COLA review behavior where the regulation is silent.

### Per-field severity ladder

| Field | `match` (auto-pass-able) | `likely` (needs-confirm) | `flag` (needs-review) |
|---|---|---|---|
| **Brand name** | Case-folded equal after suffix-strip (`Imported Beer`, `Brewing Co`, `Vineyards`, `LLC`); OR matches the COLA form's `productName` (Fanciful Name) | Shortened/extended form of either brand or product (`Suprema` vs `Suprema Imported Beer`) | Substantively different name AND no product match |
| **Class & type** | Strict equal OR declared is an umbrella COLA code (`beer`, `table red wine`, `whisky specialties` — 50+ codes) matching any specific designation | Similarity ≥ 0.85 | Substantive mismatch |
| **Alcohol content** | Numeric % within 27 CFR tolerance: spirits ±0.3, wine ±0.5, beer/malt ±0.3 (27 CFR 5.65 / 4.36 / 7.65) | Within wider agent-review band: spirits ±1.0, wine ±1.5, beer ±1.0 | Beyond agent-review band |
| **Net contents** | Same volume after parsing to mL — within 2% on a standard fill (50, 100, 187, 200, 250, 330, 355, 375, 500, 700, 720, 750, 1000, 1500, 1750, 3000 mL; 12, 16 FL OZ etc.), 5% otherwise | 5-10% delta — possible misfill, agent verifies | >10% delta — substantive content difference |
| **Bottler name/address** | Label line CONTAINS the declared bottler OR the registered brand — extra detail (address, plant info) is informational, not violation | Brand-normalized similarity | Wholly different business entity |
| **Country of origin** | Country name appears as a word after stripping multilingual prefixes (`Product of / Produit de / Hecho en / Prodotto in / Erzeugnis aus / Feito em`) including dual-language displays; native aliases (`italia ≡ italy`) | Similarity match | Different country |
| **Government Warning verbatim** | Exact match after anchor extraction (`GOVERNMENT WARNING:` … `HEALTH PROBLEMS.`) + OCR-noise normalization (whitespace, punctuation spacing, hyphenation including space-broken `AL- COHOLIC`), case-insensitive | Near-verbatim (≥85% similarity — OCR slips, garbled prefix, broken hyphens) → records `verbatimMatch=True` + `near_verbatim` advisory deviation | Below 85% similarity — substantive paraphrase |
| **Warning casing/bold** | `casing_all_caps=True` (positive evidence — heading appears in detected text OR model self-reports caps) | Body-bold report → advisory only (vision-language models often misread all-caps body as bold) | Heading not all-caps |
| **Warning font size** | Measured height ≥ 27 CFR 16.22 minimum × 0.9 (10% bbox-measurement tolerance) | Measurement in the 50-90% band of threshold → advisory pass (likely scan-resolution artefact; TTB scans don't reliably preserve physical print resolution) | Below 50% of threshold — clearly substandard even accounting for scan-resolution slop |
| **Warning contrast / separate-and-apart** | Model self-reports `True` (default) | Model self-reports `False` → advisory deviation only; bucket does not downgrade. Vision-language self-reports on contrast/separation false-positive too often to be a hard gate | — |

### Verdict-bucket logic

| Severity | Definition | What the engine does | Examples |
|---|---|---|---|
| **Critical** | Substantive non-compliance with 27 CFR | `flag` → `needs-review` | Mandatory field absent from label; Government Warning paraphrased or missing |
| **Material** | Substantively wrong declared value beyond regulatory tolerance | `flag` → `needs-review` | Net contents >10% off; ABV outside the wider agent-review band; brand AND product both differ from label |
| **Borderline** | Within regulatory or border tolerance | `likely` → `needs-confirm` (agent verifies in seconds) | ABV 0.3-1.5% off; net contents 5-10% off; near-verbatim warning with OCR slip or broken hyphen |
| **Informational** | Stylistic / format / multi-image realities | `match` → `auto-pass`-able | Brand in ALL CAPS; "KY" abbreviation; "Product of France" prefix; bottler line with extra address detail; class-type umbrella matching |

**The pre-processing pipeline that makes this work** (it's where most of the
"clean approved → false flag" pressure was relieved):

1. `ApplicationData.productName` — when the COLA form's Fanciful Name is
   supplied, the engine accepts a label-extracted brand match against
   **either** the registered brand or the product/SKU. Real labels print
   whichever is more visually prominent.
2. **Brand normalizer** strips common business suffixes (`Imported Beer`,
   `Brewing Co`, `Vineyards`, `LLC`, etc.) before comparison.
3. **Class type umbrella matching** — 40+ COLA registry codes (`beer`,
   `table red wine`, `whisky specialties`) match any printed sub-designation
   (`Pilsner`, `Cabernet`, `Bourbon`).
4. **Net contents semantic match** — both sides parsed to mL, ≤5% delta = match.
   Handles multi-unit displays (`1 PINT (16 FL OZ)`).
5. **Alcohol content numeric match** — within 0.1%, any format
   (`% Alc./Vol.`, `% ABV`, `N Proof`).
6. **Country of origin multilingual + dual-language strip** —
   `Produit de / Hecho en / Prodotto in / Erzeugnis aus / Feito em` plus
   `PRODUIT DE FRANCE PRODUCT OF FRANCE`-style dual displays. Native-language
   country aliases (`italia ≡ italy`, `españa ≡ spain`).
7. **Government Warning near-verbatim** — ≥85% character similarity is
   `verbatimMatch=True` with a `near_verbatim` advisory. Anchor extraction
   at `GOVERNMENT WARNING:` and clip at `HEALTH PROBLEMS.` strip leading
   and trailing OCR junk before the similarity ratio, so noise outside
   the warning region can't drag the score down. Real paraphrase
   (substantive wording change inside the warning) still flags below 0.85.
8. **Empty declared field** (COLA form omits bottler etc.) → `match` with
   transparent note. No false flag from missing form data.
9. **Low-confidence extraction** (<0.60) demotes `match` → `likely` so a
   confident-but-wrong AI read can't auto-pass.
10. **Missing extracted on a non-warning field** → `likely` (multi-image
    reality; field may be on another panel), never `flag`.

The result: **only critical or material differences route to `needs-review`.**
Informational differences max out at `needs-confirm` (one-click agent confirm).

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
| Casing differences (e.g. `STONE'S THROW` vs `Stone's Throw`) | `likely` (generic fields) / `match` (Brand name field) | strict-equal fails; loose-equal succeeds. Brand-name casing differences are stylistic and routinely caused by labels printing in caps for prominence — those resolve to match. |
| Brand with common business suffix dropped on label (`Suprema Imported Beer` vs `SUPREMA`) | `match` | brand-normalizer strips suffixes like `Imported Beer / Brewing Co / Vineyards / LLC` before comparison |
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
| Country of origin in another language (`Produit de France`, `Hecho en Mexico`, `Prodotto in Italia`, `Erzeugnis aus Deutschland`, `Feito em Portugal`) | `match` | multilingual prefix list (en/fr/es/it/de/pt) + native country aliases (`italia ≡ italy`, `españa ≡ spain`) |
| Country of origin in dual-language display (`PRODUIT DE FRANCE PRODUCT OF FRANCE`) | `match` | iterative prefix strip up to 3 layers, then word-level country search |

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
| **Verbatim wording** | Anchor-extracted (clip at `GOVERNMENT WARNING:` … `HEALTH PROBLEMS.`) + normalized text (whitespace collapse, line-break and space-broken hyphen reattach, OCR punctuation-spacing tightening) case-insensitively compared to the canonical text | 16.21 |
| **Near-verbatim wording (≥85% similarity)** | Detected text is *almost* canonical — OCR slips, garbled prefixes, broken hyphens — rather than paraphrase. The engine sets `verbatimMatch=True` with a `near_verbatim` advisory deviation so the agent verifies visually; the verdict isn't auto-promoted to needs-review for a transcription slip. Real paraphrase (substantive wording change inside the anchored region) drops below 0.85 and produces `verbatim=False`. | 16.21 |
| **`GOVERNMENT WARNING` in all caps** | `casing_all_caps=False` AND heading not literally present in detected text → `casingBoldOk=False`, deviation type `casing` | 16.22 |
| **Body NOT bold** | `body_bold=True` → advisory deviation `bodyBoldAdvisory`. NOT a hard gate — vision models confuse all-caps text with bold weight at warning-text size, so this is informational only. | 16.22 |
| **Type-size threshold by container** | `≤237 mL → 1 mm; ≤3 L → 2 mm; >3 L → 3 mm`. **Always runs** — DPI from EXIF when present, falls back to the 300-DPI TTB submission default with `fontSizeDpiSource='assumed'`. Three-band verdict: measurement ≥0.9× threshold passes clean; 0.5-0.9× passes with `fontSizeAdvisory`; <0.5× hard-flags as `fontSize`. The advisory band exists because scan DPI doesn't reliably preserve physical print resolution. | 16.22 |
| **Contrast** | When extractor reports `contrast_ok=False` → advisory deviation `contrastAdvisory`. NOT a hard gate — vision-language self-reports on contrast are unreliable. | 16.22 |
| **Separate and apart** | When extractor reports `separate_and_apart=False` → advisory deviation `separationAdvisory`. NOT a hard gate — same reason. | 16.22 |
| **All-caps body** (printed verbatim) | Compliant — TTB requires fixed wording, not fixed case for the body | 16.21 |
| **OCR-introduced whitespace** (`"WARNING :"`, `"( 1 )"`) | Normalized away before comparison | — |

### Routed to human review (cannot resolve from a single image)

| Case | Behavior |
|---|---|
| **Bold weight of `GOVERNMENT WARNING` heading** | Not gated on (current model can't reliably detect bold from a single rendered image); the heading must be ALL CAPS, and the body must NOT be bold — those two are gated. The bold of the heading itself is **flagged for visual confirmation by the agent**. |
| **Exact font-size measurement in mm** | Now deterministic: `fontSizeMm` always computed (Tesseract bbox + EXIF DPI or 300-DPI default). The 50-90% advisory band routes scan-resolution artefacts to "confirm visually" without hard-flagging; <50% still produces a hard `fontSize` deviation. |
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
| `casing_all_caps` | Gated boolean — must be `True` (or heading literal in detected text) for `casingBoldOk` to pass |
| `body_bold`, `contrast_ok`, `separate_and_apart` | NOT gated — surface as `bodyBoldAdvisory` / `contrastAdvisory` / `separationAdvisory` only. Vision-language self-reports on these are unreliable. |
| `heading_bold` | Recorded but NOT gated (bold can't be reliably detected from a single image) |
| Warning bbox + EXIF DPI | Three-way fan-out: Modal Tesseract container provides bbox (back-scaled to original-image pixels) + EXIF DPI; rule engine pairs them and runs the deterministic three-band 16.22 verdict |
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
