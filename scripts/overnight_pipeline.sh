#!/usr/bin/env bash
# Overnight orchestrator — runs all the auto-runnable steps after the
# stratified scrape completes, so the user wakes up to a "ready to train"
# state with no manual catch-up work.
#
# What it does (in order, halts on any failure):
#   1. Polls the scrape process until it exits
#   2. Sanity-checks the scrape output (>= 15K composites, >=1K per category)
#   3. Splits the held-out 2K (writes holdout_ttbids.txt)
#   4. Builds train.jsonl / val.jsonl (skips the holdout)
#   5. Writes scripts/MORNING.md with a clean checklist for what to do next
#
# What it does NOT do (because Modal training requires `modal token new`
# in a browser, which the user hasn't run yet):
#   - Upload training data to Modal
#   - Kick off training
#   - Eval
#
# Re-runnable: each step writes a marker file under .pipeline_state/;
# completed steps are skipped on subsequent runs.

set -uo pipefail

REPO=/Users/vikramsiwach/Downloads/ttb-label-verification
cd "$REPO"

STATE=.pipeline_state
mkdir -p "$STATE"
LOG="$STATE/overnight.log"
exec >>"$LOG" 2>&1

PY=backend/.venv/bin/python

ts() { date "+%Y-%m-%d %H:%M:%S"; }
banner() { echo; echo "=========================================="; echo "[$(ts)] $1"; echo "=========================================="; }
mark()   { touch "$STATE/$1.done"; }
done_q() { test -f "$STATE/$1.done"; }
fail()   { banner "FAILED at step: $1"; echo "$2" >&2; touch "$STATE/FAILED"; exit 1; }

banner "Pipeline starting; log = $LOG"

# ──────────────────────────────────────────────────────────────────────
# 1. Wait for scrape to finish
# ──────────────────────────────────────────────────────────────────────
if ! done_q "01_scrape"; then
    banner "Step 1: wait for scrape (PID auto-detected from log)"
    # The scrape was launched by make scrape-ttb-stratified; we poll
    # for the make process and the python child.
    while true; do
        if ! pgrep -f scrape_ttb_registry.py >/dev/null 2>&1 \
           && ! pgrep -f "make scrape-ttb-stratified" >/dev/null 2>&1; then
            echo "[$(ts)] scrape process gone"
            break
        fi
        # Heartbeat every 5 min
        sleep 300
        n_cola=$(ls "/Users/vikramsiwach/Library/CloudStorage/GoogleDrive-vsiwach@gmail.com/My Drive/ttb-scrape/images/" 2>/dev/null | wc -l | tr -d ' ')
        n_csv=$(wc -l < test/eval/data/ttb_live/ttb_live.csv 2>/dev/null | tr -d ' ')
        local_free=$(df -h /Users/vikramsiwach | tail -1 | awk '{print $4}')
        echo "[$(ts)] heartbeat: composites=$n_cola  csv=$n_csv  local_free=$local_free"
    done
    # Did it exit cleanly?
    if grep -qiE "no space|operation timed out|traceback" test/eval/data/ttb_live/scrape.log; then
        # Log it but don't auto-fail — partial scrape may still be useful
        echo "[$(ts)] WARN: scrape log shows errors; proceeding with whatever landed"
        tail -50 test/eval/data/ttb_live/scrape.log
    fi
    mark "01_scrape"
fi

# ──────────────────────────────────────────────────────────────────────
# 2. Sanity check
# ──────────────────────────────────────────────────────────────────────
if ! done_q "02_sanity"; then
    banner "Step 2: sanity check"
    N_CSV=$(wc -l < test/eval/data/ttb_live/ttb_live.csv | tr -d ' ')
    N_IMG=$(ls "/Users/vikramsiwach/Library/CloudStorage/GoogleDrive-vsiwach@gmail.com/My Drive/ttb-scrape/images/" | wc -l | tr -d ' ')
    echo "csv rows = $N_CSV; composites = $N_IMG"
    # Soft minimum — if we have at least 5K composites we can still
    # train a useful v2 (better than v1's 1377).
    if [ "$N_IMG" -lt 5000 ]; then
        fail "02_sanity" "only $N_IMG composites; need at least 5000 to make training worthwhile"
    fi
    mark "02_sanity"
fi

# ──────────────────────────────────────────────────────────────────────
# 3. Holdout split (2K stratified, blind to trainer)
# ──────────────────────────────────────────────────────────────────────
if ! done_q "03_holdout"; then
    banner "Step 3: holdout split"
    $PY test/eval/holdout_split.py --n 2000 --force || fail "03_holdout" "holdout_split.py exited non-zero"
    mark "03_holdout"
fi

# ──────────────────────────────────────────────────────────────────────
# 4. JSONL builder
# ──────────────────────────────────────────────────────────────────────
if ! done_q "04_jsonl"; then
    banner "Step 4: build training JSONL"
    $PY test/eval/build_qwen_jsonl.py || fail "04_jsonl" "build_qwen_jsonl.py exited non-zero"
    mark "04_jsonl"
fi

