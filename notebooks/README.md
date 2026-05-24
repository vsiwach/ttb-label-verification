# SFT notebooks — fine-tune + evaluate open VLMs for TTB label extraction

Self-contained Colab notebooks that:
1. Train a LoRA adapter (or full fine-tune for Donut) on top of an open-weight
   vision-language model, using data pulled from the COLA Cloud free sample (CC0).
2. Evaluate the trained adapter on the same test set Claude was scored on,
   producing a JSONL fixture that the local rules engine then scores via
   `make eval-replay-{model}`.

Trained adapter integrates back into the FastAPI backend as `INFERENCE_MODE=sft`
or `INFERENCE_MODE=modal` for production serving.

## Inventory

### Training (3 notebooks — pick one per model)

| Notebook | Base model | Stack | Active params | Realistic Colab time |
|---|---|---|---|---|
| [`sft_qwen2_5_vl.ipynb`](sft_qwen2_5_vl.ipynb) | `Qwen/Qwen2.5-VL-7B-Instruct` | transformers + peft + trl (BF16) | 7B | A100: ~3-4 hr |
| [`sft_internvl3_2b.ipynb`](sft_internvl3_2b.ipynb) | `OpenGVLab/InternVL3-2B` | transformers + peft + trl (BF16) | 2B | A100: ~1-2 hr · T4: ~3 hr |
| [`sft_donut_v2.ipynb`](sft_donut_v2.ipynb) | `naver-clova-ix/donut-base` | transformers + Trainer (BF16, full fine-tune, no LoRA) | 200M | A100: ~1.5 hr · T4: ~2 hr |

### Eval (3 notebooks — one per trained model)

| Notebook | Reads adapter from | Outputs |
|---|---|---|
| [`eval_qwen_drive.ipynb`](eval_qwen_drive.ipynb) | `MyDrive/ttb_sft/qwen2_5_vl_7b/adapter/` | `qwen_outputs.jsonl` |
| [`eval_internvl3_drive.ipynb`](eval_internvl3_drive.ipynb) | `MyDrive/ttb_sft/internvl3_2b/adapter/` | `internvl3_outputs.jsonl` |
| [`eval_donut_drive.ipynb`](eval_donut_drive.ipynb) | `MyDrive/ttb_sft/donut_v2/model/` | `donut_outputs.jsonl` |

### Utility

| File | Purpose |
|---|---|
| [`_apply_baselines.py`](_apply_baselines.py) | Re-runnable script that propagates the canonical SYSTEM_PROMPT (and any future common-baseline updates) to every training + eval notebook. Idempotent. |

## Common baseline (consistent across all notebooks)

Every notebook above uses the same verified-working stack and conventions:

- **transformers==4.51.3** — has Qwen2.5-VL + the 4.49 config-regression fix
- **peft>=0.13 + torchao>=0.16** — peft 0.13+ asserts on torchao≥0.16
- **protobuf>=5.27** — transformers 4.48+ needs `runtime_version`
- **numpy>=2.0,<2.2** — wheel ABI sweet spot, with idempotent install + auto-restart
- **BF16 throughout** (training + inference) — no quantization, no dtype mismatch
- **Group-aware train/val/test split** by COLA `TTB_ID` (no image leak across splits)
- **Canonical field names** (`Brand name`, `Class & type`, etc.) enforced in SYSTEM_PROMPT to prevent snake_case drift
- **Drive mount everywhere** — no browser uploads of the heavy adapter/model files

## Priority — which model to train next

See [`docs/MODEL_PRIORITY.md`](../docs/MODEL_PRIORITY.md) for the full decision
framework. TL;DR ordering:

1. **Qwen2.5-VL-7B BF16** first — highest accuracy ceiling
2. **InternVL3-2B BF16** second — best speed-to-accuracy + cheapest deployment
3. **Donut v2** only if there's slack — high variance, smallest-model angle

## How to run a training notebook

1. Colab → File → Upload notebook → pick the `.ipynb` from this folder
2. **Runtime → Change runtime type → A100 + High-RAM** → Save
3. Runtime → Disconnect and delete runtime (clean VM)
4. Runtime → **Run all** (1st click — installs deps, kernel auto-crashes; "session crashed" banner is expected)
5. Runtime → **Run all** (2nd click — Drive permission dialog → accept; trains end-to-end)
6. When training completes, the bundle auto-downloads to `~/Downloads/ttb_sft_{model}.zip` AND lands in `MyDrive/ttb_sft/{model}/`

## How to run an eval notebook

Prerequisite: the corresponding training notebook has completed and left the adapter in `MyDrive/ttb_sft/{model}/adapter/` (or `/model/` for Donut). Plus `MyDrive/ttb_sft/eval/cola_sample.csv` (upload once from `test/eval/data/cola_sample.csv`).

1. Same Colab setup as training (A100 + High-RAM, clean runtime)
2. Runtime → Run all (twice, for install dance)
3. `{model}_outputs.jsonl` auto-downloads to `~/Downloads/`

Then locally:

```bash
make eval-replay-qwen          # or eval-replay-internvl3 / eval-replay-donut
```

This scores the JSONL through the local rules engine (same metrics + same logic
as Claude's `test/eval/report.json`), writes `test/eval/{model}_report.json`,
and prints the side-by-side table.

After multiple models have eval reports:

```bash
make eval-compare-all          # aggregate side-by-side table
```

## Updating the common baseline

If you discover another shared fix (e.g. a new dep pin, or a stronger
SYSTEM_PROMPT), edit it in `_apply_baselines.py` and re-run:

```bash
python3 notebooks/_apply_baselines.py
```

It's idempotent — safely re-applies to every notebook in the inventory.

## Data + ground truth

- **COLA Cloud free sample** (https://colacloud.us, CC0): ~1,000 COLA records, ~1,750 label images. Clean subset of the official TTB Public COLA Registry, with per-image OCR (Google Vision) + LLM-extracted category metadata.
- Training targets are synthesized from the dataset metadata into a JSON schema that matches `backend/app/extractors/base.py::ExtractedLabel` exactly — the trained adapter is a drop-in replacement for the Claude path.

## Honest caveats

- **Distillation ceiling**: training against COLA Cloud's auto-generated labels caps quality at the labels' ~5-10% error rate. To push past, hand-verify ~100 hard cases (brand-vs-fanciful, multi-language COO, partial warnings) and append to the training set.
- **GPU required at serve time**: production deploy options are Modal/Replicate/Banana (cheap, scale-to-zero) or on-prem GPU inside the agency boundary (matches Treasury's FedRAMP/Azure-Gov pattern). See `backend/modal_deploy/serve_qwen.py` for a ready-to-deploy Modal script.

## What we tried that didn't work (for posterity)

These notebooks existed earlier in the session but were removed because the models proved unsuitable for SFT:

| Model | Why dropped |
|---|---|
| Kimi-VL-A3B-Thinking | MoE + inference-only modeling code (`assert not self.training`) — training landmines |
| Phi-3.5-vision | Microsoft's custom `modeling_phi3_v.py` drift vs current transformers; async CUDA asserts during training |

The decision framework in [`docs/MODEL_PRIORITY.md`](../docs/MODEL_PRIORITY.md) explains why we now focus on Qwen, InternVL3, and Donut.
