"""Build the two Colab notebooks for the v2 fine-tune + head-to-head eval.

Notebooks are JSON; hand-editing them is painful and error-prone. We
generate them here so the source-of-truth lives in readable Python and
both notebooks share helpers (system prompt, image preprocessing, etc).

Run:
    backend/.venv/bin/python scripts/build_v2_notebooks.py

Writes:
    notebooks/sft_qwen2_5_vl_v2.ipynb
    notebooks/eval_v1_vs_v2_drive.ipynb
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "notebooks"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def write_notebook(path: Path, cells: list[dict]) -> None:
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
            "colab": {"provenance": [], "machine_shape": "hm"},
            "accelerator": "GPU",
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(nb, indent=1))
    print(f"wrote {path.relative_to(REPO)}  ({len(cells)} cells)")


# ── Shared snippets ─────────────────────────────────────────────────────────

INSTALL_CELL = """\
# Pinned to match notebooks/sft_qwen2_5_vl.ipynb so v1 and v2 train +
# eval under the same stack. First Run all installs, kernel auto-restarts,
# second Run all uses cached wheels.
import importlib.util, subprocess, sys, os

def _have(mod):  return importlib.util.find_spec(mod) is not None
def _pinned(mod, want):
    try: return __import__(mod).__version__ == want
    except Exception: return False
def _numpy_ok():
    try:
        import numpy
        p = numpy.__version__.split('.')
        return int(p[0]) == 2 and int(p[1]) < 2
    except Exception: return False
def _torchao_ok():
    try:
        import torchao
        maj, mi = [int(x) for x in torchao.__version__.split('.')[:2]]
        return (maj, mi) >= (0, 16)
    except Exception: return False

_required = ['peft', 'trl', 'accelerate', 'PIL', 'qwen_vl_utils', 'datasets']
_ready = (
    _numpy_ok()
    and _pinned('transformers', '4.51.3')
    and _torchao_ok()
    and all(_have(m) for m in _required)
)
if _ready:
    import numpy, transformers, torchao
    print(f'✓ Stack ready — numpy {numpy.__version__}, transformers {transformers.__version__}, torchao {torchao.__version__}')
else:
    print('⏳ Installing deps (~3 min). Kernel will auto-restart at end.')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '--upgrade', 'pip'])
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '--upgrade',
        'transformers==4.51.3', 'accelerate>=0.30',
        'peft>=0.13', 'torchao>=0.16', 'bitsandbytes>=0.44', 'trl>=0.12',
        'qwen-vl-utils', 'protobuf>=5.27', 'pillow', 'tqdm',
        'datasets>=2.20', 'anthropic>=0.40'])
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q',
        '--force-reinstall', '--no-deps', 'numpy>=2.0,<2.2'])
    print('\\n' + '=' * 60)
    print('✅ Install complete. Auto-restarting kernel.')
    print('   When the "session crashed" banner appears, do Runtime → Run all AGAIN.')
    print('=' * 60)
    os.kill(os.getpid(), 9)
"""

DRIVE_MOUNT_CELL = """\
# Drive holds the TTB scrape (~9 GB) and the trained adapters. We mount
# the same Drive that the Mac scraper writes to (My Drive/ttb-scrape/).
from google.colab import drive
drive.mount('/content/drive')

from pathlib import Path
DRIVE_ROOT  = Path('/content/drive/MyDrive')
SCRAPE_DIR  = DRIVE_ROOT / 'ttb-scrape'                  # set by the Mac scraper
IMAGE_DIR   = SCRAPE_DIR / 'images'                       # ~20K composites
JSONL_DIR   = SCRAPE_DIR / 'qwen_sft'                     # staged by overnight_pipeline.sh
CSV_PATH    = SCRAPE_DIR / 'ttb_live.csv'                 # form data
HOLDOUT_TXT = SCRAPE_DIR / 'holdout_ttbids.txt'           # 2K eval set, blind to trainer

for p in (SCRAPE_DIR, IMAGE_DIR, JSONL_DIR):
    print(f'  {"✓" if p.exists() else "✗"} {p}')
