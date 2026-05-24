# TTB Label Verification — top-level convenience commands.
# All commands assume the backend venv is at backend/.venv.

VENV     := backend/.venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
UVICORN  := $(VENV)/bin/uvicorn
PYTEST   := $(VENV)/bin/pytest

API      ?= http://localhost:8000/api
PORT     ?= 8000

.PHONY: help install install-sft test eval-synth eval-real \
        eval-replay-qwen eval-replay-internvl3 eval-replay-donut eval-compare-all \
        serve-mock serve-cloud serve-max serve-sft-qwen serve-modal \
        modal-deploy modal-upload-adapter \
        demo-single demo-batch demo-all \
        build-eval-data clean

help:
	@echo "Targets:"
	@echo "  install         Create backend venv and install Python deps"
	@echo "  install-sft     Also install heavy ML deps (torch, transformers, peft) for sft mode"
	@echo "  test            Run the full pytest suite (rules engine + integration + synthetic gate)"
	@echo "  eval-synth      Boot backend in MOCK mode and run synthetic eval; MUST be 100% (CI gate)"
	@echo "  eval-real       Run real eval against test/eval/data (requires backend already running)"
	@echo "  eval-replay-qwen     Replay Qwen outputs through the local rules engine"
	@echo "  eval-replay-internvl3 Replay InternVL3-2B outputs"
	@echo "  eval-replay-donut    Replay Donut v2 outputs"
	@echo "  eval-compare-all     Side-by-side table of all model reports vs Claude"
	@echo "  build-eval-data Build/refresh the stratified COLA Cloud sample (idempotent)"
	@echo "  serve-mock      Run backend in mock mode (no API key required)"
	@echo "  serve-cloud     Run backend in cloud mode (reads backend/.env; pay-per-token API)"
	@echo "  serve-max       Run backend via Claude Code CLI (uses Max subscription, no API key)"
	@echo "  serve-sft-qwen  Run backend with the local Qwen2.5-VL LoRA adapter (no network)"
	@echo "  serve-modal     Run backend routing inference to a Modal-hosted Qwen endpoint"
	@echo "  modal-deploy    Deploy backend/modal_deploy/serve_qwen.py to Modal"
	@echo "  modal-upload-adapter  Upload trained LoRA adapter to Modal's persistent volume"
	@echo "  demo-single      Run 3 single-label demos (one per verdict bucket) against local backend"
	@echo "  demo-batch       Run the 9-label batch demo against local backend"
	@echo "  demo-all         Run every single-label demo + the batch (full manual test sweep)"
	@echo "  clean           Remove caches"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

# Heavy ML deps for sft mode (~3 GB). Run after `make install`.
# CUDA users: install torch from https://pytorch.org/ FIRST with the right CUDA wheel.
install-sft:
	$(PIP) install -r backend/requirements-sft.txt

test:
	cd backend && ../$(PY) -m pytest

# Deterministic CI gate. The pytest wrapper in backend/tests/test_eval_synthetic.py
# boots its own backend in mock mode and asserts 100%.
eval-synth:
	cd backend && ../$(PY) -m pytest tests/test_eval_synthetic.py -v

# Real-data accuracy report. NOT a hard gate — see test/EVALUATION.md §3.
# The backend must already be running in CLOUD mode (or onprem) before this.
eval-real:
	$(PY) test/eval/run_eval.py --api $(API) \
	    --csv test/eval/data/cola_sample.csv \
	    --images test/eval/data/images \
	    --out test/eval

# Replay model outputs (from a Colab eval notebook) through the local rules
# engine and produce a test/eval/{label}_report.json — apples-to-apples vs
# test/eval/report.json (Claude). Each target points at a different JSONL
# default that matches where the respective eval notebook auto-downloads it.
eval-replay-qwen:
	$(PY) test/eval/replay_extractions.py \
	    --jsonl ~/Downloads/qwen_outputs.jsonl \
	    --label qwen \
	    --out test/eval/qwen_report.json

eval-replay-internvl3:
	$(PY) test/eval/replay_extractions.py \
	    --jsonl ~/Downloads/internvl3_outputs.jsonl \
	    --label internvl3 \
	    --out test/eval/internvl3_report.json

eval-replay-donut:
	$(PY) test/eval/replay_extractions.py \
	    --jsonl ~/Downloads/donut_outputs.jsonl \
	    --label donut \
	    --out test/eval/donut_report.json

# Aggregate all model reports + Claude into a single side-by-side comparison
# table. Reads whatever {qwen,internvl3,donut}_report.json files exist plus
# the Claude baseline report.json.
eval-compare-all:
	$(PY) test/eval/compare_models.py

build-eval-data:
	cd test/eval/data && $(PY) ../build_dataset.py

serve-mock:
	cd backend && INFERENCE_MODE=mock ANTHROPIC_API_KEY="" ../$(UVICORN) app.main:app --reload --port $(PORT)

serve-cloud:
	cd backend && unset ANTHROPIC_API_KEY && set -a && . ./.env && set +a && \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

# Routes extraction through the `claude` CLI; uses your Claude Code / Max
# subscription quota instead of pay-per-token API credits. Requires Claude
# Code installed and logged in. No ANTHROPIC_API_KEY needed.
serve-max:
	cd backend && INFERENCE_MODE=claude-code ANTHROPIC_API_KEY="" \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

# Locally-fine-tuned Qwen2.5-VL LoRA — no network, no API keys.
# Requires `make install-sft`. On Mac (no CUDA), loads the full-precision
# base (~14 GB unified memory) and runs slow (~30-60s/image). On CUDA hosts
# loads in BF16 and merges LoRA for fast inference.
serve-sft-qwen:
	cd backend && INFERENCE_MODE=sft SFT_MODEL_DIR=models/qwen2_5_vl_7b ANTHROPIC_API_KEY="" \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

# Routes extraction to a Modal-hosted Qwen endpoint. No GPU or heavy ML deps
# locally; the backend just makes HTTPS calls. Reads MODAL_ENDPOINT_URL from
# backend/.env (set after `modal deploy backend/modal_deploy/serve_qwen.py`).
serve-modal:
	cd backend && set -a && . ./.env && set +a && INFERENCE_MODE=modal ANTHROPIC_API_KEY="" \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

# Deploy Qwen to Modal. One-time: `pip install modal && modal token new`.
# After deploy, copy the printed URL into backend/.env as MODAL_ENDPOINT_URL.
modal-deploy:
	modal deploy backend/modal_deploy/serve_qwen.py

# Upload the trained LoRA adapter to Modal's persistent volume.
# Idempotent — re-running with new weights overwrites the volume contents.
SFT_MODEL_DIR ?= backend/models/qwen2_5_vl_7b
modal-upload-adapter:
	modal volume create ttb-qwen-adapter 2>/dev/null || true
	modal volume put --force ttb-qwen-adapter $(SFT_MODEL_DIR)/adapter /adapter

# Manual demo scripts — exercise every verdict bucket against a running backend.
# Requires `make serve-mock` (or serve-cloud / serve-modal) running on :8000.
# See test/manual/README.md for full details.

demo-single:
	@echo "Demoing 3 single-label requests — one per verdict bucket"
	@echo "(start the backend in another terminal: make serve-mock)"
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

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
