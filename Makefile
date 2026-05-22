# TTB Label Verification — top-level convenience commands.
# All commands assume the backend venv is at backend/.venv.

VENV     := backend/.venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
UVICORN  := $(VENV)/bin/uvicorn
PYTEST   := $(VENV)/bin/pytest

API      ?= http://localhost:8000/api
PORT     ?= 8000

.PHONY: help install test eval-synth eval-real serve-mock serve-cloud build-eval-data clean

help:
	@echo "Targets:"
	@echo "  install         Create backend venv and install Python deps"
	@echo "  test            Run the full pytest suite (rules engine + integration + synthetic gate)"
	@echo "  eval-synth      Boot backend in MOCK mode and run synthetic eval; MUST be 100% (CI gate)"
	@echo "  eval-real       Run real eval against test/eval/data (requires backend already running in CLOUD mode)"
	@echo "  build-eval-data Build/refresh the stratified COLA Cloud sample (idempotent)"
	@echo "  serve-mock      Run backend in mock mode (no API key required)"
	@echo "  serve-cloud     Run backend in cloud mode (reads backend/.env)"
	@echo "  clean           Remove caches"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt

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

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