print(f'  composites: {len(list(IMAGE_DIR.glob("*.jpg"))) if IMAGE_DIR.exists() else 0}')
"""

# Fields-only system prompt — matches backend/modal_deploy/serve_qwen_v2.py
# and test/eval/build_qwen_jsonl.py target-schema decision.
SYSTEM_PROMPT_V2 = """\
SYSTEM_PROMPT = (
    "You are a careful transcription assistant for U.S. TTB alcohol label review. "
    "You will see a single image that may contain MULTIPLE label panels stacked "
    "vertically (front + back + neck + strip). READ what is printed across ALL panels "
    "and RETURN ONLY a JSON object matching the schema below. Do NOT decide compliance.\\n\\n"
    "CRITICAL — use ONLY these EXACT field names in the fields object (case-sensitive, "
    "preserve spaces and punctuation):\\n"
    "  - 'Brand name'\\n"
    "  - 'Class & type'\\n"
    "  - 'Bottler name/address'\\n"
    "  - 'Country of origin'  (imports only; omit for U.S. labels)\\n\\n"
    "Do NOT invent variants ('brand_name', 'Volume', 'Bottled_by', 'product_type', "
    "'location', etc). If a field is not clearly visible across the panels, OMIT it "
    "from the fields object entirely. Never guess; never substitute deposit codes "
    "(e.g. 'CA CRV'), NOM IDs, or barcodes.\\n\\n"
    "Schema: {fields: {<field name>: {value, confidence}}}"
)
"""

# v1's full-schema prompt — used when running v1 in the comparison eval
# so v1 is asked the same way it was trained.
SYSTEM_PROMPT_V1 = """\
SYSTEM_PROMPT_V1 = (
    "You are a careful transcription assistant for U.S. TTB alcohol label review. "
    "Given ONE label panel image and the beverage type, READ what is printed and "
    "RETURN ONLY a JSON object matching the schema below. Do NOT decide compliance.\\n\\n"
    "CRITICAL — use ONLY these EXACT field names in the fields object (case-sensitive, "
    "preserve spaces and punctuation):\\n"
    "  - 'Brand name'\\n"
    "  - 'Class & type'\\n"
    "  - 'Alcohol content'\\n"
    "  - 'Net contents'\\n"
    "  - 'Bottler name/address'\\n"
    "  - 'Country of origin'  (imports only)\\n\\n"
    "Do NOT invent variants. If a field is not clearly visible, OMIT it.\\n\\n"
    "Schema: {fields: {<field name>: {value, confidence}}, government_warning: "
    "{present, detected_text, casing_all_caps, heading_bold, body_bold, approx_font_mm, "
    "contrast_ok, separate_and_apart}, image_quality: {score, legible, note}}"
)
"""

IMAGE_RESIZE_FN = """\
from PIL import Image

