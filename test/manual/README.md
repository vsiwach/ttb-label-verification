# Manual testing — ready-to-run demo scripts

Self-contained curl scripts that exercise every verdict bucket against the
local FastAPI backend. Use these to:

- Smoke-test the backend after changes
- Demo the system to stakeholders
- Verify all three verdict paths (`auto-pass` / `needs-confirm` / `needs-review`) end-to-end

## Prerequisites

Backend must be running locally on port 8000:

```bash
make serve-mock    # fastest path — deterministic fixtures, no API key, <100ms/request
# OR
make serve-cloud   # real Claude Vision (needs ANTHROPIC_API_KEY in backend/.env)
# OR
make serve-modal   # production Qwen LoRA on Modal (needs MODAL_ENDPOINT_URL)
```

Scripts default to `API=http://localhost:8000/api`. Override with
`API=https://your.deployed.host/api bash test/manual/...sh`.

## Single-label scripts (9, one per synthetic fixture)

Each script POSTs one image + the correct application data, prints the
typed `VerificationResult` as pretty JSON.

| Script | Expected verdict | What it exercises |
|---|---|---|
| `single_01_1_old_tom_spirits_auto_pass.sh` | **auto-pass** | Clean spirits label — all fields match, warning verbatim |
| `single_02_2_stones_throw_wine_needs_confirm.sh` | **needs-confirm** | 700 mL vs declared 750 mL — within 10% border tolerance → `likely` |
| `single_03_3_northwind_beer_needs_review.sh` | **needs-review** | Government Warning paraphrased + sub-minimum font |
| `single_04_4_cedar_sage_missing_warning_needs_review.sh` | **needs-review** | Mandatory Government Warning entirely absent |
| `single_05_5_valley_crest_wine_auto_pass.sh` | **auto-pass** | Wine with CONTAINS SULFITES — bottler address abbreviation OK |
| `single_06_6_iron_anchor_lager_auto_pass.sh` | **auto-pass** | Beer with no ABV on label and none declared (PRD: malt ABV is optional) |
| `single_07_7_bright_wave_seltzer_auto_pass.sh` | **auto-pass** | Hard seltzer — added-flavor detection auto-requires ABV |
| `single_08_8_glen_arden_scotch_auto_pass.sh` | **auto-pass** | Imported spirit with "PRODUCT OF SCOTLAND" |
| `single_09_9_summit_peak_rye_needs_review.sh` | **needs-review** | Brand mismatch: application says "SUMMIT RIDGE" but label says "SUMMIT PEAK" |

**Quick coverage check** (one per bucket):

```bash
bash test/manual/single_01_1_old_tom_spirits_auto_pass.sh                  # auto-pass
bash test/manual/single_02_2_stones_throw_wine_needs_confirm.sh            # needs-confirm
bash test/manual/single_04_4_cedar_sage_missing_warning_needs_review.sh    # needs-review
```

Or run them all:

```bash
for f in test/manual/single_*.sh; do
    bash "$f"
    echo
done
```

## Batch scripts (2)

| Script | What it does |
|---|---|
| `batch_one_of_each.sh` | Quick 3-image batch — sanity-check the fan-out path returns mixed verdicts |
| `batch_all_9.sh` | Full 9-image batch — stress the concurrent extractor + bounded semaphore |

Both pretty-print a per-item table with verdict bucket distribution at the bottom.

```bash
bash test/manual/batch_all_9.sh
```

**Note on batch verdict distribution**: the `/api/verify-batch` endpoint
accepts ONE shared `applicationData` for the whole batch. When omitted (as
in these scripts), the backend round-robins through the mock
`SAVED_APPLICATIONS` — so each image gets paired with a *different*
COLA than its "matching" one. This is intentional for stress-testing the
fan-out + per-item failure isolation. The per-image verdict precision is
exercised by the single-label scripts.

## Testing the frontend manually

The same images work in the React UI:

```bash
# In one terminal:
make serve-mock                                  # backend on :8000

# In another:
echo "VITE_API_BASE_URL=http://localhost:8000/api" > .env.local
npm run dev                                       # frontend on :5173
```

Then in the browser:

1. **`/upload`** — drag any `test/synthetic/label_*.png` into the dropzone, fill the form (or paste from `expected_results.json`), submit
2. **`/result`** — see the per-field cards, Government Warning panel, verdict badge, HITL decision panel
3. **`/batch`** — drag multiple PNGs at once; triage dashboard groups them by verdict
4. **`/review`** — keyboard-driven queue for the needs-review items

## Pointing the scripts at a remote deploy

All scripts honor `$API`. To test a Modal/Render/agency deploy:

```bash
API=https://api.example.com/api bash test/manual/batch_all_9.sh
```

## Adding new test cases

1. Drop a new label image into `test/synthetic/`
2. Add an entry to `test/synthetic/expected_results.json` with the correct
   `applicationData` and expected verdict
3. Regenerate the single-label scripts:
   ```bash
   # (the per-case script generator is in test/manual/ history; rerun
   # the snippet from the commit message of test/manual creation, OR
   # just write a new script copying the pattern of an existing one)
   ```

Or for a one-off test, copy `single_01_*.sh`, change the `IMG` and
`APP_DATA` variables, and run.
