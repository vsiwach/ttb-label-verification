# SFT notebooks — fine-tune an open-source VLM for TTB label extraction

Two self-contained Colab notebooks that train a LoRA adapter on top of an
open-weight vision-language model, using data pulled from the COLA Cloud
free sample (CC0). The trained adapter integrates back into the FastAPI
backend as a new `INFERENCE_MODE=sft` — no Anthropic API calls needed at
inference time once the adapter is downloaded.

| Notebook | Base model | Library | Active params | Realistic Colab time |
|---|---|---|---|---|
| [`sft_qwen2_5_vl.ipynb`](sft_qwen2_5_vl.ipynb) | `unsloth/Qwen2.5-VL-7B-Instruct` | Unsloth + TRL | 7B | A100: ~3-4 hr · T4: skip (OOM) |
| [`sft_kimi_vl.ipynb`](sft_kimi_vl.ipynb) | `moonshotai/Kimi-VL-A3B-Thinking-2506` | transformers + PEFT + TRL | 3B (16B MoE) | A100: ~2-3 hr · T4: ~5-6 hr |

## Why two

Different bets, same eval harness — pick the winner head-to-head:

- **Qwen2.5-VL-7B (Unsloth)** — well-trodden recipe, mature fine-tuning ecosystem, strong on document/OCR benchmarks. Lower variance, faster to first checkpoint.
- **Kimi-VL-A3B-Thinking** — newer, MIT-licensed, has built-in chain-of-thought reasoning. Smaller active params → fits on a T4 + faster inference at serve time. Upside bet on whether reasoning helps the brand-vs-fanciful / multi-language COO edge cases that bite Claude.

## How to run

1. Open Colab → File → Upload notebook → drag-drop one of the `.ipynb` files.
2. `Runtime → Change runtime type → GPU`:
   - For Qwen: **A100** (40 GB) required. Pro / Pro+ subscription.
   - For Kimi: T4 (16 GB) works but slowly; A100 is faster.
3. `Runtime → Run all`. The notebook is end-to-end automated:
   - Mounts Google Drive (workspace at `/MyDrive/ttb_sft/{model_tag}/`)
   - Pulls the COLA Cloud sample zip (~500 KB)
   - Builds (image, structured-JSON) pairs from `BRAND_NAME`, `CLASS_NAME`, `PRODUCT_NAME`, `OCR_ABV`, `OCR_VOLUME`, `ORIGIN_NAME`, `OCR_TEXT`
   - Downloads ~800 label images from the COLA Cloud CDN
   - Splits 80/10/10 train/val/test (seeded for reproducibility)
   - LoRA fine-tune (rank 16, attention + MLP projections), 3 epochs
   - Per-field accuracy + warning-presence accuracy on the held-out test set
   - Saves the adapter, processor config, and eval report to Drive
   - **Zips everything and triggers a browser download** — adapter lands at `~/Downloads/ttb_sft_{model_tag}.zip` on your Mac
4. Caffeinate your Mac so the tab stays alive. (`brew install caffeine` or `caffeinate -i &` in a terminal.)

## Running both in parallel

With Colab Pro you can have two simultaneous A100 sessions — open the Qwen notebook in one browser tab, the Kimi notebook in another. Each tab gets its own VM.

On the free tier you're limited to one GPU session at a time. Either run them sequentially OR use two Google accounts (one notebook on each).

## After training

The Drive layout will look like:

```
/MyDrive/ttb_sft/{model_tag}/
├── adapter/                  ← LoRA weights + processor + manifest.json
├── checkpoints/              ← per-epoch checkpoints (drop after picking the best)
├── splits/
│   ├── train.jsonl
│   ├── val.jsonl
│   └── test.jsonl
└── eval_report.json          ← per-field accuracy on the test set
```

To integrate locally:

```bash
# 1. Download adapter (use rclone / Google Drive desktop / browser)
mkdir -p backend/models/{model_tag}
cp -r '/Users/you/Google Drive/MyDrive/ttb_sft/{model_tag}/adapter/'* backend/models/{model_tag}/

# 2. Once we add backend/app/extractors/sft.py:
INFERENCE_MODE=sft SFT_MODEL_DIR=backend/models/{model_tag} \
    make serve-sft   # to be added to Makefile

# 3. Re-run the eval to compare head-to-head with Claude:
make eval-real
```

## Data sources

- **COLA Cloud free sample** (https://colacloud.us, CC0): 1,000 records, ~1,750 images, includes per-image OCR via Google Vision plus LLM-extracted category metadata. This is the primary training corpus. It's a clean subset of the official TTB Public COLA Registry.
- **TTB data.gov "Public COLA Registry Search and Download"** (https://catalog.data.gov/dataset/ttb-public-cola-registry-search-and-download-extract-data-about-colas-that-meet-specified--cafd3): the linked resource turns out to be a wrapper around the interactive UI at `ttbonline.gov` — no public bulk CSV endpoint. If you later want more data, options are: (a) buy the COLA Cloud full corpus (2.6M records), (b) write a per-TTB-ID scraper against the public registry's detail pages (respect rate limits and terms), or (c) hand-annotate ~100 additional hard cases to push past Claude's distillation ceiling.

## Training targets — how we generate ground truth

The notebooks synthesize a structured JSON target per (image, COLA row) pair from the dataset metadata:

```jsonc
{
  "fields": {
    "Brand name":          {"value": "Half Acre", "confidence": 0.95},
    "Class & type":        {"value": "beer", "confidence": 0.95},
    "Alcohol content":     {"value": "5.2% Alc./Vol.", "confidence": 0.92},  // from OCR_ABV
    "Net contents":        {"value": "12 FL OZ", "confidence": 0.92},        // from OCR_VOLUME
    "Bottler name/address": {"value": "Brewed by Half Acre, Chicago, Illinois", "confidence": 0.85},
    "Country of origin":   {"value": "Product of Italy", "confidence": 0.85} // imports only
  },
  "government_warning": {
    "present": true,
    "detected_text": "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL ...",  // from OCR_TEXT
    "casing_all_caps": true,
    "heading_bold": true,
    "body_bold": false,
    "approx_font_mm": null,
    "contrast_ok": true,
    "separate_and_apart": true
  },
  "image_quality": {"score": 0.85, "legible": true, "note": null}
}
```

The schema matches `backend/app/extractors/base.py::ExtractedLabel` exactly — the trained adapter is a drop-in replacement for the Claude path.

## Honest caveats

- **Distillation ceiling**: a model trained against COLA Cloud's auto-generated labels is bounded by the quality of those labels. Google Vision OCR + GPT-4o (LLM_CATEGORY) make ~5-10% errors. To push past that ceiling you'd hand-verify ~100 hard cases (brand-vs-fanciful, multi-language COO, partial warnings) and append them to the training set.
- **Domain narrowing**: the SFT'd model will be better at TTB labels than Claude *on similar artwork* and worse on unusual artwork. The rules engine still backstops with conservative routing.
- **Realistic latency win**: Qwen2.5-VL-7B 4-bit on a single 4090 inferences at ~1.5 s/label. Kimi-VL-A3B at ~0.8 s/label. Vs Claude's ~10 s (API) or ~30 s (CLI).
- **Best results need GPU at serve time**. Production deploy options: a small GPU host (Modal, Replicate, Banana), a TPU pod, or on-prem inside the agency boundary (matches the PRD's Phase-2 plan).