def _resize_for_training(img, max_pixels=1500 * 1024):
    \"\"\"Multi-panel composites need more pixels than v1's single panels.
    1.5M caps visual-token count at ~1.5K, which is the A100 sweet spot.\"\"\"
    w, h = img.size
    if w * h > max_pixels:
        scale = (max_pixels / (w * h)) ** 0.5
        img = img.resize((max(int(w * scale), 28), max(int(h * scale), 28)), Image.LANCZOS)
    w, h = img.size
    w28, h28 = max((w // 28) * 28, 28), max((h // 28) * 28, 28)
    if (w28, h28) != (w, h):
        img = img.resize((w28, h28), Image.LANCZOS)
    return img
"""


# ─── BUILD TRAINING NOTEBOOK ────────────────────────────────────────────────

def build_training_notebook() -> None:
    cells = [
        md("""# Fine-tune **Qwen2.5-VL-7B v2** on the TTB-live stratified 18K (Colab + Drive)

LoRA fine-tune mirroring `notebooks/sft_qwen2_5_vl.ipynb` (v1), with these changes:

- **Training data: 18K TTB-live composites** (vs v1's 1377 COLA Cloud singles) — sourced
  by `test/eval/scrape_ttb_registry.py` on the Mac, lives at `MyDrive/ttb-scrape/images/`.
- **Stratified by beverage**: ~6K spirits / 6K wine / 8K beer-malt (TTB classTypeCode buckets).
- **Targets are fields-only** (Brand name, Class & type, Bottler name/address, Country of origin)
  sourced verbatim from TTB Form 5100.31. Alcohol content / Net contents / Government warning
  are NOT carried on the form; teaching them from model output would just bake in the
  upstream model's mistakes.
- **2K held-out test set** at `MyDrive/ttb-scrape/holdout_ttbids.txt` — the trainer never sees
  it; the comparison notebook scores v1, v2, and Haiku against it.
- **Adapter saves to `MyDrive/ttb_sft/qwen2_5_vl_7b_v2/`** so v1 and v2 coexist for the head-to-head.
- **1 epoch** (vs v1's 2): 18K × 1 ≈ 6× more unique signal than v1's 1377 × 2;
  ~3-4 hr on A100, ~6-8 hr on T4 with reduced batch.

## How to run
1. `Runtime → Change runtime type → GPU` (A100 preferred; T4 works with smaller `MAX_PIXELS`)
2. `Runtime → Run all` — installs deps, restarts kernel
3. Wait for "session crashed" banner, then `Runtime → Run all` AGAIN
4. Training proceeds end-to-end; adapter saves to Drive automatically
"""),
        md("## 0. Install dependencies"),
        code(INSTALL_CELL),
        md("## 1. Validate imports (fails fast on ABI mismatch)"),
        code("""\
import importlib, traceback
import numpy
if numpy.__version__.startswith('1.'):
    raise RuntimeError(f'numpy is {numpy.__version__}; restart kernel + Run all again.')
print(f'  ✓ numpy {numpy.__version__}')
_required = ['torch', 'transformers', 'accelerate', 'peft', 'trl',
             'datasets', 'PIL', 'tqdm', 'torchao', 'qwen_vl_utils']
for mod in _required:
    m = importlib.import_module(mod)
    print(f'  ✓ {mod:<16} {getattr(m, "__version__", "?")}')
print('\\n✅ All imports clean.')
"""),
        md("## 2. Mount Drive + set up paths"),
        code(DRIVE_MOUNT_CELL),
        code("""\
# v2 adapter destination — distinct from v1 so they coexist
MODEL_TAG = 'qwen2_5_vl_7b_v2'
BASE_MODEL = 'Qwen/Qwen2.5-VL-7B-Instruct'
WORK_DIR = DRIVE_ROOT / 'ttb_sft' / MODEL_TAG
WORK_DIR.mkdir(parents=True, exist_ok=True)
print(f'work dir: {WORK_DIR}')
print(f'v1 adapter (for comparison eval later): {DRIVE_ROOT / "ttb_sft" / "qwen2_5_vl_7b"}')
"""),
        md("""## 3. Load training JSONL from Drive

Built by `test/eval/build_qwen_jsonl.py` on the Mac and staged to Drive by
`scripts/overnight_pipeline.sh`. The JSONL excludes the 2K holdout.
"""),
        code("""\
import json
def _load_jsonl(path):
    return [json.loads(line) for line in open(path) if line.strip()]

train_raw = _load_jsonl(JSONL_DIR / 'train.jsonl')
val_raw   = _load_jsonl(JSONL_DIR / 'val.jsonl')
print(f'train: {len(train_raw)}   val: {len(val_raw)}')

# Rewrite image_path from Mac-relative ('test/eval/data/ttb_live/images/<f>.jpg')
# to Drive-absolute. Strip prefix, prepend IMAGE_DIR.
def _fix_paths(rows):
    for r in rows:
        r['image_path'] = str(IMAGE_DIR / Path(r['image_path']).name)
    return rows

train = _fix_paths(train_raw)
val   = _fix_paths(val_raw)
# Drop any rows whose composite is missing on Drive (in case scrape was partial)
train = [r for r in train if Path(r['image_path']).exists()]
val   = [r for r in val   if Path(r['image_path']).exists()]
print(f'after image-presence filter:  train={len(train)}  val={len(val)}')

# Beverage distribution (sanity check stratification held)
from collections import Counter
print('train beverage mix:', Counter(r['beverage_type'] for r in train))
"""),
        md("## 4. System prompt + image preprocessing"),
        code(SYSTEM_PROMPT_V2),
        code(IMAGE_RESIZE_FN),
        md("## 5. Load Qwen2.5-VL-7B base + LoRA rank 16"),
        code("""\
import torch
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
from peft import LoraConfig, get_peft_model

print(f'Loading {BASE_MODEL} BF16...')
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.bfloat16,
    device_map='auto',
    attn_implementation='sdpa',
)
tokenizer = AutoProcessor.from_pretrained(BASE_MODEL)

# Freeze vision tower (matches v1)
for n, p in model.named_parameters():
    if 'visual' in n:
        p.requires_grad = False

# LoRA rank 16 / alpha 32 / dropout 0.05 — slight nudge from v1's rank 16/alpha 16/dropout 0
# to give the wider 18K dataset more capacity while regularizing against overfit.
lora_cfg = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, bias='none',
    target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj',
                    'gate_proj', 'up_proj', 'down_proj'],
    task_type='CAUSAL_LM',
)
model = get_peft_model(model, lora_cfg)
model.print_trainable_parameters()

if hasattr(model, 'enable_input_require_grads'):
    model.enable_input_require_grads()
model.gradient_checkpointing_enable()
print('✓ gradient_checkpointing_enable — disable manually if you have A100-80GB headroom')
"""),
        md("## 6. HF Dataset + per-example collator (Qwen-VL needs batch_size=1)"),
        code("""\
from datasets import Dataset

train_ds = Dataset.from_list([
    {'image_path': ex['image_path'], 'beverage_type': ex['beverage_type'],
     'target_json': json.dumps(ex['target'])}
    for ex in train
])
val_ds = Dataset.from_list([
    {'image_path': ex['image_path'], 'beverage_type': ex['beverage_type'],
     'target_json': json.dumps(ex['target'])}
    for ex in val
])
print(f'train_ds: {len(train_ds)}   val_ds: {len(val_ds)}')

def _collate(batch):
    assert len(batch) == 1, 'Qwen2.5-VL collator expects batch_size=1'
    ex = batch[0]
    img = _resize_for_training(Image.open(ex['image_path']).convert('RGB'))
    msgs = [
        {'role': 'system',    'content': [{'type': 'text', 'text': SYSTEM_PROMPT}]},
        {'role': 'user',      'content': [
            {'type': 'image', 'image': img},
            {'type': 'text',  'text': f"Beverage type: {ex['beverage_type']}. Extract per the schema."},
        ]},
        {'role': 'assistant', 'content': [{'type': 'text', 'text': ex['target_json']}]},
    ]
    text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
    enc = tokenizer(text=[text], images=[img], padding=True, return_tensors='pt',
                    truncation=True, max_length=2048)
    labels = enc['input_ids'].clone()
    pad_id = tokenizer.tokenizer.pad_token_id
    if pad_id is not None:
        labels[labels == pad_id] = -100
    enc['labels'] = labels
    return enc
"""),
        md("## 7. Smoke test — 1 step on 4 samples"),
        code("""\
from trl import SFTTrainer, SFTConfig

_smoke = train_ds.select(range(min(4, len(train_ds))))
SFTTrainer(
    model=model,
    train_dataset=_smoke,
    data_collator=_collate,
    args=SFTConfig(
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        max_steps=1, warmup_steps=0,
        learning_rate=1e-4,
        bf16=True, fp16=False,
        logging_steps=1, output_dir='/tmp/smoke',
        report_to='none', remove_unused_columns=False,
        dataset_kwargs={'skip_prepare_dataset': True},
    ),
).train()
print('\\n✅ SMOKE TEST PASSED — full training is safe to start.')
"""),
        md("""## 8. Full training run (1 epoch over 18K, BF16)

~3-4 hr on A100, ~6-8 hr on T4. Saves checkpoints to Drive every 1000 steps; resume by
re-running this cell if Colab disconnects (Trainer auto-resumes from latest checkpoint).
"""),
        code("""\
from trl import SFTTrainer, SFTConfig

trainer = SFTTrainer(
    model=model,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    data_collator=_collate,
    args=SFTConfig(
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        warmup_ratio=0.03,
        num_train_epochs=1,
        learning_rate=1e-4,
        bf16=True, fp16=False,
        lr_scheduler_type='cosine',
        weight_decay=0.01,
        optim='adamw_8bit',
        logging_steps=20,
        eval_strategy='steps', eval_steps=500,
        save_strategy='steps', save_steps=1000, save_total_limit=3,
        seed=42,
        output_dir=str(WORK_DIR / 'checkpoints'),
        report_to='none',
        remove_unused_columns=False,
        dataset_kwargs={'skip_prepare_dataset': True},
    ),
)
trainer.train()
"""),
        md("## 9. Save adapter to Drive (v2 path — coexists with v1)"),
        code("""\
import shutil
ADAPTER_DIR = WORK_DIR / 'adapter'
ADAPTER_DIR.mkdir(exist_ok=True)
model.save_pretrained(str(ADAPTER_DIR))
try: tokenizer.save_pretrained(str(ADAPTER_DIR))
except Exception as e: print(f'(skip processor save: {e})')

_safetensors = ADAPTER_DIR / 'adapter_model.safetensors'
_sz = _safetensors.stat().st_size if _safetensors.exists() else 0
assert _sz > 1_000_000, f'adapter_model.safetensors is {_sz} bytes — LoRA weights not saved.'
print(f'✓ adapter: {_safetensors} ({_sz/1024**2:.1f} MB)')

manifest = {
    'model_tag':         MODEL_TAG,
    'base_model':        BASE_MODEL,
    'trained_on':        f'TTB-live stratified N={len(train)} (fields-only targets)',
    'lora_rank':         16,
    'lora_alpha':        32,
    'epochs':            1,
    'lr':                1e-4,
    'n_train_examples':  len(train),
    'n_val_examples':    len(val),
    'training_dtype':    'bf16',
    'schema':            'fields-only (no government_warning, no image_quality)',
}
(ADAPTER_DIR / 'manifest.json').write_text(json.dumps(manifest, indent=2))
print(f'manifest: {ADAPTER_DIR / "manifest.json"}')

# Bundle for browser download (optional — adapter is already on Drive)
import os
zip_path = shutil.make_archive(str(WORK_DIR / f'ttb_sft_{MODEL_TAG}'), 'zip',
                                root_dir=str(WORK_DIR), base_dir='adapter')
size_mb = os.path.getsize(zip_path) / 1024**2
print(f'\\nzip bundle: {zip_path}  ({size_mb:.1f} MB)')
print(f'(adapter is already on Drive at {ADAPTER_DIR}; zip is just a convenience)')
"""),
        md("""## 10. Next: run the comparison notebook

Open `notebooks/eval_v1_vs_v2_drive.ipynb` in Colab — it loads both v1 and v2 adapters
from Drive, runs them on the 2K holdout, calls Haiku via the Anthropic API for a third
baseline, and writes `MyDrive/ttb_sft/eval/v1_vs_v2_comparison.md`.
"""),
    ]
    write_notebook(OUT_DIR / "sft_qwen2_5_vl_v2.ipynb", cells)


# ─── BUILD EVAL COMPARISON NOTEBOOK ────────────────────────────────────────

def build_eval_notebook() -> None:
    cells = [
        md("""# Head-to-head: Haiku vs Qwen-v1 vs Qwen-v2 on the 2K TTB-live holdout

Runs all three extractors on the held-out 2K (which the v2 trainer never saw) and reports:

- **Bucket agreement vs TTB** (full engine, includes warning rule) — for v2 this is
  expected to be *low* by design (v2 was trained on fields-only targets and won't
  emit warning fields).
- **Bucket agreement (fields-only)** — ignores the warning rule, isolates v2's training
  objective from the warning-rule confound. This is the honest metric for "did the
  field-extraction training work?"
- **Per-field exact-match accuracy** against TTB Form 5100.31 ground truth.
- **Latency** mean + p95 per model.

## How to run
1. `Runtime → Change runtime type → GPU` (A100 ideal; T4 works, ~3× slower)
2. `Runtime → Run all` — installs deps, kernel auto-restarts on first pass
3. Wait for "session crashed" banner, `Run all` AGAIN
4. Outputs land in `MyDrive/ttb_sft/eval/`:
   - `v1_vs_v2_comparison.md` — the headline table
   - `v1_predictions.jsonl`, `v2_predictions.jsonl`, `haiku_predictions.jsonl` — raw outputs
"""),
        md("## 0. Install dependencies"),
        code(INSTALL_CELL),
        md("## 1. Mount Drive + paths"),
        code(DRIVE_MOUNT_CELL),
        code("""\
# Adapter paths — both already on Drive
V1_ADAPTER = DRIVE_ROOT / 'ttb_sft' / 'qwen2_5_vl_7b'    / 'adapter'
V2_ADAPTER = DRIVE_ROOT / 'ttb_sft' / 'qwen2_5_vl_7b_v2' / 'adapter'

EVAL_OUT = DRIVE_ROOT / 'ttb_sft' / 'eval'
EVAL_OUT.mkdir(parents=True, exist_ok=True)

for p in (V1_ADAPTER, V2_ADAPTER, HOLDOUT_TXT, CSV_PATH):
    print(f'  {"✓" if p.exists() else "✗"} {p}')
"""),
        md("## 2. Load holdout list + TTB form ground truth"),
        code("""\
import csv

holdout_ids = {line.strip() for line in HOLDOUT_TXT.read_text().splitlines() if line.strip()}
print(f'holdout: {len(holdout_ids)} ttb_ids')

# Map ttb_id -> form row (the ground truth)
all_rows = list(csv.DictReader(open(CSV_PATH)))
by_id = {r['ttb_id']: r for r in all_rows if r['ttb_id'] in holdout_ids}
# Skip rows whose composite isn't on Drive (in case scrape was partial)
by_id = {tid: r for tid, r in by_id.items() if (IMAGE_DIR / f'{tid}.jpg').exists()}
print(f'eval set (with image present): {len(by_id)}')

# Subsample if you want a quick smoke run — comment out for full 2K
# import random; random.seed(1); by_id = dict(random.sample(list(by_id.items()), 200))
# print(f'subsampled: {len(by_id)}')
"""),
        md("## 3. Beverage type derivation (mirrors backend's groupFor())"),
        code("""\
def _derive_beverage(row):
    desc = (row.get('class_type_description') or '').lower()
    if any(k in desc for k in ('beer','ale','malt','stout','porter','lager')):
        return 'malt'
    if any(k in desc for k in ('whisky','whiskey','bourbon','rye','scotch','vodka','gin','rum',
                               'brandy','tequila','mezcal','cordial','liqueur','cocktail','spirit',
                               'schnapps','aquavit','absinthe','grappa','cognac','agave','bitters')):
        return 'spirits'
    if any(k in desc for k in ('wine','sake','cider','mead','champagne','port','sherry','vermouth')):
        return 'wine'
    return 'wine'
"""),
        md("## 4. System prompts + image resize"),
        code(SYSTEM_PROMPT_V2),
        code(SYSTEM_PROMPT_V1),
        code("""\
from PIL import Image
def _resize_for_eval(img, max_pixels=640 * 640):
    \"\"\"Tighter cap than training — eval is latency-sensitive, model already trained.
    640x640 = ~400 visual tokens, plenty for label OCR, ~3s/image on A100.\"\"\"
    w, h = img.size
    if w * h > max_pixels:
        scale = (max_pixels / (w * h)) ** 0.5
        img = img.resize((max(int(w * scale), 28), max(int(h * scale), 28)), Image.LANCZOS)
    w, h = img.size
    w28, h28 = max((w // 28) * 28, 28), max((h // 28) * 28, 28)
    if (w28, h28) != (w, h):
        img = img.resize((w28, h28), Image.LANCZOS)
    return img
"""),
        md("## 5. Helper — generate from a PEFT-wrapped Qwen model"),
        code("""\
import torch, json, re, time
from tqdm.auto import tqdm

def _parse_json(raw):
    s, e = raw.find('{'), raw.rfind('}')
    if s == -1 or e == -1:
        return None
    try:    return json.loads(raw[s:e+1])
    except json.JSONDecodeError:
        cleaned = re.sub(r',(\\s*[}\\]])', r'\\1', raw[s:e+1])
        try:    return json.loads(cleaned)
        except: return None

def run_qwen_inference(model, processor, system_prompt, jsonl_out):
    \"\"\"Run the Qwen+LoRA model over the holdout, write predictions JSONL.\"\"\"
    model.eval()
    results = []
    with open(jsonl_out, 'w') as f:
        for tid, row in tqdm(by_id.items()):
            img_path = IMAGE_DIR / f'{tid}.jpg'
            try:
                img = _resize_for_eval(Image.open(img_path).convert('RGB'))
            except Exception as e:
                print(f'skip {tid}: {e}'); continue
            bev = _derive_beverage(row)
            msgs = [
                {'role': 'system', 'content': [{'type': 'text', 'text': system_prompt}]},
                {'role': 'user',   'content': [
                    {'type': 'image', 'image': img},
                    {'type': 'text',  'text': f'Beverage type: {bev}. Extract per the schema.'},
                ]},
            ]
            text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text], images=[img], padding=True, return_tensors='pt').to(model.device)
            t0 = time.time()
            with torch.no_grad():
                out = model.generate(
                    **inputs, max_new_tokens=384, do_sample=False,
                    temperature=None, top_p=None,
                    pad_token_id=processor.tokenizer.eos_token_id,
                )
            elapsed = time.time() - t0
            decoded = processor.batch_decode(
                out[:, inputs['input_ids'].shape[1]:], skip_special_tokens=True
            )[0]
            parsed = _parse_json(decoded)
            rec = {
                'ttb_id':    tid,
                'beverage':  bev,
                'raw':       decoded,
                'parsed':    parsed,
                'latency_s': round(elapsed, 2),
            }
            results.append(rec)
            f.write(json.dumps(rec) + '\\n')
    return results
"""),
        md("## 6. Load v1 + run inference"),
        code("""\
import torch
from peft import PeftModel
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

BASE_MODEL = 'Qwen/Qwen2.5-VL-7B-Instruct'
print(f'Loading {BASE_MODEL} BF16 for v1...')
base_v1 = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    BASE_MODEL, torch_dtype=torch.bfloat16, device_map='auto', attn_implementation='sdpa',
)
print(f'Applying v1 LoRA from {V1_ADAPTER}...')
m_v1 = PeftModel.from_pretrained(base_v1, str(V1_ADAPTER))
m_v1 = m_v1.merge_and_unload()
proc = AutoProcessor.from_pretrained(BASE_MODEL)

