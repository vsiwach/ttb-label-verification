# TTB Label Verification — Test Plan & Matrix

Goal: prove the system works on **real COLA applications and label images** across the full
variety of products, not just the happy path. Tests come in two tiers:

- **Automated fixtures (synthetic):** deterministic cases with known expected outcomes, wired
  into the backend's unit/integration tests. These cover the verdict logic and the deliberate
  violations no real (approved) label will contain.
- **Manual real-COLA cases:** genuine approved labels pulled from the TTB Public COLA Registry,
  used to confirm extraction + matching hold up on real artwork. Downloaded into `eval/data/` (see `EVALUATION.md`).

---

## How to pull real cases (Advanced Search) — validated against the live page

Advanced Search (`ttbonline.gov/colasonline/publicSearchColasAdvanced.do`) exposes exactly these
filters (confirmed from the page). Use them to source the categories below:

- **Date Completed** (from/to) — **required** for any non-ID search; range ≤ 15 years. `%` works as a wildcard in any non-date field.
- **Product Name** — radio for Brand Name / Fanciful Name / Either.
- **Product Class/Type** — multi-select list (Ctrl/Shift to multi-pick), with modes "Show Codes (with description)", "Show Descriptions (with code)", or "Enter Code Manually". Pull whole categories by **code**:
  - `81` Table White Wine · `82`-ish Table Red (browse) · `101` Straight Bourbon Whisky (the Jim Beam case) · `154` Unblended Scotch Whisky · `977`/`978` Tequila · `400`/`410`/`412` Rum (white/gold) · `86` Vermouth/Mixed · `604`/`654` Triple Sec. Browse the list for vodka, gin, beer/ale, sparkling, liqueur, sake, cider codes.
- **Origin Code** — multi-select. Distinguishes **domestic** (states; `00` American, plus per-state codes) from **imports** (countries; e.g., Argentina `62`, Algeria `61`). Use this to stratify domestic vs import and to find **foreign-language** labels.
- **Received Code** — `001` Electronic Submission vs `000` Front Desk / `002` Mail / `003` Overnight (all paper). **Electronic = clean digital images; paper = scanned (lower-res, skew, artifacts).** Use paper codes to source hard image-quality cases (see §F).
- **Status** — approved / expired / surrendered / revoked (per the page header).
- **TTB ID** (range), **Serial #** (range), **Plant Registry/Permit** (data after 04/26/2003).

Tip: a date range + a Class/Type code (or a brand name) is the fastest way to get a clean spread.
Each result's detail page gives you the label image(s) **and** the application fields. Remember the
Jim Beam finding: the form carries brand/class-type/bottler but **not ABV or net contents** — read
those off the label image.

---

## A. Core matrix — beverage type × mandatory fields

The single most important coverage: each beverage type has a different mandatory-field set.

| ID | Beverage type | Must verify | Key rule under test | Source | Expected |
|---|---|---|---|---|---|
| A1 | Distilled spirits | brand, class/type, **ABV (mandatory)**, net contents, bottler, gov warning | ABV required for spirits | Real (e.g., Jim Beam) + synthetic | Auto-pass |
| A2 | Wine ≥7% | brand, class/type, **ABV**, net contents, bottler, gov warning, sulfites if applicable | ABV required; sulfite declaration | Real table wine | Auto-pass |
| A3 | Malt beverage / beer | brand, class/type, net contents, bottler, gov warning — **ABV optional** | App must NOT flag missing ABV on plain beer | Real beer | Auto-pass (no ABV flag) |
| A4 | Flavored malt beverage / hard seltzer | as A3 **but ABV becomes mandatory** (added nonbeverage flavors) | conditional ABV requirement | Real (e.g., White Claw / Truly) | ABV expected; flag if absent |
| A5 | Low-ABV (0.5–7%) wine / product | gov warning still required ≥0.5% ABV | warning required below FAA 7% wine threshold | Synthetic | Warning enforced |
| A6 | Non-alcoholic (<0.5%) | gov warning NOT required | warning correctly not demanded | Synthetic | No warning flag |

## B. Product-category coverage (real samples to pull)

Pull one real approved COLA for each to stress extraction across label designs. Search by brand
or class/type in Advanced Search.

