#!/usr/bin/env bash
# Morning orchestrator — runs after `modal token new` has been done.
# Resumable via .pipeline_state/<step>.done markers.

set -uo pipefail

REPO=/Users/vikramsiwach/Downloads/ttb-label-verification
cd "$REPO"

STATE=.pipeline_state
mkdir -p "$STATE"
LOG="$STATE/morning.log"
exec >>"$LOG" 2>&1

VENV=backend/.venv
PY=$VENV/bin/python
MODAL=$VENV/bin/modal

ts() { date "+%Y-%m-%d %H:%M:%S"; }
banner() { echo; echo "=========================================="; echo "[$(ts)] $1"; echo "=========================================="; }
mark()   { touch "$STATE/$1.done"; }
done_q() { test -f "$STATE/$1.done"; }
fail()   { banner "FAILED at step: $1"; echo "$2"; touch "$STATE/FAILED"; exit 1; }

banner "Morning pipeline starting"

# ── Sanity: Modal auth ────────────────────────────────────────────────
if ! done_q "10_modal_auth_check"; then
    banner "Step 10: verify Modal auth"
    if ! $MODAL token current >/dev/null 2>&1; then
        fail "10_modal_auth_check" "Modal not authenticated. Run: $MODAL token new"
    fi
    $MODAL token current 2>&1 | head -3
    mark "10_modal_auth_check"
fi

# ── 11. Upload training data to Modal volume ─────────────────────────
if ! done_q "11_modal_upload"; then
    banner "Step 11: upload JSONL + composites to Modal volume (~30-45 min)"
    $MODAL volume create ttb-qwen-train-data 2>/dev/null || true
    $MODAL volume put --force ttb-qwen-train-data test/eval/data/qwen_sft/train.jsonl /train.jsonl  || fail "11_modal_upload" "train.jsonl upload failed"
    $MODAL volume put --force ttb-qwen-train-data test/eval/data/qwen_sft/val.jsonl   /val.jsonl    || fail "11_modal_upload" "val.jsonl upload failed"
    $MODAL volume put --force ttb-qwen-train-data test/eval/data/ttb_live/images       /images       || fail "11_modal_upload" "images upload failed"
    mark "11_modal_upload"
fi

# ── 12. Kick off training (~17 hr on A100-40GB) ──────────────────────
if ! done_q "12_modal_train"; then
    banner "Step 12: Modal A100 training (TRAIN_EPOCHS=1)"
    # `modal run` blocks until remote completes; safe to leave running.
    $MODAL run backend/modal_deploy/train_qwen.py --epochs 1 || fail "12_modal_train" "modal run train_qwen exited non-zero"
    mark "12_modal_train"
fi

# ── 13. Download v2 adapter back to Mac ──────────────────────────────
if ! done_q "13_adapter_download"; then
    banner "Step 13: download v2 adapter"
    mkdir -p backend/models/qwen2_5_vl_7b_v2
    $MODAL volume get ttb-qwen-adapter-v2 /adapter backend/models/qwen2_5_vl_7b_v2/adapter || fail "13_adapter_download" "adapter download failed"
    mark "13_adapter_download"
fi

# ── 14. Deploy v2 to its own Modal endpoint ──────────────────────────
if ! done_q "14_deploy_v2"; then
    banner "Step 14: deploy serve_qwen_v2.py"
    $MODAL deploy backend/modal_deploy/serve_qwen_v2.py 2>&1 | tee "$STATE/deploy_v2.out" || fail "14_deploy_v2" "v2 deploy failed"
    # Capture the v2 endpoint URL — the deploy output prints it
    V2_URL=$(grep -oE "https://[a-z0-9-]+--ttb-qwen-extractor-v2-extract-web[^ ]*" "$STATE/deploy_v2.out" | head -1)
    if [ -z "$V2_URL" ]; then
        fail "14_deploy_v2" "couldn't parse v2 endpoint URL from deploy output"
    fi
    echo "v2 endpoint: $V2_URL"
    echo "$V2_URL" > "$STATE/v2_endpoint_url.txt"
    mark "14_deploy_v2"
fi

# ── 15. Also deploy v1 serve so we have a clean endpoint ────────────
if ! done_q "15_deploy_v1"; then
    banner "Step 15: deploy serve_qwen.py (v1, for fair eval)"
    $MODAL deploy backend/modal_deploy/serve_qwen.py 2>&1 | tee "$STATE/deploy_v1.out" || fail "15_deploy_v1" "v1 deploy failed"
    V1_URL=$(grep -oE "https://[a-z0-9-]+--ttb-qwen-extractor-extract-web[^ ]*" "$STATE/deploy_v1.out" | head -1)
    if [ -z "$V1_URL" ]; then
        fail "15_deploy_v1" "couldn't parse v1 endpoint URL"
    fi
    echo "v1 endpoint: $V1_URL"
    echo "$V1_URL" > "$STATE/v1_endpoint_url.txt"
    mark "15_deploy_v1"
fi

V1_URL=$(cat "$STATE/v1_endpoint_url.txt")
V2_URL=$(cat "$STATE/v2_endpoint_url.txt")

# ── Helper: start backend with a given inference mode, run eval, kill ─
run_eval() {
    local TAG="$1"; local MODE="$2"; local URL="$3"
    if done_q "16_eval_$TAG"; then return; fi
    banner "Eval pass: TAG=$TAG  MODE=$MODE  URL=${URL:-none}"
    # Kill any stray backend
    pkill -f "uvicorn app.main" 2>/dev/null; sleep 2
    (
        cd backend
        set -a; . ./.env 2>/dev/null; set +a
        INFERENCE_MODE="$MODE" MODAL_ENDPOINT_URL="$URL" \
        ../$VENV/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
            >"../$STATE/backend_$TAG.log" 2>&1 &
        echo $! > "../$STATE/backend_$TAG.pid"
    )
    sleep 8  # let uvicorn bind
    if ! curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1; then
        cat "$STATE/backend_$TAG.log" | tail -30
        fail "16_eval_$TAG" "backend didn't come up for $TAG"
    fi
    $PY test/eval/eval_holdout.py --report-tag "$TAG" || fail "16_eval_$TAG" "eval_holdout failed for $TAG"
    BPID=$(cat "$STATE/backend_$TAG.pid")
    kill "$BPID" 2>/dev/null; sleep 2; kill -9 "$BPID" 2>/dev/null
    mark "16_eval_$TAG"
}

# ── 16. Eval all three models ────────────────────────────────────────
run_eval "haiku"   "cloud"  ""
run_eval "qwen_v1" "modal"  "$V1_URL"
run_eval "qwen_v2" "modal"  "$V2_URL"

# ── 17. Aggregate comparison ─────────────────────────────────────────
if ! done_q "17_compare"; then
    banner "Step 17: aggregate head-to-head"
    $PY test/eval/compare_holdout_models.py || fail "17_compare" "compare exited non-zero"
    mark "17_compare"
fi

banner "PIPELINE COMPLETE"
echo "Decision in test/eval/data/holdout_eval/COMPARISON.md:"
echo "-----------------------------------------------------"
cat test/eval/data/holdout_eval/COMPARISON.md
