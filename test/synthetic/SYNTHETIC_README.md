# TTB Label Verification — Manual Test Pack

Four synthetic label images plus the **application data to type into the form** and the **expected result**. These are deliberately built to exercise every path: a clean pass, a fuzzy near-match, a hard flag, the Government Warning format checks, and a missing warning.

> How to use: open a label image, upload it in the app, type the application data below into the form (or load it), and check the result against "Expected."

---

## Case 1 — OLD TOM DISTILLERY (spirits) → should fully PASS
**Upload:** `label_1_old_tom_spirits.png`

| Field | Value to enter |
|---|---|
| Brand name | `OLD TOM DISTILLERY` |
| Class/Type | `Kentucky Straight Bourbon Whiskey` |
| Alcohol content | `45% Alc./Vol. (90 Proof)` |
| Net contents | `750 mL` |
| Bottler name/address | `Old Tom Distillery, Frankfort, Kentucky` |
| Beverage type | Spirits |

**Expected:** every field **Match**; Government Warning **compliant** (verbatim, ALL-CAPS + bold) → **Auto-pass / Approve**.

---

## Case 2 — STONE'S THROW (wine) → near-match + flag
**Upload:** `label_2_stones_throw_wine.png` (the label prints "Stone's Throw" and "700 mL")

| Field | Value to enter |
|---|---|
| Brand name | `STONE'S THROW`  *(label is title-case "Stone's Throw")* |
| Class/Type | `California Red Table Wine` |
| Alcohol content | `13.5% Alc./Vol.` |
| Net contents | `750 mL`  *(label says 700 mL — deliberate mismatch)* |
| Bottler name/address | `Stone's Throw Cellars, Sonoma, California` |
| Beverage type | Wine |

**Expected:** Brand → **Likely match** (casing only, one-click confirm); Net contents → **Flag** (750 mL declared vs 700 mL on label); warning compliant → **Needs review**.

---

## Case 3 — NORTHWIND BREWING (beer) → Government Warning violations
**Upload:** `label_3_northwind_beer.png`

| Field | Value to enter |
|---|---|
| Brand name | `NORTHWIND BREWING` |
| Class/Type | `India Pale Ale` |
| Alcohol content | `6.8% Alc./Vol.`  *(optional for beer)* |
| Net contents | `12 FL OZ` |
| Bottler name/address | `Northwind Brewing Co., Bend, Oregon` |
| Beverage type | Beer |

**Expected:** fields match; **Government Warning flagged** on three counts — title case (not ALL-CAPS/bold), paraphrased wording ("Drinking" instead of "Consumption"), and sub-minimum font → **Needs review**.

---

## Case 4 — CEDAR & SAGE (gin) → missing warning
**Upload:** `label_4_cedar_sage_missing_warning.png` (no warning printed)

| Field | Value to enter |
|---|---|
| Brand name | `CEDAR & SAGE` |
| Class/Type | `Distilled Gin` |
| Alcohol content | `40% Alc./Vol. (80 Proof)` |
| Net contents | `750 mL` |
| Bottler name/address | `Cedar & Sage Spirits, Portland, Oregon` |
| Beverage type | Spirits |

**Expected:** fields match; **Government Warning NOT present** → **Needs review** (mandatory warning missing).

---

## Case 5 — VALLEY CREST (wine) → near-match (needs-confirm) + sulfites
**Upload:** `label_5_valley_crest_wine.png` (prints "Sonoma, CA" and "CONTAINS SULFITES")

| Field | Value to enter |
|---|---|
| Brand name | `VALLEY CREST` |
| Class/Type | `Sonoma County Chardonnay` |
| Alcohol content | `13.5% Alc./Vol.` |
| Net contents | `750 mL` |
| Bottler name/address | `Valley Crest Winery, Sonoma, California`  *(label abbreviates to "CA")* |
| Beverage type | Wine |

**Expected:** all Match **except** Bottler → **Likely match** (address abbreviation CA vs California) → **Needs confirm**. Warning compliant. Tests A2 / E1 / D4 — and demonstrates the amber/needs-confirm bucket.

---

## Case 6 — IRON ANCHOR (beer) → must NOT flag missing ABV
**Upload:** `label_6_iron_anchor_lager.png` (no alcohol statement printed)

| Field | Value to enter |
|---|---|
| Brand name | `IRON ANCHOR` |
| Class/Type | `Premium Lager Beer` |
| Alcohol content | *(leave blank)* |
| Net contents | `12 FL OZ` |
| Bottler name/address | `Iron Anchor Brewing Co., Milwaukee, Wisconsin` |
| Beverage type | Beer |

**Expected:** all Match; the app must **not** flag a missing alcohol statement (optional for malt beverages); warning compliant → **Auto-pass**. Tests A3.

---

## Case 7 — BRIGHT WAVE (hard seltzer / FMB) → ABV required, passes
**Upload:** `label_7_bright_wave_seltzer.png`

| Field | Value to enter |
|---|---|
| Brand name | `BRIGHT WAVE` |
| Class/Type | `Black Cherry Hard Seltzer` |
| Alcohol content | `5% Alc./Vol.` |
| Net contents | `12 FL OZ` |
| Bottler name/address | `Bright Wave Beverage Co., Austin, Texas` |
| Beverage type | Malt |

**Expected:** all Match; warning compliant → **Auto-pass**. Tests A4 (added-flavor malt beverage — ABV mandatory).

---

## Case 8 — GLEN ARDEN (imported Scotch) → country of origin
**Upload:** `label_8_glen_arden_scotch.png` (prints "PRODUCT OF SCOTLAND")

| Field | Value to enter |
|---|---|
| Brand name | `GLEN ARDEN` |
| Class/Type | `Blended Scotch Whisky` |
| Alcohol content | `40% Alc./Vol. (80 Proof)` |
| Net contents | `750 mL` |
| Bottler name/address | `Glen Arden Imports, New York, NY` |
| Country of origin | `Scotland` |
| Beverage type | Spirits |

**Expected:** all Match; warning compliant → **Auto-pass**. Tests B2 / E6 (import + country-of-origin statement).

---

## Case 9 — SUMMIT PEAK (rye) → brand mismatch flag
**Upload:** `label_9_summit_peak_rye.png` (label brand reads "SUMMIT PEAK")

| Field | Value to enter |
|---|---|
| Brand name | `SUMMIT RIDGE`  *(deliberately wrong — label says "SUMMIT PEAK")* |
| Class/Type | `Straight Rye Whiskey` |
| Alcohol content | `47% Alc./Vol. (94 Proof)` |
| Net contents | `750 mL` |
| Bottler name/address | `Summit Spirits, Denver, Colorado` |
| Beverage type | Spirits |

**Expected:** Brand → **Flag** (Summit Ridge vs Summit Peak); other fields Match; warning compliant → **Needs review**. Tests D6.

---

## Notes

These are clean synthetic artwork — ideal for verifying the extraction + the rules engine deterministically. For two extra real-world checks:

- **Imperfect image:** photograph one of these on your phone at a slight angle or with glare, then upload — that tests the image-quality gate and the model's robustness.
- **Real labels:** pull a few genuine approved labels from the **TTB Public COLA Registry** (ttbonline.gov → Public COLA Registry) — the detail page gives you both the label image and the declared application fields, so you get real ground-truth positives. Note: approved registry labels are compliant by definition, so they won't contain the deliberate violations in Cases 2–4 — that's exactly why those are synthetic.

**Verbatim Government Warning baseline (27 CFR 16.21):**
`GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.`