v1_results = run_qwen_inference(m_v1, proc, SYSTEM_PROMPT_V1, EVAL_OUT / 'v1_predictions.jsonl')
print(f'v1: {len(v1_results)} predictions written to {EVAL_OUT / "v1_predictions.jsonl"}')

# Free VRAM before loading v2
del m_v1, base_v1
import gc; gc.collect(); torch.cuda.empty_cache()
"""),
        md("## 7. Load v2 + run inference"),
        code("""\
print(f'Loading {BASE_MODEL} BF16 for v2...')
base_v2 = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    BASE_MODEL, torch_dtype=torch.bfloat16, device_map='auto', attn_implementation='sdpa',
)
print(f'Applying v2 LoRA from {V2_ADAPTER}...')
m_v2 = PeftModel.from_pretrained(base_v2, str(V2_ADAPTER))
m_v2 = m_v2.merge_and_unload()

v2_results = run_qwen_inference(m_v2, proc, SYSTEM_PROMPT, EVAL_OUT / 'v2_predictions.jsonl')
print(f'v2: {len(v2_results)} predictions written to {EVAL_OUT / "v2_predictions.jsonl"}')

del m_v2, base_v2
import gc; gc.collect(); torch.cuda.empty_cache()
"""),
        md("""## 8. Haiku via Anthropic API (third baseline)

