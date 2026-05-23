# Pickup notes for the next Claude session

Drop this file in the chat (or paste its contents) to resume seamlessly.

## Project: TTB Label Verification

A frontend prototype + FastAPI backend for the U.S. TTB's AI-assisted alcohol
label compliance review. Demo on Vercel + a separate backend host.

## State at end of last session

**Three working inference paths** (all wired through the same rules engine):
- `INFERENCE_MODE=mock` — deterministic fixtures, no API key
- `INFERENCE_MODE=cloud` — Anthropic API (pay-per-token, exhausted today)
- `INFERENCE_MODE=claude-code` — routes through Claude Code CLI (uses Max subscription) — **this is what we left running**

**Rules engine: 78/78 unit tests passing.** Per-field severity model with graduated tolerances calibrated to 27 CFR (see [docs/COVERAGE.md](docs/COVERAGE.md)).

**Real-data accuracy (last apples-to-apples measurement, same 20 random clean approved labels, seed=7):**

| | Original | After tier model |
|---|---|---|
| Auto-pass | 5% | 35% |
| Needs-confirm | 30% | 30% |
| Needs-review (false-positive) | 65% | **35%** |
| Warning false-flag | 25% | 15% |

## What's actively in-flight

**Two SFT Colab notebooks running** (or about to run):
- `notebooks/sft_qwen2_5_vl.ipynb` — Unsloth + LoRA on Qwen2.5-VL-7B-Instruct-bnb-4bit
- `notebooks/sft_kimi_vl.ipynb` — transformers + PEFT + TRL on Kimi-VL-A3B-Thinking-2506

Both 32 cells, statically verified (every code cell parses, all required names assigned, all 16 pipeline stages present). Data-prep verified locally against real COLA Cloud data (1714 valid pairs).

**The user is running both in parallel browser tabs.** Latest fixes (commit `3e1dd96`):
- Explicit `numpy>=2.0` install before everything else (was previously deferred and pip kept Colab's stock numpy 1.x, causing ABI mismatch in peft/datasets wheels)
- Explicit `unsloth_zoo` install (Unsloth sibling package not auto-pulled)
- Pin `peft<0.14` (newer peft needs transformers>=4.49 which conflicts with Kimi's pinned 4.48.2)
- Validate cell prechecks `numpy.__version__` upfront with actionable error + paste-fix instruction

**Expected output**: each notebook trains a LoRA adapter (~2-3 hr on A100), evaluates on a held-out test set, then auto-downloads `ttb_sft_{model_tag}.zip` to the user's Mac `~/Downloads`.

## Where to pick up

### Most likely: user has trained adapters and wants integration

1. Unzip both adapters:
   ```bash
   mkdir -p backend/models/qwen2_5_vl_7b backend/models/kimi_vl_a3b_thinking
   unzip ~/Downloads/ttb_sft_qwen2_5_vl_7b.zip -d backend/models/qwen2_5_vl_7b/
   unzip ~/Downloads/ttb_sft_kimi_vl_a3b_thinking.zip -d backend/models/kimi_vl_a3b_thinking/
   ```

2. Add `backend/app/extractors/sft.py` adapter:
   - Loads base model + LoRA via transformers + PEFT (or vLLM if available)
   - Same `ExtractedLabel` schema as the cloud extractor
   - `__init__(model_dir)` reads the manifest.json to know base model + tokenizer

3. Wire `INFERENCE_MODE=sft` into `backend/app/extractors/factory.py` and `backend/app/config.py`.

4. Add `make serve-sft` to the Makefile, document in `backend/README.md`.

5. Head-to-head eval via the existing harness:
   ```bash
   make serve-sft
   make eval-real   # produces test/eval/report.md
   ```

6. Compare to the head-to-head Claude numbers in `test/eval/ANALYSIS.md`.

### If notebooks failed and user still debugging

The validate cell raises a `RuntimeError` with an actionable paste-fix. The most likely remaining failure modes:
- numpy 1.x in memory → restart session
- peft version conflict → `pip install --upgrade 'peft<0.14'`
- unsloth_zoo missing → `pip install unsloth_zoo`

If a NEW error surfaces, ask the user to paste the FULL output of the validate cell (the per-module `✗` lines, not just the RuntimeError summary).

### Vercel deployment (also pending)

The user wants to deploy the frontend to Vercel + the backend on a small host (Render/Railway/Fly.io) running `claude-code` mode so it bills against Max plan instead of API.

Frontend wiring: set `VITE_API_BASE_URL` env var on Vercel to the backend's public URL. The Vite client auto-flips from mock to real backend.

Backend host: needs Claude CLI installed + the user's Claude Code auth token. Easier on a personal Mac mini / VPS than on Vercel's serverless (which can't run the CLI subprocess).

## Recent commit log (most recent first)

```
3e1dd96  sft notebooks: explicit numpy>=2.0 install + unsloth_zoo + numpy version precheck
3d0d72a  sft notebooks: pin peft<0.14, surface actual import errors in validate cell
a415a35  sft notebooks: clean rewrite, statically + locally verified before GPU commit
5b1b678  sft notebooks: fail fast — import validation + 1-step smoke test before training
687d691  sft notebooks: pin numpy<2.0 before install (fixes Colab binary-incompat)  [SUPERSEDED]
ea73b6d  sft notebooks: auto-zip + browser-download adapter to ~/Downloads
75c5b10  sft: two self-sustaining Colab notebooks (Qwen2.5-VL + Kimi-VL)
1387275  engine: per-field severity tiering — needs-review false-pos 65% -> 35%
090ffdc  preprocess: severity model + productName fallback so only real violations flag
31e566b  eval: multi-agent diagnostic + 4 fixes cut warning false-flag 15% -> 2%
4571969  eval: stress-test expansion + conservative engine + coverage matrix
58a7f5f  eval: COLA Cloud harness + engine refinements + integration gate
92720f6  extractor: INFERENCE_MODE=claude-code routes vision via Max subscription
```

## Key files to read first (for the next Claude)

1. `docs/COVERAGE.md` — per-field severity model, what the engine handles vs flags
2. `test/eval/ANALYSIS.md` — most recent real-data measurement
3. `backend/app/rules/engine.py` — where all per-field classifiers live
4. `backend/app/extractors/` — `claude_code.py`, `cloud.py`, `mock.py`, `onprem.py` patterns to follow when adding `sft.py`
5. `notebooks/README.md` — how to run + integrate

## Quick sanity check on resume

```bash
cd backend && source .venv/bin/activate && python -m pytest    # expect: 78 passed
```

## User context

The user is preparing for a TTB interview. The deterministic 100% rules engine + AI-bounded extraction + human-in-the-loop is the right architecture for federal compliance. The SFT bet is to see if a fine-tuned open-weight VLM beats Claude on the narrow task; if it does, that's the production story (privacy + cost + accuracy on agency hardware).