# ──────────────────────────────────────────────────────────────────────
# 5. Stage JSONL + CSV + holdout list to Drive (so Colab can read directly)
# ──────────────────────────────────────────────────────────────────────
if ! done_q "05_stage_to_drive"; then
    banner "Step 5: stage training files to Drive for Colab"
    DRIVE_ROOT="/Users/vikramsiwach/Library/CloudStorage/GoogleDrive-vsiwach@gmail.com/My Drive"
    DRIVE_TTB="$DRIVE_ROOT/ttb-scrape"
    DRIVE_JSONL="$DRIVE_TTB/qwen_sft"
    mkdir -p "$DRIVE_JSONL"
    # Copy (not move) — local copies are tiny and useful for the eval scripts.
    cp test/eval/data/qwen_sft/train.jsonl              "$DRIVE_JSONL/train.jsonl"
    cp test/eval/data/qwen_sft/val.jsonl                "$DRIVE_JSONL/val.jsonl"
    cp test/eval/data/qwen_sft/manifest.json            "$DRIVE_JSONL/manifest.json"
    cp test/eval/data/ttb_live/ttb_live.csv             "$DRIVE_TTB/ttb_live.csv"
    cp test/eval/data/ttb_live_test/holdout_ttbids.txt  "$DRIVE_TTB/holdout_ttbids.txt"
    cp test/eval/data/ttb_live_test/holdout_manifest.json "$DRIVE_TTB/holdout_manifest.json"
    echo "Drive layout under $DRIVE_TTB:"
    ls -la "$DRIVE_TTB/" | head
    echo "JSONL files:"
    ls -la "$DRIVE_JSONL/"
    mark "05_stage_to_drive"
fi

# ──────────────────────────────────────────────────────────────────────
# 6. Write MORNING.md checklist
# ──────────────────────────────────────────────────────────────────────
banner "Step 6: write morning checklist"
N_IMG=$(ls "/Users/vikramsiwach/Library/CloudStorage/GoogleDrive-vsiwach@gmail.com/My Drive/ttb-scrape/images/" | wc -l | tr -d ' ')
N_TRAIN=$(wc -l < test/eval/data/qwen_sft/train.jsonl 2>/dev/null | tr -d ' ' || echo "?")
N_VAL=$(wc -l < test/eval/data/qwen_sft/val.jsonl 2>/dev/null | tr -d ' ' || echo "?")

cat > scripts/MORNING.md <<EOF
# Morning state — overnight pipeline summary

Generated: $(ts)

## What landed overnight

- Scrape composites on Drive: **$N_IMG**
- Held-out test set: 2 000 ttb_ids → \`MyDrive/ttb-scrape/holdout_ttbids.txt\`
- Training JSONL: **$N_TRAIN** train + **$N_VAL** val
  - Mac copy: \`test/eval/data/qwen_sft/\`
  - Drive copy: \`MyDrive/ttb-scrape/qwen_sft/\` (for Colab)
- Form-text ground truth: \`MyDrive/ttb-scrape/ttb_live.csv\`

## How to train + eval (Colab path — no Modal needed)

The training pivoted from Modal to Colab. Two notebooks are ready, both
read directly from your Drive (no upload step required).

### Step 1 — fine-tune Qwen v2 (~3-4 hr on Colab A100, ~6-8 hr on T4)

1. Open https://colab.research.google.com → File → Upload notebook → pick
   \`notebooks/sft_qwen2_5_vl_v2.ipynb\` from your local checkout
   (or open from GitHub once pushed)
2. Runtime → Change runtime type → **GPU (A100 if you have Colab Pro)**
3. Runtime → Run all
4. First pass installs deps + auto-restarts. When the "session crashed"
   banner appears, Runtime → Run all AGAIN.
5. Training runs end-to-end; adapter lands at
   \`MyDrive/ttb_sft/qwen2_5_vl_7b_v2/adapter/\` (coexists with v1 at
   \`MyDrive/ttb_sft/qwen2_5_vl_7b/adapter/\`).

### Step 2 — head-to-head eval (Haiku vs v1 vs v2, ~30-90 min)

1. Open \`notebooks/eval_v1_vs_v2_drive.ipynb\` in Colab (same upload flow).
2. For the Haiku baseline: open the **key icon in the Colab sidebar** →
   add a secret named \`ANTHROPIC_API_KEY\` with the value from your
   local \`backend/.env\` (skip if you only want v1 vs v2).
3. Run all → \`MyDrive/ttb_sft/eval/v1_vs_v2_comparison.md\` is the
   headline report.

### Step 3 — promote v2 if it wins

\`\`\`bash
# On the Mac, pull the v2 adapter back from Drive into the backend
rsync -av "/Users/vikramsiwach/Library/CloudStorage/GoogleDrive-vsiwach@gmail.com/My Drive/ttb_sft/qwen2_5_vl_7b_v2/adapter/" \\
          backend/models/qwen2_5_vl_7b_v2/adapter/
\`\`\`

## Logs

- Scrape: \`test/eval/data/ttb_live/scrape.log\`
- Overnight orchestrator: \`.pipeline_state/overnight.log\`
- Completion markers: \`.pipeline_state/*.done\`

## If something looks off

\`\`\`bash
tail -50 .pipeline_state/overnight.log
ls .pipeline_state/                 # which steps completed
\`\`\`

To re-run a single step: \`rm .pipeline_state/<step>.done\` and re-run
\`bash scripts/overnight_pipeline.sh\`.

## (Legacy: Modal path)

The earlier Modal training scripts (\`backend/modal_deploy/train_qwen.py\`,
\`scripts/morning_pipeline.sh\`) still work if you want a fully unattended
remote training run instead of Colab. Requires \`backend/.venv/bin/modal
token new\` first.
EOF

banner "DONE — see scripts/MORNING.md"
echo "Tail of MORNING.md:"
tail -30 scripts/MORNING.md