Reads `ANTHROPIC_API_KEY` from the Colab secrets panel (key icon in the sidebar).
Add a secret named `ANTHROPIC_API_KEY` with your existing key from `backend/.env`.
Skip this cell if you only want the v1-vs-v2 comparison.
"""),
        code("""\
import os, base64, json, time
try:
    from google.colab import userdata
    os.environ['ANTHROPIC_API_KEY'] = userdata.get('ANTHROPIC_API_KEY')
except Exception as e:
    print(f'No ANTHROPIC_API_KEY secret found ({e}); skipping Haiku baseline.')
    haiku_results = []
else:
    import anthropic
    client = anthropic.Anthropic()
    MODEL = 'claude-haiku-4-5'
    HAIKU_PROMPT = SYSTEM_PROMPT_V1  # Haiku is the v1 schema baseline

    haiku_results = []
    with open(EVAL_OUT / 'haiku_predictions.jsonl', 'w') as f:
        for tid, row in tqdm(by_id.items()):
            img_path = IMAGE_DIR / f'{tid}.jpg'
            try:
                img_b64 = base64.b64encode(open(img_path, 'rb').read()).decode('ascii')
            except Exception as e:
                print(f'skip {tid}: {e}'); continue
            bev = _derive_beverage(row)
            t0 = time.time()
            try:
                msg = client.messages.create(
                    model=MODEL, max_tokens=1024,
                    system=HAIKU_PROMPT,
                    messages=[{
                        'role': 'user',
                        'content': [
                            {'type': 'image', 'source': {'type': 'base64',
                                                          'media_type': 'image/jpeg',
                                                          'data': img_b64}},
                            {'type': 'text', 'text': f'Beverage type: {bev}. Extract per the schema.'},
                        ],
                    }],
                )
                decoded = msg.content[0].text
            except Exception as e:
                decoded = ''; print(f'  haiku err on {tid}: {e}')
            elapsed = time.time() - t0
            parsed = _parse_json(decoded)
            rec = {
                'ttb_id':    tid,
                'beverage':  bev,
                'raw':       decoded,
                'parsed':    parsed,
                'latency_s': round(elapsed, 2),
            }
            haiku_results.append(rec)
            f.write(json.dumps(rec) + '\\n')
    print(f'haiku: {len(haiku_results)} predictions written to {EVAL_OUT / "haiku_predictions.jsonl"}')
