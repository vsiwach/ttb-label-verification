# TTB Label Verification — top-level convenience commands.
# All commands assume the backend venv is at backend/.venv.

VENV     := backend/.venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
UVICORN  := $(VENV)/bin/uvicorn
PYTEST   := $(VENV)/bin/pytest

API      ?= http://localhost:8000/api
PORT     ?= 8000

.PHONY: help install install-sft test test-synth \
        serve serve-api serve-modal \
        modal-deploy modal-upload-adapter \
        demo-single demo-batch demo-all \
        audit-reals uat-pack scrape-ttb \
        clean

help:
	@echo "Targets:"
	@echo ""
	@echo "  --- Run locally (Claude Code CLI — uses your Max subscription) ---"
	@echo "  install         Create backend venv and install Python deps"
	@echo "  serve           Run backend in claude-code mode (no API token spend; needs 'claude' CLI logged in)"
	@echo "  serve-api       Run backend in cloud mode using ANTHROPIC_API_KEY (pay-per-token)"
	@echo "  test            Run the full pytest suite (115 tests, ~3 seconds)"
	@echo ""
	@echo "  --- Deploy to Modal (Qwen LoRA, scale-to-zero GPU) ---"
	@echo "  modal-upload-adapter   Upload the trained LoRA adapter to Modal's persistent volume"
	@echo "  modal-deploy           Deploy the Qwen extractor to Modal; prints the endpoint URL"
	@echo "  serve-modal            Run backend locally routing inference to the deployed Modal endpoint"
	@echo ""
	@echo "  --- Demo scripts (require backend already running) ---"
	@echo "  demo-single     3 single-label demos covering all three verdict buckets"
	@echo "  demo-batch      9-image batch demo"
	@echo "  demo-all        Every single + the batch in one sweep"
	@echo ""
	@echo "  clean           Remove caches"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

# Heavy ML deps for local sft mode (~3 GB). Not needed when using Modal.
install-sft:
	$(PIP) install -r backend/requirements-sft.txt

test:
	cd backend && ../$(PY) -m pytest

# Local default: claude-code CLI mode (uses your Max subscription, no API spend).
# Requires the `claude` CLI installed and logged in.
serve:
	cd backend && INFERENCE_MODE=claude-code ANTHROPIC_API_KEY="" \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

# Optional: run against the paid Anthropic API (reads ANTHROPIC_API_KEY from backend/.env).
serve-api:
	cd backend && unset ANTHROPIC_API_KEY && set -a && . ./.env && set +a && \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

# Backend routes inference to the deployed Modal endpoint (Qwen2.5-VL LoRA on A10G).
# Needs MODAL_ENDPOINT_URL in backend/.env (printed by `make modal-deploy`).
serve-modal:
	cd backend && set -a && . ./.env && set +a && INFERENCE_MODE=modal ANTHROPIC_API_KEY="" \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

# Deploy the Qwen extractor + FastAPI backend to Modal. One-time bootstrap:
#   $(VENV)/bin/pip install modal
#   $(VENV)/bin/modal token new
modal-deploy:
	$(VENV)/bin/modal deploy backend/modal_deploy/serve_qwen.py

# Upload the trained LoRA adapter to Modal's persistent volume (idempotent).
SFT_MODEL_DIR ?= backend/models/qwen2_5_vl_7b
modal-upload-adapter:
	$(VENV)/bin/modal volume create ttb-qwen-adapter 2>/dev/null || true
	$(VENV)/bin/modal volume put --force ttb-qwen-adapter $(SFT_MODEL_DIR)/adapter /adapter

# Manual demo scripts — exercise every verdict bucket against a running backend.
# Backend must already be running (make serve  OR  make serve-modal).

demo-single:
	@echo "Demoing 3 single-label requests — one per verdict bucket"
	@echo "(start the backend in another terminal: make serve)"
	@echo
	bash test/manual/single_01_1_old_tom_spirits_auto_pass.sh                | tail -3
	@echo "..."
	bash test/manual/single_02_2_stones_throw_wine_needs_confirm.sh          | tail -3
	@echo "..."
	bash test/manual/single_04_4_cedar_sage_missing_warning_needs_review.sh  | tail -3

demo-batch:
	bash test/manual/batch_all_9.sh

# All 9 single-label demos + the all-9 batch in one shot
demo-all:
	@for f in test/manual/single_*.sh; do bash "$$f" | tail -1; done
	@echo
	bash test/manual/batch_all_9.sh

# Cross-verify every clean real COLA against the live backend.
# Writes test/eval/real_audit.json + test/eval/REAL_AUDIT.md.
# Takes ~12-20 minutes against the claude-code path (slow per-call).
# Backend must be running (make serve OR make serve-modal).
audit-reals:
	$(PY) test/eval/audit_real_samples.py

# Export every clean real label image + paired application data so the
# agent can drive the upload/batch workflow manually (labels in one
# place, app data in another). Idempotent.
# Output: test/eval/uat_pack/{labels/, applications.csv, applications.json}
uat-pack:
	$(PY) test/eval/export_for_uat.py

# Pull fresh COLAs directly from the TTB Public COLA Registry — full
# Form 5100.31 data including the bottler line, plus the actual label
# image with DPI metadata. ~1 request/sec polite rate; 50 COLAs ≈ 3 min.
# Output: test/eval/data/ttb_live/{ttb_live.csv, images/<ttb_id>.jpg}
# Idempotent: re-runs skip ttb_ids already in ttb_live.csv.
TTB_COUNT ?= 50
scrape-ttb:
	$(PY) test/eval/scrape_ttb_registry.py --count $(TTB_COUNT)

# Audit the engine against the scraped TTB-live tier (real Form 5100.31
# data, including the bottler line). All scraped labels are TTB-approved,
# so the engine's "auto-pass" rate on this set is the real-data accuracy
# metric. Writes test/eval/TTB_LIVE_AUDIT.md + ttb_live_audit.json.
audit-ttb-live:
	$(PY) test/eval/audit_ttb_live.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
