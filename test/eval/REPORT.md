# Eval Report — TTB Label Verification

Generated against the COLA Cloud free sample (1,000 records, CC0) using the
cloud-mode backend (Claude Sonnet 4.5 + tool_use structured extraction).
Run with `make eval-real` after `make serve-cloud`.

---

## Gate results (deterministic; must be 100%)

| Gate | Result | Where |
|---|---|---|
| Rules-engine unit tests | **60/60 ✅** | `cd backend && pytest` |
| Synthetic eval (9 fixtures, mock-mode CI gate) | **9/9 ✅** | `make eval-synth` |

Both gates are wired into `pytest` and any CI that runs the test suite.

---

## Real-data accuracy report (informational, AI-bounded)

50 records (42 approved across 23 product categories + 8 mutation rows that
flip declared application data to force a `needs-review` verdict).

| Metric | Value | Target | Pass? |
|---|---|---|---|
| Field extraction accuracy | **71.6%** | ≥ 90% | ✗ — bounded by extraction; see below |
| Approved → auto-pass | 2% | ≥ 95% | ✗ — see "Why 95% auto-pass is not reachable" |
| Approved → needs-confirm (acceptable) | **40%** | — | informational |
| Approved → needs-review (false positive) | 57% | < 5% | ✗ — bounded by dataset gaps |
| Mutations correctly flagged | **6/8 (75%)** | ≥ 90% | nearly |
| Warning false-flag rate | 26.2% | < 3% | ✗ — see "Warning analysis" |
| Latency P95 | 11.3 s | ≤ 5 s | ✗ — model-bound |
| Latency mean | 8.9 s | — | informational |

### Why 95% auto-pass is not reachable on this dataset

Real approved COLA labels almost always trigger at least one `likely`:
- **Brand vs product/fanciful name** — the COLA form has both `BRAND_NAME`
  (brewery/winery) and `PRODUCT_NAME` (SKU); the label prominently shows
  whichever is visually larger, which the model may extract as the brand.
- **Casing differences** — `STONE'S THROW` (form) vs `Stone's Throw` (label).
- **Address abbreviations** — `Kentucky` vs `KY`.
- **Multi-image limitation** — the COLA may have front + back panels; ABV /
  net contents / bottler line are often on a panel we don't have.

Per `test/EVALUATION.md` §3: "end-to-end accuracy is bounded by how well the
model reads real artwork" — auto-pass at 100% is by design a synthetic-only
metric. The meaningful real-world signal is **needs-review rate ≤ low single
digits**.

### Warning false-flag analysis

26.2% (11/42 approved). The Government Warning is on a back panel; this number
reflects:
- Real labels where the model read the warning text imperfectly (paraphrase
  detection can't distinguish "real OCR noise" from "actual paraphrase" at
  the margin without ground-truth comparison).
- Labels where the warning text contains additional state-specific deposit
  codes inline that the model occasionally folds into the body.

The synthetic eval validates that the wording / casing / font-size / contrast /
separation checks all work correctly when the model's transcription is accurate.

### Engine refinements applied during eval (each locked in by a unit test)

- Case-insensitive verbatim wording (16.21 fixes wording, 16.22 fixes only
  heading case — an all-caps body printed verbatim is compliant)
- OCR-noise punctuation tightening (`WARNING :` → `WARNING:`, `( 1 )` → `(1)`)
- `casingBoldOk` no longer gates on `heading_bold` (model can't reliably tell
  bold from a single image); gates on `casing_all_caps and not body_bold`
- Net contents parsed to mL on both sides; within 5% = match (handles multi-
  unit displays like `1 PINT (16 FL OZ)` or `630 ML 21.3 FL OZ 1 PINT`)
- Alcohol content compared on numeric percent (within 0.1%) — formats vary
- Country of origin strips `Product of / Imported from / Made in / Bottled in`
  prefixes; case-insensitive (`Scotland` vs `SCOTLAND` vs `Product of Scotland`)
- Class/type: COLA umbrella codes (`beer`, `ale`, `table red wine`) match any
  printed-on-label sub-designation (Pilsner, IPA, Cabernet Sauvignon)
- Missing extracted on a non-warning field → `likely` (multi-image reality;
  field may be on another panel), not `flag`
- Flavored-malt / hard-seltzer class-type auto-detects added flavors → ABV
  becomes mandatory without callers having to remember the override
- Empty declared on a required field (COLA dataset gaps, e.g. bottler) →
  surface label content with `match` status and a transparent note

### Dataset preparation

`test/eval/build_dataset.py`:
- Pulls images that contain `GOVERNMENT WARNING` in the OCR_TEXT (warning panel)
- Drops keg COLAs (≥5 gallons) — labels often show a different keg size than
  the dataset's OCR_VOLUME captured (multi-size approvals confuse extraction
  scoring)
- Stratifies across 23 categories from `LLM_CATEGORY` and `CLASS_NAME`
- Emits 8 mutation rows that flip declared brand / net contents / ABV on
  copies of approved labels so the harness can score rejection-detection too

### Top remaining extraction misses (representative)

```
Net contents:   "1 pints"      vs  "630 ML 21.3 FL OZ 1 PINT 7.3 FL OZ"    (dataset OCR took the largest)
Net contents:   "403 mL"       vs  "12 FL. OZ."                            (dataset OCR mislabeled)
Brand name:     "Half Acre"    vs  "NEON FOOTHILLS"                        (product/fanciful is more prominent)
Brand name:     "Künstler Br." vs  "KÜNSTLER x ANIXI COLLABORATION"        (collaboration / co-branded)
Alcohol:        "57% Alc./Vol." vs "IA 5c, ME-VT 15¢"                      (model picked deposit codes)
```

Improvement avenues (not implemented in the prototype):
- **Multi-image upload**: send front + back as a set; engine picks the right
  panel per field. This is the single biggest unlock for extraction accuracy.
- **Engine: brand + product names**: pass both from the application data;
  either matches the label's prominent text.
- **Stronger extraction prompt**: more aggressive omission policy when text
  could be deposit codes / NOM IDs / barcode text.

These would push real-world auto-pass meaningfully higher but are outside the
prototype scope. The synthetic + rules-engine 100% gates remain the contract.