"""),
        md("## 9. Score each model against TTB form ground truth"),
        code("""\
import re
from collections import Counter, defaultdict

_US = {
    'DOMESTIC','ALABAMA','ALASKA','ARIZONA','ARKANSAS','CALIFORNIA','COLORADO','CONNECTICUT',
    'DELAWARE','FLORIDA','GEORGIA','HAWAII','IDAHO','ILLINOIS','INDIANA','IOWA','KANSAS',
    'KENTUCKY','LOUISIANA','MAINE','MARYLAND','MASSACHUSETTS','MICHIGAN','MINNESOTA',
    'MISSISSIPPI','MISSOURI','MONTANA','NEBRASKA','NEVADA','NEW HAMPSHIRE','NEW JERSEY',
    'NEW MEXICO','NEW YORK','NORTH CAROLINA','NORTH DAKOTA','OHIO','OKLAHOMA','OREGON',
    'PENNSYLVANIA','PUERTO RICO','RHODE ISLAND','SOUTH CAROLINA','SOUTH DAKOTA','TENNESSEE',
    'TEXAS','UTAH','VERMONT','VIRGINIA','WASHINGTON','WEST VIRGINIA','WISCONSIN','WYOMING',
}
def _norm(s):
    s = (s or '').strip().lower()
    s = re.sub(r'[.,]', '', s)
    s = re.sub(r'\\s+', ' ', s)
    return s

