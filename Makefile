# TTB Label Verification — top-level convenience commands.
# All commands assume the backend venv is at backend/.venv.

VENV     := backend/.venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
UVICORN  := $(VENV)/bin/uvicorn
PYTEST   := $(VENV)/bin/pytest

API      ?= http://localhost:8000/api
PORT     ?= 8000

.PHONY: help install install-sft test eval-synth eval-real eval-replay-qwen \
        serve-mock serve-cloud serve-max serve-sft-qwen serve-modal \
        modal-deploy modal-upload-adapter \
        build-eval-data clean

help:
	@echo "Targets:"
	@echo "  install         Create backend venv and install Python deps"
	@echo "  install-sft     Also install heavy ML deps (torch, transformers, peft, bitsandbytes) for sft mode"
	@echo "  test            Run the full pytest suite (rules engine + integration + synthetic gate)"
	@echo "  eval-synth      Boot backend in MOCK mode and run synthetic eval; MUST be 100% (CI gate)"
	@echo "  eval-real       Run real eval against test/eval/data (requires backend already running)"
	@echo "  eval-replay-qwen Replay Qwen outputs from ~/Downloads/qwen_outputs.jsonl through the local rules engine"
	@echo "  build-eval-data Build/refresh the stratified COLA Cloud sample (idempotent)"
	@echo "  serve-mock      Run backend in mock mode (no API key required)"
	@echo "  serve-cloud     Run backend in cloud mode (reads backend/.env; pay-per-token API)"
	@echo "  serve-max       Run backend via Claude Code CLI (uses Max subscription, no API key)"
	@echo "  serve-sft-qwen  Run backend with the local Qwen2.5-VL LoRA adapter (no network)"
	@echo "  serve-modal     Run backend routing inference to a Modal-hosted Qwen endpoint"
	@echo "  modal-deploy    Deploy backend/modal_deploy/serve_qwen.py to Modal"
	@echo "  modal-upload-adapter  Upload trained LoRA adapter to Modal's persistent volume"
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

# Replay Qwen outputs (from the Colab eval cell) through the local rules
# engine and produce test/eval/qwen_report.json — apples-to-apples vs
# test/eval/report.json (Claude). Defaults to ~/Downloads/qwen_outputs.jsonl
# which is where the Colab cell auto-downloads it.
eval-replay-qwen:
	$(PY) test/eval/replay_qwen.py

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
# loads in 4-bit and matches training-time speed.
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
modal-upload-adapter:
	modal volume create ttb-qwen-adapter 2>/dev/null || true
	modal volume put --force ttb-qwen-adapter backend/models/qwen2_5_vl_7b/adapter /adapter

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
