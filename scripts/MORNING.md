# Morning state — scrape complete, ready for Colab training

Generated: 2026-05-25 10:35

## What landed overnight

| Item | Count | Where |
|---|---|---|
| Scrape composites | **11,439** | `MyDrive/ttb-scrape/images/` |
| Held-out test set | **2,000** ttb_ids | `MyDrive/ttb-scrape/holdout_ttbids.txt` |
| Training set | **8,968** examples | `MyDrive/ttb-scrape/qwen_sft/train.jsonl` |
| Validation set | **471** examples | `MyDrive/ttb-scrape/qwen_sft/val.jsonl` |
| Form ground truth | 20,306 rows | `MyDrive/ttb-scrape/ttb_live.csv` |

### Beverage mix in training set

```
wine     4607  (51.4%)
spirits  3097  (34.5%)
malt     1264  (14.1%)
```

⚠️ Beer-malt is **underrepresented** vs the 30% target. Root cause: TTB's
public registry has no panel images for ~80% of beer/malt COLAs we
scraped (yields ~20% usable composites in that bucket vs ~89% for
spirits and wine). Not a scraper bug — TTB source-data sparsity for
beer/malt. v2 will still learn beer/malt conventions, just expect lower
per-bucket accuracy on malt at eval time.

## Step 1 — Fine-tune Qwen v2 in Colab (~12-14 hr on Pro+ A100-80GB)

1. Open https://colab.research.google.com → **File → Upload notebook**
   → pick `notebooks/sft_qwen2_5_vl_v2.ipynb` from your local checkout
2. **Runtime → Change runtime type → A100 GPU** (Pro+ gets 80GB)
3. **Runtime → Manage sessions → Background execution: ON** (so you can
   close the tab without losing the run; up to 24 hr cap)
4. **Runtime → Run all**
5. First pass installs deps and auto-restarts the kernel. When the
   "session crashed" banner appears, **Runtime → Run all AGAIN.**
6. Training proceeds end-to-end. Checkpoints to Drive every 500 steps
   (~30 min). If Colab disconnects, re-run the training cell —
   `Trainer` auto-resumes from latest checkpoint.
7. Adapter lands at `MyDrive/ttb_sft/qwen2_5_vl_7b_v2/adapter/`
   (coexists with v1 at `MyDrive/ttb_sft/qwen2_5_vl_7b/adapter/`).

The notebook has a runtime **leakage assertion** at the top of the data-
loading section that hard-stops if any train/val ttb_id appears in the
holdout — last line of defense against contaminated eval.

## Step 2 — Head-to-head eval (Haiku vs v1 vs v2, ~30-90 min)

1. (Optional) Stash Anthropic API key as a Colab secret: key icon in
   left sidebar → New secret → `ANTHROPIC_API_KEY` → paste value from
   `backend/.env` → toggle "Notebook access" on. Skip if you only want
   v1 vs v2.
2. Open `notebooks/eval_v1_vs_v2_drive.ipynb` in Colab (same upload flow
   as the training notebook).
3. Same runtime config (A100, Background execution).
4. **Runtime → Run all** → twice (first pass installs + restarts).
5. Output: `MyDrive/ttb_sft/eval/v1_vs_v2_comparison.md` is the
   head-to-head report with per-field accuracy, bucket agreement
   (full engine + fields-only variants), and a ship/hold recommendation.

## Step 3 — Promote v2 to backend (if it wins)

```bash
# Pull v2 adapter from Drive into the backend models dir
rsync -av \
  "/Users/vikramsiwach/Library/CloudStorage/GoogleDrive-vsiwach@gmail.com/My Drive/ttb_sft/qwen2_5_vl_7b_v2/adapter/" \
  backend/models/qwen2_5_vl_7b_v2/adapter/
```

## Drive quota housekeeping

You already emptied Trash once during the scrape — nice. After the
beer-malt phase finished, ~6 GB more was trashed (per-COLA panel
staging from the run that started before the trash-fix commit landed).
Empty Drive Trash once more for a clean baseline. Future scrapes use
local `/tmp` staging (committed in `8c40624`) and won't generate Drive
trash at all.

## Logs + resumption

```
test/eval/data/ttb_live/scrape.log       full scrape transcript
.pipeline_state/overnight.log            orchestrator log
.pipeline_state/*.done                   step completion markers
```

To re-run a step: `rm .pipeline_state/<step>.done && bash scripts/overnight_pipeline.sh`

## Legacy Modal path

If you ever want to skip Colab for a fully unattended remote training run:
- `backend/.venv/bin/modal token new` (one-time browser click)
- `bash scripts/morning_pipeline.sh` (drives the Modal path end-to-end)