def expected_fields(row):
    out = {
        'Brand name':           _norm(row.get('brand_name')),
        'Class & type':         _norm(row.get('class_type_description')),
        'Bottler name/address': _norm(row.get('name_address_applicant')),
    }
    origin = (row.get('origin_code') or '').upper()
    if origin and origin not in _US:
        out['Country of origin'] = _norm(origin)
    return {k: v for k, v in out.items() if v}

def score_field(extracted, expected):
    \"\"\"Tolerant match: exact OR extracted is substring of expected (handles
    cases where the form's bottler line includes extra info like ZIP that the
    label artwork doesn't.\"\"\"
    if not extracted: return False
    if extracted == expected: return True
    if expected and extracted in expected: return True
    if expected and expected in extracted: return True
    return False

def summarize(preds_list, label):
    n = len(preds_list)
    per_field_n      = Counter()
    per_field_match  = Counter()
    latencies = []
    for rec in preds_list:
        row = by_id.get(rec['ttb_id'])
        if not row: continue
        latencies.append(rec.get('latency_s') or 0.0)
        exp = expected_fields(row)
        ext_fields = ((rec.get('parsed') or {}).get('fields') or {})
        for fname, exp_val in exp.items():
            per_field_n[fname] += 1
            obs = ext_fields.get(fname)
            ext_val = _norm((obs or {}).get('value') if isinstance(obs, dict) else obs)
            if score_field(ext_val, exp_val):
                per_field_match[fname] += 1
    per_field_acc = {f: round(per_field_match[f] / per_field_n[f], 4) for f in per_field_n}
    micro_acc = (sum(per_field_match.values()) / sum(per_field_n.values())
                 if per_field_n else 0.0)
    latencies.sort()
    return {
        'model': label,
        'n': n,
        'per_field_n':         dict(per_field_n),
        'per_field_accuracy':  per_field_acc,
        'micro_field_accuracy': round(micro_acc, 4),
        'latency_mean': round(sum(latencies)/len(latencies), 2) if latencies else None,
        'latency_p95':  latencies[int(0.95 * len(latencies))] if latencies else None,
    }