| ID | Category | Example search term | What it stresses |
|---|---|---|---|
| B1 | Bourbon / whiskey | "Jim Beam", "Maker's Mark" | proof + ABV dual statement, age/straight designation |
| B2 | Scotch (import) | "Macallan", "Glenfiddich" | country of origin, "Product of Scotland", age statement |
| B3 | Vodka | "Tito's", "Grey Goose" | minimal label text, large brand, flavored variants |
| B4 | Gin | "Tanqueray", "Hendrick's" | "Distilled Gin" class/type |
| B5 | Rum (import) | "Bacardi" | origin, "Product of Puerto Rico" |
| B6 | Tequila (import) | "Patrón", "Jose Cuervo" | origin = Mexico, NOM, agave designation |
| B7 | Brandy / Cognac (import) | "Hennessy" | origin = France, foreign text |
| B8 | Liqueur / cordial | "Baileys", "Kahlúa" | aspartame/allergen disclosures, dairy |
| B9 | Table wine (red/white) | "Barefoot", "Kendall-Jackson" | sulfite declaration, varietal/appellation/vintage |
| B10 | Sparkling / Champagne | "Korbel", "Veuve Clicquot" (import) | "Méthode Champenoise", origin = France |
| B11 | Fortified / dessert wine | "Port", "Sherry" | higher ABV, semi-generic names |
| B12 | Import wine (FR/IT) | "Yellow Tail" (AU), a Chianti | foreign-language text, translations (item 15) |
| B13 | Beer / IPA / lager | "Sierra Nevada", "Budweiser" | ABV optional, standard of fill (12 FL OZ) |
| B14 | Flavored malt / seltzer | "White Claw", "Truly" | ABV mandatory, fruit-flavor statements |
| B15 | Cider | "Angry Orchard" | wine vs malt classification edge |
| B16 | Sake / rice wine (import) | a sake brand | origin = Japan, non-Latin script |

## C. Government Warning checks (the marquee)

| ID | Case | Source | Expected |
|---|---|---|---|
| C1 | Compliant warning, verbatim, ALL-CAPS + bold | Real (approved) + synthetic `label_1` | Compliant |
| C2 | Warning on the **back label** (front has none) | Real (Jim Beam back) | Compliant when back uploaded; "not present" if only front — see §F multi-image |
| C3 | "Government Warning" in **title case** (not caps/bold) | Synthetic `label_3` | Flag — casing |
| C4 | **Paraphrased / reworded** ("Drinking" vs "Consumption") | Synthetic `label_3` | Flag — wording (non-verbatim) |
| C5 | **Missing** warning entirely | Synthetic `label_4` | Flag — not present |
| C6 | **Sub-minimum font** for container size | Synthetic `label_3` | Flag — font size (or Amber/confirm if unmeasurable) |
| C7 | **Low contrast** / camouflaged text | Synthetic | Flag — contrast (or Amber) |
| C8 | Not **separate and apart** (crowded into other copy) | Synthetic | Flag — separation (or Amber) |
| C9 | Abbreviated / truncated warning | Synthetic | Flag — wording |

## D. Field matching / fuzzy logic (3-state behavior)

| ID | Case | Example | Expected status |
|---|---|---|---|
| D1 | Exact match | "OLD TOM DISTILLERY" = "OLD TOM DISTILLERY" | Match (green) |
| D2 | Casing difference | app "STONE'S THROW" vs label "Stone's Throw" | Likely (amber) |
| D3 | Punctuation/spacing | "12 FL OZ" vs "12 FL. OZ." | Likely (amber) |
| D4 | Address abbreviation | "Kentucky" vs "KY", "Street" vs "St." | Likely (amber) |
| D5 | Net contents mismatch | app "750 mL" vs label "700 mL" | Flag (red) |
| D6 | Brand mismatch | wrong brand on label | Flag (red) |
| D7 | ABV mismatch | app "45%" vs label "40%" | Flag (red) |
| D8 | Class/type entered in brand field | common applicant error | Flag (red) |
| D9 | Equivalent units | "750 mL" vs "75 cL" | Likely/Match (define behavior) |
| D10 | Extra/missing whitespace, OCR noise | "JIM  BEAM" / line breaks | Match after normalization |

## E. Conditional / disclosure fields

| ID | Case | Beverage | Expected |
|---|---|---|---|
| E1 | Sulfite declaration "CONTAINS SULFITES" | wine | present/verified where applicable |
| E2 | Aspartame "PHENYLKETONURICS: CONTAINS PHENYLALANINE" | any with aspartame | verbatim, caps |
| E3 | FD&C Yellow No. 5 disclosure | any | present where colorant used |
| E4 | Commodity / neutral-spirits statement | spirits | present where required |
| E5 | Grape varietal / appellation / vintage | wine | extracted, not mismatched |
| E6 | Country of origin statement | imports | present + matches origin code |
| E7 | NOT-yet-final rules (allergen / Alcohol Facts / cancer) | any | informational only — must NOT reject |

