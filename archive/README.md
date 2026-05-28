# archive/

Preserved files that are no longer part of the live deployment but are
kept for reproducibility — the eval narrative, the v1 head-to-head, and
the training pipeline that produced the v2 LoRA.

Nothing here is imported by the runtime. The Vercel function (`api/index.py`),
the live Modal endpoints (`backend/modal_deploy/serve_qwen_v2.py` and
`serve_tesseract.py`), and the FastAPI backend all run without any
reference to this directory. Safe to ignore unless you're retraining
v3 or rerunning the head-to-head eval.

## What's in here

### `modal_deploy/`

- **`serve_qwen.py`** — v1 Modal endpoint (Qwen + COLA Cloud training).
  Superseded by `backend/modal_deploy/serve_qwen_v2.py`. Kept so a v1-vs-v2
  head-to-head can still be reproduced: `modal deploy archive/modal_deploy/serve_qwen.py`.
- **`serve_full_app.py`** — alternative deployment topology that bundles
  React + FastAPI + Qwen into one Modal container (the "agency-hosted"
  privacy topology described on PPT slide 9). Not the active deploy; the
  live system runs Vercel front-end + Modal back-end as separate concerns.
- **`train_qwen.py`** — Modal A100 training entrypoint that produced
  the v2 LoRA. Invoked once via `make modal-train`; the trained adapter
  was downloaded back to Drive and the same Drive path is loaded by the
  live `serve_qwen_v2.py` from a persistent Modal volume.

### `notebooks/`

Rejected-model exploration notebooks from the SFT bake-off (Day 2).
Each loaded its model + trained a LoRA + evaluated on the same 200-row
holdout used by the eventual v2 winner.

- **`sft_donut_v2.ipynb`** + **`eval_donut_drive.ipynb`** — Donut full
  fine-tune. Lost on label OCR; Donut's encoder doesn't have the same
  document-image inductive bias for label backgrounds as the Qwen-VL
  vision tower.
- **`sft_internvl3_2b.ipynb`** + **`eval_internvl3_drive.ipynb`** —
  InternVL3-2B LoRA. Smaller model, faster, but lost on the trained
  fields. Worth revisiting if the cost/perf curve matters and 90% of
  Qwen-VL's accuracy is enough.

The active training notebooks (`sft_qwen2_5_vl_v2.ipynb`,
`eval_qwen_drive.ipynb`, `eval_v1_vs_v2_drive.ipynb`) stay at
`notebooks/`.

### `scripts/`

- **`morning_pipeline.sh`** + **`overnight_pipeline.sh`** — chained
  shell pipelines that build the JSONL, upload to Modal, kick off
  training, download the adapter, and re-run the head-to-head. Used
  when training v2; usable verbatim for v3.
- **`build_v2_notebooks.py`** — generator that produced the v2
  notebooks from a template. Kept alongside the pipelines.

## When to un-archive

If you decide to ship a v3 LoRA, the pipeline scripts + `train_qwen.py`
come back into use. The donut/internvl3 notebooks stay archived unless
you decide to do another model bake-off.

If a deployment scenario calls for the bundled `serve_full_app.py`
topology — e.g. FedRAMP boundary that won't allow a separate Vercel
frontend — copy it back to `backend/modal_deploy/` and re-deploy.