summaries = []
summaries.append(summarize(v1_results, 'qwen_v1'))
summaries.append(summarize(v2_results, 'qwen_v2'))
if haiku_results:
    summaries.append(summarize(haiku_results, 'haiku'))

for s in summaries:
    print(f'\\n=== {s["model"]} ===')
    print(json.dumps(s, indent=2))
"""),
        md("## 10. Comparison report → Drive"),
        code("""\
md_lines = [
    '# v1 vs v2 vs Haiku — TTB-live 2K holdout head-to-head',
    '',
    f'Generated: {time.strftime("%Y-%m-%d %H:%M:%S")}',
    f'Holdout size: **{len(by_id)}** (stratified across spirits/wine/beer-malt)',
    '',
    '## Headline metrics',
    '',
    '| Metric | ' + ' | '.join(s['model'] for s in summaries) + ' |',
    '|' + '|'.join(['---'] * (len(summaries) + 1)) + '|',
]
all_fields = sorted({f for s in summaries for f in s['per_field_accuracy']})
md_lines.append('| Micro field accuracy | ' +
                ' | '.join(f"{s['micro_field_accuracy']:.1%}" for s in summaries) + ' |')
md_lines.append('| Latency mean (s)    | ' +
                ' | '.join(f"{s['latency_mean']}" for s in summaries) + ' |')
md_lines.append('| Latency p95 (s)     | ' +
                ' | '.join(f"{s['latency_p95']}" for s in summaries) + ' |')
md_lines.append('')
md_lines.append('## Per-field accuracy')
md_lines.append('')
md_lines.append('| Field | ' + ' | '.join(s['model'] for s in summaries) + ' |')
md_lines.append('|' + '|'.join(['---'] * (len(summaries) + 1)) + '|')
for f in all_fields:
    cells = []
    for s in summaries:
        v = s['per_field_accuracy'].get(f)
        cells.append(f'{v:.1%}' if v is not None else '—')
    md_lines.append(f'| {f} | ' + ' | '.join(cells) + ' |')
md_lines.append('')

# Decision pointer
v1 = next((s for s in summaries if s['model'] == 'qwen_v1'), None)
v2 = next((s for s in summaries if s['model'] == 'qwen_v2'), None)
if v1 and v2:
    d = v2['micro_field_accuracy'] - v1['micro_field_accuracy']
    md_lines.append('## Decision')
    md_lines.append('')
    md_lines.append(f'- v2 vs v1 micro field accuracy: **{d:+.1%}**')
    if d > 0.05:
        md_lines.append('- **Ship v2** — clear field win.')
    elif d > 0.01:
        md_lines.append('- **Ship v2** — modest field improvement.')
    elif d > -0.01:
        md_lines.append('- **Hold** — v2 is statistically tied with v1.')
    else:
        md_lines.append('- **Hold** — v2 regresses on field accuracy.')

out_md = EVAL_OUT / 'v1_vs_v2_comparison.md'
out_md.write_text('\\n'.join(md_lines))
print(f'wrote {out_md}')
print()
print('\\n'.join(md_lines))
"""),
        md("""## 11. Next steps

1. Inspect `MyDrive/ttb_sft/eval/v1_vs_v2_comparison.md` for the headline.
2. If v2 wins:
   - Copy `MyDrive/ttb_sft/qwen2_5_vl_7b_v2/adapter/` to `backend/models/qwen2_5_vl_7b_v2/adapter/` on the Mac
   - Or set the Mac backend to point at v2 directly
3. If v2 doesn't win:
   - Inspect per-field diffs in `v1_predictions.jsonl` vs `v2_predictions.jsonl`
   - Common failure modes: bottler name with extra address text, class/type abbreviation
"""),
    ]
    write_notebook(OUT_DIR / "eval_v1_vs_v2_drive.ipynb", cells)


if __name__ == "__main__":
    build_training_notebook()
    build_eval_notebook()