## F. Image quality & multi-image (real-world artwork)

| ID | Case | Source | Expected |
|---|---|---|---|
| F1 | Clean high-res scan | Real COLA image | High quality score; clean extraction |
| F2 | Phone photo at an angle | Photograph a synthetic label | Reads or routes to "request better image" |
| F3 | Glare / reflection | Photograph with glare | Quality flagged if unreadable |
| F4 | Low light / blur | Blurred capture | Low quality score → request better image |
| F5 | Low resolution | Downscaled image | Graceful degradation |
| F6 | Rotated 90°/180° | Rotated file | Reads or flags orientation |
| F7 | **Multi-image set** (front + back + neck) | Real COLA (Jim Beam) | Each image verifies its own fields; warning on back |
| F8 | Keg collar / distinctive bottle / odd aspect | Real COLA | Handles non-standard layout |
| F9 | Embossed/blown info not on label (item 15) | Real COLA | Doesn't false-flag missing on-label info |
| F10 | **Paper-scanned vs electronic** submission | Real COLA — Received Code `002`/`003` (paper) vs `001` (electronic) | Scanned/skewed paper images still read, or route to "request better image"; electronic should be clean |

## G. Record / document edge cases

| ID | Case | Source | Expected |
|---|---|---|---|
| G1 | Approved status | Real | normal path |
| G2 | Expired / surrendered / revoked status | Real (Advanced Search → Status) | handled (informational; still verify label) |
| G3 | Certificate of **Exemption** (not a COLA) | Real | recognized as exemption, not full COLA |
| G4 | **Distinctive Liquor Bottle** approval | Real | bottle-shape case, label rules still apply |
| G5 | Resubmission after rejection | Real | normal |
| G6 | **Data-only** record (pre-1999, no image) | Real | graceful "no image to verify" message |
| G7 | Multiple plant registries / DBA "used on label" | Real (Jim Beam: James B. Beam Distilling Co.) | bottler name matches the on-label DBA |
| G8 | COLA form lacks ABV & net contents | Real (all) | app handles "declared value unavailable" — read from label, don't false-flag |

## H. Batch

| ID | Case | Expected |
|---|---|---|
| H1 | Large batch (200–300 images) | completes < ~1 min; progressive fill |
| H2 | Mixed outcomes | correct auto-pass / needs-confirm / needs-review grouping |
| H3 | One corrupt/unreadable item in batch | that item errors; batch still completes |
| H4 | Duplicate images | both processed (or flagged as dup if implemented) |
| H5 | Multi-image products in a batch | front/back grouped or handled per image |

## I. Negative / robustness / security

| ID | Case | Expected |
|---|---|---|
| I1 | Non-label image (random photo) | low confidence / "not a label" — no fabricated fields |
| I2 | Corrupt / truncated file | plain-language error, no crash |
| I3 | Unsupported type (TIFF/HEIC/PDF) | clear message or conversion path |
| I4 | Very large file (e.g., 20 MB) | downscaled or rejected gracefully |
| I5 | Blank / white image | "no label detected" |
| I6 | Non-alcohol product label | no false COLA verdict |
| I7 | Same image twice with different application data | verdicts differ correctly (no caching bug) |

## J. Real "must auto-pass" regression set (false-positive guard)

Pull ~12 genuinely **approved** COLAs spanning the categories in §B (a bourbon, a scotch, a vodka,
a table wine, a sparkling, an IPA, a seltzer, an import tequila, an import wine, a liqueur, a cider,
a sake). Every one should return **all fields Match + warning compliant → Auto-pass**. Any flag here
is a false positive worth investigating (extraction miss or over-strict rule). This is the most
important real-world guardrail: it proves the tool doesn't reject legitimate labels.

---

## Coverage: automated vs manual

- **Automated (backend unit/integration tests):** A1, A3–A6, C1, C3–C9, D1–D10, E2, E7, H2–H3, I1–I7 — all have deterministic expected outcomes; use the `synthetic/` fixtures + small constructed inputs.
- **Manual / real COLA (downloaded to `eval/data/`):** A2, B1–B16, C1–C2, E1/E3–E6, F1/F7–F9, G1–G8, J — require genuine artwork; scored by the harness against the dataset's fields (and an optional `expected_outcome` column).
- **Photograph-to-test:** F2–F6 — take phone photos of the synthetic labels.

Minimum bar before calling it done: all automated tests green, the §J regression set all auto-pass,
and §C3–C6 (the warning violations) all correctly flagged.
