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
        serve-mock serve-cloud serve-max serve-sft-qwen serve-sft-donut \
        build-eval-data clean

help:
	@echo "Targets:"
	@echo "  install         Create backend venv and install Python deps"
	@echo "  install-sft     Also install heavy ML deps (torch, transformers, peft, bitsandbytes) for sft mode"
	@echo "  test            Run the full pytest suite (rules engine + integration + synthetic gate)"
	@echo "  eval-synth      Boot backend in MOCK mode and run synthetic eval; MUST be 100% (CI gate)"
	@echo "  eval-real       Run real eval against test/eval/data (requires backend already running)"
	@echo "  build-eval-data Build/refresh the stratified COLA Cloud sample (idempotent)"
	@echo "  serve-mock      Run backend in mock mode (no API key required)"
	@echo "  serve-cloud     Run backend in cloud mode (reads backend/.env; pay-per-token API)"
	@echo "  serve-max       Run backend via Claude Code CLI (uses Max subscription, no API key)"
	@echo "  serve-sft-qwen  Run backend with the local Qwen2.5-VL LoRA adapter (no network)"
	@echo "  serve-sft-donut Run backend with the local Donut fine-tune (no network)"
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

# Locally-fine-tuned VLMs — no network, no API keys. Requires `make install-sft`.
serve-sft-qwen:
	cd backend && INFERENCE_MODE=sft SFT_MODEL_DIR=models/qwen2_5_vl_7b ANTHROPIC_API_KEY="" \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

serve-sft-donut:
	cd backend && INFERENCE_MODE=sft SFT_MODEL_DIR=models/donut ANTHROPIC_API_KEY="" \
	    ../$(UVICORN) app.main:app --reload --port $(PORT)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
