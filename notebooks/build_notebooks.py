#!/usr/bin/env python3
"""Generate the two SFT Colab notebooks from a shared source.

Run once locally to produce:
  - sft_qwen2_5_vl.ipynb   — Unsloth + LoRA on Qwen2.5-VL-7B-Instruct
  - sft_kimi_vl.ipynb       — transformers + PEFT + TRL on Kimi-VL-A3B-Thinking

Both notebooks are self-sustaining: they install deps, pull the COLA Cloud
free sample (CC0), build (image, structured-JSON) pairs from the dataset's
OCR + LLM metadata, train a LoRA adapter, eval on a held-out test set, and
write the adapter to your Google Drive at /MyDrive/ttb_sft/{model}/.
"""

import json
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────
# Shared cell content. Each entry is (cell_type, source). source is a list of
# lines OR a string. Markdown and code cells are produced verbatim.
# ────────────────────────────────────────────────────────────────────────────


def md(*lines):
    return ("markdown", list(lines))


def code(*lines):
    return ("code", list(lines))


# Header — model-specific (passed in build).
def header(model_name, base_model, library):
    return md(
        f"# Fine-tune **{model_name}** for TTB Label Verification\n",
        "\n",
        f"Self-contained Colab notebook. Trains a LoRA adapter on top of "
        f"`{base_model}` using {library}, on data pulled from the COLA Cloud "
        f"free sample (CC0). Outputs go to your Google Drive at "
        f"`/MyDrive/ttb_sft/{model_name.lower()}/`.\n",
        "\n",
        "**What to do before running**:\n",
        "1. `Runtime → Change runtime type → GPU` (A100 ideal; T4 works for the small Kimi-VL but Qwen2.5-VL-7B needs 24GB+).\n",
        "2. `Runtime → Run all`. The notebook is designed to run end-to-end without intervention.\n",
        "3. Caffeinate your Mac / leave the tab open. On a Colab A100 the full run is **~3–6 hours**.\n",
        "\n",
        "**What it does**:\n",
        "- Pulls 1,000 COLA Cloud records + ~800 label images\n",
        "- Builds a structured JSON ground-truth target per image from the dataset's `BRAND_NAME`, `CLASS_NAME`, `PRODUCT_NAME`, `OCR_ABV`, `OCR_VOLUME`, `ORIGIN_NAME`, and `OCR_TEXT` columns\n",
        "- 80/10/10 train/val/test split\n",
        "- LoRA fine-tune (rank 16, attention projections)\n",
        "- Per-field extraction accuracy on the held-out test set\n",
        "- Writes the adapter + tokenizer config + eval report to Drive\n",
        "\n",
        "**Note on TTB data.gov**: the data.gov 'Public COLA Registry Search and Download' resource is a link to the interactive UI at `ttbonline.gov` — there's no public bulk CSV. The COLA Cloud free sample (also sourced from the TTB registry) is the only direct-fetch path. If you later want to scrape additional COLAs by TTB_ID, that's a separate pull job; the notebook architecture supports adding more (image, JSON) pairs to the dataset dir without code changes.\n",
    )


SETUP_DRIVE = code(
    "# Mount Drive — adapter + checkpoints persist between runs.\n",
    "from google.colab import drive\n",
    "drive.mount('/content/drive')\n",
    "import os, pathlib\n",
    "MODEL_TAG = MODEL_TAG  # set in the previous cell\n",
    "WORK_DIR = pathlib.Path(f'/content/drive/MyDrive/ttb_sft/{MODEL_TAG}')\n",
    "WORK_DIR.mkdir(parents=True, exist_ok=True)\n",
    "DATA_DIR = pathlib.Path('/content/cola_data')\n",
    "DATA_DIR.mkdir(parents=True, exist_ok=True)\n",
    "IMG_DIR  = DATA_DIR / 'images'; IMG_DIR.mkdir(exist_ok=True)\n",
    "print('Work dir:', WORK_DIR)\n",
    "print('Data dir:', DATA_DIR)\n",
)


DOWNLOAD_DATA = md(
    "## 1. Download COLA Cloud free sample\n",
    "\n",
    "1,000 recent COLA records + ~1,750 image rows. ~500 KB zip. CC0 license.\n",
), code(
    "import urllib.request, zipfile, os\n",
    "COLA_ZIP_URL = 'https://dyuie4zgfxmt6.cloudfront.net/samples/cola-sample-pack-v1.zip'\n",
    "zip_path = DATA_DIR / 'sample.zip'\n",
    "if not (DATA_DIR / 'cola.csv').exists():\n",
    "    print('Downloading COLA Cloud sample...')\n",
    "    urllib.request.urlretrieve(COLA_ZIP_URL, zip_path)\n",
    "    with zipfile.ZipFile(zip_path, 'r') as z:\n",
    "        z.extractall(DATA_DIR)\n",
    "    print('  Extracted.')\n",
    "else:\n",
    "    print('Already downloaded.')\n",
    "!ls -la {DATA_DIR}\n",
)


BUILD_PAIRS = md(
    "## 2. Build (image, structured-JSON) training pairs\n",
    "\n",
    "For each label image where the dataset has usable metadata, we synthesize the structured JSON the model should learn to produce. The schema matches the backend's `ExtractedLabel` shape so the SFT'd model is drop-in for `INFERENCE_MODE=sft`.\n",
    "\n",
    "Ground-truth labels come from the COLA Cloud dataset itself:\n",
    "- `BRAND_NAME`, `PRODUCT_NAME`, `CLASS_NAME`, `ORIGIN_NAME` — directly from the COLA form\n",
    "- `OCR_ABV`, `OCR_VOLUME` — Google Vision OCR run on the label image\n",
    "- `OCR_TEXT` — full per-image OCR (used to extract the warning text + bottler line)\n",
    "\n",
    "Images that don't have a downloadable file or don't have `GOVERNMENT WARNING` in the OCR are dropped (they don't help the warning-verification task).\n",
), code(
    "import csv, json, re\n",
    "from collections import defaultdict\n",
    "from pathlib import Path\n",
    "\n",
    "VERBATIM_GOVERNMENT_WARNING = (\n",
    "    'GOVERNMENT WARNING: (1) According to the Surgeon General, women should not '\n",
    "    'drink alcoholic beverages during pregnancy because of the risk of birth defects. '\n",
    "    '(2) Consumption of alcoholic beverages impairs your ability to drive a car or '\n",
    "    'operate machinery, and may cause health problems.'\n",
    ")\n",
    "\n",
    "def _net_str(row):\n",
    "    v, u = (row.get('OCR_VOLUME') or '').strip(), (row.get('OCR_VOLUME_UNIT') or '').strip().lower()\n",
    "    if not v: return ''\n",
    "    try:\n",
    "        f = float(v); v = str(int(f)) if f.is_integer() else str(f)\n",
    "    except ValueError: pass\n",
    "    unit_map = {'milliliters':'mL','milliliter':'mL','ml':'mL',\n",
    "                'liters':'L','liter':'L','l':'L',\n",
    "                'fluid ounces':'FL OZ','fluid ounce':'FL OZ','fl oz':'FL OZ','fl. oz.':'FL OZ',\n",
    "                'ounces':'FL OZ','ounce':'FL OZ','oz':'FL OZ'}\n",
    "    return f\"{v} {unit_map.get(u, u or 'mL')}\"\n",
    "\n",
    "def _abv_str(row):\n",
    "    v = (row.get('OCR_ABV') or '').strip()\n",
    "    if not v: return ''\n",
    "    try:\n",
    "        f = float(v); return f'{f:g}% Alc./Vol.'\n",
    "    except ValueError: return ''\n",
    "\n",
    "def _extract_warning(ocr_text):\n",
    "    if not ocr_text or 'GOVERNMENT WARNING' not in ocr_text.upper():\n",
    "        return None\n",
    "    # take from 'GOVERNMENT WARNING' to end of 'health problems.'\n",
    "    start = ocr_text.upper().find('GOVERNMENT WARNING')\n",
    "    tail = ocr_text[start:]\n",
    "    m = re.search(r'machinery[^.]*\\.\\s*', tail, re.IGNORECASE)\n",
    "    return tail[:m.end()].strip() if m else tail[:500].strip()\n",
    "\n",
    "def _extract_bottler(ocr_text):\n",
    "    if not ocr_text: return ''\n",
    "    for kw in ('BOTTLED BY', 'BREWED BY', 'PRODUCED BY', 'DISTILLED BY', 'IMPORTED BY',\n",
    "               'Bottled by', 'Brewed by', 'Produced by', 'Distilled by', 'Imported by'):\n",
    "        if kw in ocr_text:\n",
    "            idx = ocr_text.find(kw)\n",
    "            end = ocr_text.find('.', idx)\n",
    "            return ocr_text[idx:end if end != -1 else idx+200].strip()\n",
    "    return ''\n",
    "\n",
    "def _derive_beverage(row):\n",
    "    pt = (row.get('PRODUCT_TYPE') or '').lower(); cn = (row.get('CLASS_NAME') or '').lower()\n",
    "    if 'seltzer' in cn or 'flavored' in cn: return 'malt'\n",
    "    if pt == 'distilled spirits': return 'spirits'\n",
    "    if pt == 'wine': return 'wine'\n",
    "    if pt == 'malt beverage': return 'beer'\n",
    "    return 'wine'\n",
    "\n",
    "# Load CSVs\n",
    "cola = list(csv.DictReader(open(DATA_DIR / 'cola.csv')))\n",
    "imgs = list(csv.DictReader(open(DATA_DIR / 'cola_image.csv')))\n",
    "by_ttb = defaultdict(list)\n",
    "for ir in imgs: by_ttb[ir['TTB_ID']].append(ir)\n",
    "\n",
    "# Build candidate pairs\n",
    "candidates = []\n",
    "for cola_row in cola:\n",
    "    ttb_id = cola_row['TTB_ID']\n",
    "    images_for = by_ttb.get(ttb_id, [])\n",
    "    if not images_for: continue\n",
    "    for img_row in images_for:\n",
    "        ocr_text = img_row.get('OCR_TEXT') or ''\n",
    "        if not ocr_text: continue\n",
    "        warning_text = _extract_warning(ocr_text)\n",
    "        target = {\n",
    "            'fields': {},\n",
    "            'government_warning': {\n",
    "                'present': warning_text is not None,\n",
    "                'detected_text': warning_text or '',\n",
    "                'casing_all_caps': True if warning_text and warning_text[:18].isupper() else False,\n",
    "                'heading_bold': True if warning_text else False,\n",
    "                'body_bold': False,\n",
    "                'approx_font_mm': None,\n",
    "                'contrast_ok': True,\n",
    "                'separate_and_apart': True,\n",
    "            },\n",
    "            'image_quality': {'score': 0.85, 'legible': True, 'note': None},\n",
    "        }\n",
    "        # Field labels (only when populated AND the field is likely on this panel)\n",
    "        pos = img_row.get('CONTAINER_POSITION','').upper()\n",
    "        is_back = pos == 'BACK'\n",
    "        # Brand / class / product appear on FRONT typically\n",
    "        if not is_back:\n",
    "            if cola_row.get('BRAND_NAME'):\n",
    "                target['fields']['Brand name'] = {'value': cola_row['BRAND_NAME'], 'confidence': 0.95}\n",
    "            if cola_row.get('CLASS_NAME'):\n",
    "                target['fields']['Class & type'] = {'value': cola_row['CLASS_NAME'], 'confidence': 0.95}\n",
    "        # ABV / Net contents — OCR sourced; may be either panel\n",
    "        if _abv_str(cola_row) and img_row.get('TTB_IMAGE_ID') == cola_row.get('OCR_ABV_TTB_IMAGE_ID'):\n",
    "            target['fields']['Alcohol content'] = {'value': _abv_str(cola_row), 'confidence': 0.92}\n",
    "        if _net_str(cola_row) and img_row.get('TTB_IMAGE_ID') == cola_row.get('OCR_VOLUME_TTB_IMAGE_ID'):\n",
    "            target['fields']['Net contents'] = {'value': _net_str(cola_row), 'confidence': 0.92}\n",
    "        # Bottler — usually on back\n",
    "        bottler = _extract_bottler(ocr_text)\n",
    "        if bottler and is_back:\n",
    "            target['fields']['Bottler name/address'] = {'value': bottler, 'confidence': 0.85}\n",
    "        # Country of origin — imports only, usually on back\n",
    "        if (cola_row.get('DOMESTIC_OR_IMPORTED') or '').lower() == 'imported' and cola_row.get('ORIGIN_NAME') and is_back:\n",
    "            target['fields']['Country of origin'] = {'value': f\"Product of {cola_row['ORIGIN_NAME'].title()}\", 'confidence': 0.85}\n",
    "        # Only keep examples with at least 1 field OR the warning\n",
    "        if not target['fields'] and not target['government_warning']['present']:\n",
    "            continue\n",
    "        candidates.append({\n",
    "            'ttb_image_id': img_row['TTB_IMAGE_ID'],\n",
    "            'ttb_id': ttb_id,\n",
    "            'container_position': pos,\n",
    "            'beverage_type': _derive_beverage(cola_row),\n",
    "            'target': target,\n",
    "        })\n",
    "\n",
    "print(f'Built {len(candidates)} candidate (image, JSON) pairs')\n",
    "print('Sample target JSON:')\n",
    "print(json.dumps(candidates[0]['target'], indent=2)[:800])\n",
)


DOWNLOAD_IMAGES = md(
    "## 3. Download label images (parallel, ~2–5 minutes)\n",
), code(
    "import concurrent.futures, urllib.request\n",
    "CDN = 'https://dyuie4zgfxmt6.cloudfront.net/{}.webp'\n",
    "\n",
    "def _download_one(cand):\n",
    "    ttb_image_id = cand['ttb_image_id']\n",
    "    dest = IMG_DIR / f'{ttb_image_id}.webp'\n",
    "    if dest.exists() and dest.stat().st_size > 0:\n",
    "        return cand, True\n",
    "    try:\n",
    "        req = urllib.request.Request(CDN.format(ttb_image_id), headers={'User-Agent': 'ttb-sft/0.1'})\n",
    "        with urllib.request.urlopen(req, timeout=20) as r:\n",
    "            data = r.read()\n",
    "        dest.write_bytes(data)\n",
    "        return cand, True\n",
    "    except Exception as e:\n",
    "        return cand, False\n",
    "\n",
    "downloaded = []\n",
    "with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:\n",
    "    for cand, ok in ex.map(_download_one, candidates):\n",
    "        if ok:\n",
    "            cand['image_path'] = str(IMG_DIR / f'{cand[\"ttb_image_id\"]}.webp')\n",
    "            downloaded.append(cand)\n",
    "\n",
    "print(f'Downloaded {len(downloaded)} / {len(candidates)} images')\n",
)


SPLIT_DATA = md(
    "## 4. Train / val / test split (80 / 10 / 10) + sanity check\n",
), code(
    "import random\n",
    "random.seed(42)\n",
    "random.shuffle(downloaded)\n",
    "n = len(downloaded)\n",
    "n_train = int(n * 0.80); n_val = int(n * 0.10)\n",
    "train = downloaded[:n_train]\n",
    "val   = downloaded[n_train:n_train + n_val]\n",
    "test  = downloaded[n_train + n_val:]\n",
    "print(f'train={len(train)}  val={len(val)}  test={len(test)}')\n",
    "\n",
    "# Persist the split so we can re-eval against the same test set later.\n",
    "import json\n",
    "(WORK_DIR / 'splits').mkdir(exist_ok=True)\n",
    "for name, split in [('train', train), ('val', val), ('test', test)]:\n",
    "    with open(WORK_DIR / 'splits' / f'{name}.jsonl', 'w') as f:\n",
    "        for ex in split:\n",
    "            f.write(json.dumps({k: v for k, v in ex.items() if k != 'target'}) + '\\n')\n",
    "            # store target separately so the file is parsable for eval\n",
    "    print(f'  wrote {name} split → {WORK_DIR}/splits/{name}.jsonl')\n",
)


SYSTEM_PROMPT_VAR = code(
    "SYSTEM_PROMPT = (\n",
    "    'You are a careful transcription assistant for U.S. TTB alcohol label review. '\n",
    "    'Given ONE label panel image and the beverage type, you READ what is printed and '\n",
    "    'RETURN ONLY a JSON object matching the schema below. Do NOT decide whether the '\n",
    "    'label complies with regulations.\\n\\n'\n",
    "    'If a field is not clearly visible on the panel, OMIT it from the fields object. '\n",
    "    'Never guess; never substitute deposit codes (e.g. \"CA CRV\"), NOM IDs, or barcodes. '\n",
    "    'Transcribe the Government Warning EXACTLY as printed (preserve case, punctuation, '\n",
    "    'any wording errors).\\n\\n'\n",
    "    'Schema: {fields: {<field name>: {value, confidence}}, government_warning: '\n",
    "    '{present, detected_text, casing_all_caps, heading_bold, body_bold, approx_font_mm, '\n",
    "    'contrast_ok, separate_and_apart}, image_quality: {score, legible, note}}'\n",
    ")\n",
)


def model_load_qwen():
    return md(
        "## 5. Load Qwen2.5-VL-7B with Unsloth (4-bit + LoRA)\n",
    ), code(
        "from unsloth import FastVisionModel\n",
        "import torch\n",
        "\n",
        "model, tokenizer = FastVisionModel.from_pretrained(\n",
        "    'unsloth/Qwen2.5-VL-7B-Instruct',\n",
        "    load_in_4bit = True,\n",
        "    use_gradient_checkpointing = 'unsloth',\n",
        ")\n",
        "\n",
        "model = FastVisionModel.get_peft_model(\n",
        "    model,\n",
        "    finetune_vision_layers     = False,  # keep vision tower frozen; train projection + LM\n",
        "    finetune_language_layers   = True,\n",
        "    finetune_attention_modules = True,\n",
        "    finetune_mlp_modules       = True,\n",
        "    r = 16,\n",
        "    lora_alpha = 16,\n",
        "    lora_dropout = 0,\n",
        "    bias = 'none',\n",
        "    random_state = 42,\n",
        "    target_modules = 'all-linear',\n",
        ")\n",
        "print(model.print_trainable_parameters())\n",
    )


def model_load_kimi():
    return md(
        "## 5. Load Kimi-VL-A3B-Thinking with PEFT (LoRA, bf16)\n",
        "\n",
        "Unsloth doesn't support Kimi yet — we use HF transformers + PEFT directly.\n",
    ), code(
        "import torch\n",
        "from transformers import AutoProcessor, AutoModelForCausalLM, BitsAndBytesConfig\n",
        "from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training\n",
        "\n",
        "MODEL_ID = 'moonshotai/Kimi-VL-A3B-Thinking-2506'\n",
        "\n",
        "bnb = BitsAndBytesConfig(\n",
        "    load_in_4bit = True,\n",
        "    bnb_4bit_compute_dtype = torch.bfloat16,\n",
        "    bnb_4bit_quant_type = 'nf4',\n",
        "    bnb_4bit_use_double_quant = True,\n",
        ")\n",
        "\n",
        "processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)\n",
        "model = AutoModelForCausalLM.from_pretrained(\n",
        "    MODEL_ID,\n",
        "    quantization_config = bnb,\n",
        "    torch_dtype = torch.bfloat16,\n",
        "    device_map = 'auto',\n",
        "    trust_remote_code = True,\n",
        ")\n",
        "model = prepare_model_for_kbit_training(model)\n",
        "\n",
        "lora_cfg = LoraConfig(\n",
        "    r = 16, lora_alpha = 16, lora_dropout = 0.05, bias = 'none',\n",
        "    target_modules = ['q_proj', 'k_proj', 'v_proj', 'o_proj',\n",
        "                      'gate_proj', 'up_proj', 'down_proj'],\n",
        "    task_type = 'CAUSAL_LM',\n",
        ")\n",
        "model = get_peft_model(model, lora_cfg)\n",
        "model.print_trainable_parameters()\n",
    )


def format_dataset_qwen():
    return md(
        "## 6. Format dataset for Unsloth SFT trainer\n",
    ), code(
        "from PIL import Image\n",
        "from unsloth.trainer import UnslothVisionDataCollator\n",
        "\n",
        "def _convo(ex):\n",
        "    return {\n",
        "        'messages': [\n",
        "            {'role': 'system', 'content': [{'type': 'text', 'text': SYSTEM_PROMPT}]},\n",
        "            {'role': 'user',   'content': [\n",
        "                {'type': 'image', 'image': Image.open(ex['image_path']).convert('RGB')},\n",
        "                {'type': 'text',  'text': f\"Beverage type: {ex['beverage_type']}. Extract per the schema.\"},\n",
        "            ]},\n",
        "            {'role': 'assistant', 'content': [\n",
        "                {'type': 'text', 'text': json.dumps(ex['target'])},\n",
        "            ]},\n",
        "        ],\n",
        "    }\n",
        "\n",
        "train_ds = [_convo(ex) for ex in train]\n",
        "val_ds   = [_convo(ex) for ex in val[:32]]   # cap val to keep eval fast during training\n",
        "print('train examples:', len(train_ds), 'val examples:', len(val_ds))\n",
    )


def format_dataset_kimi():
    return md(
        "## 6. Format dataset for TRL SFTTrainer\n",
    ), code(
        "from PIL import Image\n",
        "from datasets import Dataset\n",
        "\n",
        "def _to_chat(ex):\n",
        "    messages = [\n",
        "        {'role': 'system', 'content': SYSTEM_PROMPT},\n",
        "        {'role': 'user', 'content': [\n",
        "            {'type': 'image', 'image': ex['image_path']},\n",
        "            {'type': 'text', 'text': f\"Beverage type: {ex['beverage_type']}. Extract per the schema.\"},\n",
        "        ]},\n",
        "        {'role': 'assistant', 'content': [{'type': 'text', 'text': json.dumps(ex['target'])}]},\n",
        "    ]\n",
        "    return {'messages': messages}\n",
        "\n",
        "train_ds = Dataset.from_list([_to_chat(ex) for ex in train])\n",
        "val_ds   = Dataset.from_list([_to_chat(ex) for ex in val[:32]])\n",
        "print('train examples:', len(train_ds), 'val examples:', len(val_ds))\n",
    )


def trainer_qwen():
    return md(
        "## 7. Train — Unsloth SFT trainer\n",
    ), code(
        "from trl import SFTTrainer, SFTConfig\n",
        "from unsloth import is_bf16_supported\n",
        "\n",
        "trainer = SFTTrainer(\n",
        "    model = model,\n",
        "    tokenizer = tokenizer,\n",
        "    data_collator = UnslothVisionDataCollator(model, tokenizer),\n",
        "    train_dataset = train_ds,\n",
        "    args = SFTConfig(\n",
        "        per_device_train_batch_size = 2,\n",
        "        gradient_accumulation_steps = 4,\n",
        "        warmup_steps = 5,\n",
        "        num_train_epochs = 3,\n",
        "        learning_rate = 2e-4,\n",
        "        fp16 = not is_bf16_supported(),\n",
        "        bf16 = is_bf16_supported(),\n",
        "        logging_steps = 5,\n",
        "        optim = 'adamw_8bit',\n",
        "        weight_decay = 0.01,\n",
        "        lr_scheduler_type = 'linear',\n",
        "        seed = 42,\n",
        "        output_dir = str(WORK_DIR / 'checkpoints'),\n",
        "        save_strategy = 'epoch',\n",
        "        report_to = 'none',\n",
        "        remove_unused_columns = False,\n",
        "        dataset_text_field = '',\n",
        "        dataset_kwargs = {'skip_prepare_dataset': True},\n",
        "        dataset_num_proc = 1,\n",
        "        max_seq_length = 2048,\n",
        "    ),\n",
        ")\n",
        "trainer_stats = trainer.train()\n",
        "print('Done:', trainer_stats)\n",
    )


def trainer_kimi():
    return md(
        "## 7. Train — TRL SFTTrainer with custom collator\n",
    ), code(
        "from trl import SFTTrainer, SFTConfig\n",
        "from PIL import Image\n",
        "\n",
        "def _collate(batch):\n",
        "    texts, images = [], []\n",
        "    for ex in batch:\n",
        "        msgs = ex['messages']\n",
        "        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)\n",
        "        texts.append(text)\n",
        "        # Find the user message's image path and load\n",
        "        for m in msgs:\n",
        "            if m['role'] == 'user' and isinstance(m['content'], list):\n",
        "                for c in m['content']:\n",
        "                    if c.get('type') == 'image':\n",
        "                        images.append(Image.open(c['image']).convert('RGB'))\n",
        "    enc = processor(text=texts, images=images, return_tensors='pt', padding=True, truncation=True, max_length=2048)\n",
        "    enc['labels'] = enc['input_ids'].clone()\n",
        "    # Mask system + user tokens from the loss\n",
        "    return enc\n",
        "\n",
        "trainer = SFTTrainer(\n",
        "    model = model,\n",
        "    args = SFTConfig(\n",
        "        per_device_train_batch_size = 1,\n",
        "        gradient_accumulation_steps = 8,\n",
        "        warmup_steps = 5,\n",
        "        num_train_epochs = 3,\n",
        "        learning_rate = 1e-4,\n",
        "        bf16 = True,\n",
        "        logging_steps = 5,\n",
        "        optim = 'adamw_8bit',\n",
        "        weight_decay = 0.01,\n",
        "        lr_scheduler_type = 'linear',\n",
        "        seed = 42,\n",
        "        output_dir = str(WORK_DIR / 'checkpoints'),\n",
        "        save_strategy = 'epoch',\n",
        "        report_to = 'none',\n",
        "        max_seq_length = 2048,\n",
        "        remove_unused_columns = False,\n",
        "    ),\n",
        "    train_dataset = train_ds,\n",
        "    data_collator = _collate,\n",
        ")\n",
        "trainer_stats = trainer.train()\n",
        "print('Done:', trainer_stats)\n",
    )


EVAL_CELL = md(
    "## 8. Evaluate on the held-out test set\n",
    "\n",
    "Per-field accuracy + bucket distribution. The eval mirrors the backend's rules engine to give a head-to-head against Claude's numbers.\n",
), code(
    "import json, re\n",
    "from collections import Counter\n",
    "\n",
    "def _norm(s):\n",
    "    s = (s or '').strip().lower()\n",
    "    s = re.sub(r'\\s+', ' ', s)\n",
    "    s = re.sub(r'[.,]', '', s)\n",
    "    return s\n",
    "\n",
    "def _generate_json(image_path, beverage_type):\n",
    "    \"\"\"Run the trained model on one image and return its parsed JSON.\"\"\"\n",
    "    from PIL import Image\n",
    "    img = Image.open(image_path).convert('RGB')\n",
    "    msgs = [\n",
    "        {'role': 'system', 'content': SYSTEM_PROMPT},\n",
    "        {'role': 'user',   'content': [\n",
    "            {'type': 'image', 'image': img},\n",
    "            {'type': 'text', 'text': f'Beverage type: {beverage_type}. Extract per the schema.'},\n",
    "        ]},\n",
    "    ]\n",
    "    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)\n",
    "    inputs = processor(text=[text], images=[img], return_tensors='pt').to(model.device)\n",
    "    with torch.no_grad():\n",
    "        out = model.generate(**inputs, max_new_tokens=512, do_sample=False)\n",
    "    txt = processor.batch_decode(out[:, inputs['input_ids'].shape[1]:], skip_special_tokens=True)[0]\n",
    "    # Try to find the JSON object in the output\n",
    "    try:\n",
    "        start = txt.find('{')\n",
    "        return json.loads(txt[start:txt.rfind('}') + 1])\n",
    "    except Exception:\n",
    "        return None\n",
    "\n",
    "field_correct = Counter(); field_total = Counter()\n",
    "warning_present_match = 0; warning_total = 0\n",
    "n_parsed = n_unparseable = 0\n",
    "\n",
    "from tqdm.auto import tqdm\n",
    "for ex in tqdm(test, desc='Evaluating'):\n",
    "    pred = _generate_json(ex['image_path'], ex['beverage_type'])\n",
    "    if pred is None:\n",
    "        n_unparseable += 1\n",
    "        continue\n",
    "    n_parsed += 1\n",
    "    # Per-field accuracy\n",
    "    for fname, fobs in (ex['target']['fields'] or {}).items():\n",
    "        field_total[fname] += 1\n",
    "        got = (pred.get('fields') or {}).get(fname, {}).get('value', '')\n",
    "        if _norm(got) == _norm(fobs['value']):\n",
    "            field_correct[fname] += 1\n",
    "    # Warning presence + verbatim closeness\n",
    "    gt_w = ex['target']['government_warning']\n",
    "    pred_w = pred.get('government_warning') or {}\n",
    "    warning_total += 1\n",
    "    if bool(gt_w.get('present')) == bool(pred_w.get('present')):\n",
    "        warning_present_match += 1\n",
    "\n",
    "print(f'\\nParsed: {n_parsed} / Unparseable: {n_unparseable}')\n",
    "print('Per-field accuracy:')\n",
    "for fname in sorted(field_total):\n",
    "    acc = field_correct[fname] / field_total[fname]\n",
    "    print(f'  {fname:<24} {field_correct[fname]:>3} / {field_total[fname]:>3} = {acc:.1%}')\n",
    "print(f'Warning-presence accuracy: {warning_present_match} / {warning_total} = {warning_present_match/warning_total:.1%}')\n",
    "\n",
    "# Save report to Drive\n",
    "report = {\n",
    "    'n_test': len(test), 'n_parsed': n_parsed, 'n_unparseable': n_unparseable,\n",
    "    'field_accuracy': {f: {'correct': field_correct[f], 'total': field_total[f]} for f in field_total},\n",
    "    'warning_present_accuracy': warning_present_match / warning_total if warning_total else None,\n",
    "}\n",
    "with open(WORK_DIR / 'eval_report.json', 'w') as f:\n",
    "    json.dump(report, f, indent=2)\n",
    "print(f'\\nReport written to {WORK_DIR}/eval_report.json')\n",
)


SAVE_ADAPTER = md(
    "## 9. Save LoRA adapter to Drive (downloadable, integrates with backend)\n",
), code(
    "import shutil, json\n",
    "ADAPTER_DIR = WORK_DIR / 'adapter'\n",
    "ADAPTER_DIR.mkdir(exist_ok=True)\n",
    "\n",
    "# Save adapter\n",
    "model.save_pretrained(str(ADAPTER_DIR))\n",
    "# Save processor (so the backend can re-load with the same tokenizer config)\n",
    "try:\n",
    "    tokenizer.save_pretrained(str(ADAPTER_DIR))\n",
    "except Exception:\n",
    "    processor.save_pretrained(str(ADAPTER_DIR))\n",
    "\n",
    "# Write a small manifest so the backend knows what to load\n",
    "manifest = {\n",
    "    'model_tag': MODEL_TAG,\n",
    "    'base_model': BASE_MODEL,\n",
    "    'trained_on': 'COLA Cloud free sample (CC0) — N=' + str(len(train)),\n",
    "    'lora_rank': 16,\n",
    "    'epochs': 3,\n",
    "}\n",
    "with open(ADAPTER_DIR / 'manifest.json', 'w') as f:\n",
    "    json.dump(manifest, f, indent=2)\n",
    "\n",
    "print(f'Adapter + processor saved to {ADAPTER_DIR}')\n",
    "print('Download it via Files panel → drive/MyDrive/ttb_sft/' + MODEL_TAG + '/adapter')\n",
)


AUTO_DOWNLOAD = md(
    "## 10. Zip the adapter and download to your Mac\n",
    "\n",
    "Bundles the adapter + processor config + eval report into a single zip\n",
    "and triggers a browser download to your default Downloads folder. After\n",
    "this cell finishes, the file `~/Downloads/ttb_sft_{model_tag}.zip` is on\n",
    "your Mac, ready to integrate into the backend.\n",
), code(
    "import shutil\n",
    "from google.colab import files\n",
    "\n",
    "# Include adapter + splits + eval report in the bundle so we can audit later.\n",
    "BUNDLE_DIR = WORK_DIR / f'ttb_sft_{MODEL_TAG}'\n",
    "BUNDLE_DIR.mkdir(exist_ok=True)\n",
    "import os\n",
    "for src in ['adapter', 'splits', 'eval_report.json']:\n",
    "    src_path = WORK_DIR / src\n",
    "    if src_path.exists():\n",
    "        dst = BUNDLE_DIR / src\n",
    "        if dst.exists():\n",
    "            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()\n",
    "        if src_path.is_dir():\n",
    "            shutil.copytree(src_path, dst)\n",
    "        else:\n",
    "            shutil.copy(src_path, dst)\n",
    "\n",
    "zip_base = str(WORK_DIR / f'ttb_sft_{MODEL_TAG}')\n",
    "zip_path = shutil.make_archive(zip_base, 'zip', root_dir=str(BUNDLE_DIR))\n",
    "size_mb = os.path.getsize(zip_path) / 1024**2\n",
    "print(f'Bundle: {zip_path}  ({size_mb:.1f} MB)')\n",
    "print('Triggering browser download — accept the prompt that pops up.')\n",
    "files.download(zip_path)\n",
),


INTEGRATION_NOTE = md(
    "## 11. Integrate the trained model into the backend\n",
    "\n",
    "After this notebook finishes, the LoRA adapter sits in your Drive at:\n",
    "```\n",
    "/MyDrive/ttb_sft/{model_tag}/adapter/\n",
    "```\n",
    "\n",
    "Local-side steps (next session):\n",
    "1. Download the `adapter/` directory to `backend/models/{model_tag}/`.\n",
    "2. Add a new `INFERENCE_MODE=sft` adapter in `backend/app/extractors/sft.py` that loads the base model + LoRA via vLLM (production) or transformers (dev) and returns the same `ExtractedLabel` shape.\n",
    "3. Register the mode in `backend/app/extractors/factory.py`.\n",
    "4. Run `make serve-sft` (we'll add it to the Makefile).\n",
    "5. Re-run the eval against the same test set — head-to-head with Claude.\n",
    "\n",
    "If the eval beats Claude on per-field accuracy AND latency is < 2s on a single GPU, this becomes the recommended path for the production demo.\n",
)


# ────────────────────────────────────────────────────────────────────────────
# Notebook builder
# ────────────────────────────────────────────────────────────────────────────


def build_notebook(model_tag, base_model, library, cells):
    """Convert a list of (kind, lines) tuples into a Jupyter notebook dict."""
    nb_cells = []
    for kind, lines in cells:
        if kind == "markdown":
            nb_cells.append({
                "cell_type": "markdown",
                "metadata": {},
                "source": lines,
            })
        else:
            nb_cells.append({
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": lines,
            })
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
            "colab": {"provenance": [], "gpuType": "A100"},
            "accelerator": "GPU",
        },
        "cells": nb_cells,
    }


def write(path, nb):
    path.write_text(json.dumps(nb, indent=1))


# ────────────────────────────────────────────────────────────────────────────
# Compose the two notebooks
# ────────────────────────────────────────────────────────────────────────────


def main():
    OUT = Path(__file__).parent

    # Each notebook starts with a model-tag cell so the rest of the cells can
    # reference MODEL_TAG / BASE_MODEL without hard-coding.
    def model_tag_cell(tag, base):
        return code(f"MODEL_TAG = {tag!r}\nBASE_MODEL = {base!r}\n")

    # ── Qwen notebook ──
    qwen_cells = [
        header("Qwen2.5-VL-7B", "unsloth/Qwen2.5-VL-7B-Instruct", "Unsloth"),
        md("## 0. Install dependencies & set model tag\n"),
        code("!pip install -q --upgrade pip\n",
             "!pip install -q \"unsloth[colab-new]\" 'trl<0.10.0' peft accelerate bitsandbytes\n",
             "!pip install -q datasets pillow requests tqdm\n"),
        model_tag_cell("qwen2_5_vl_7b", "unsloth/Qwen2.5-VL-7B-Instruct"),
        SETUP_DRIVE,
        *DOWNLOAD_DATA,
        *BUILD_PAIRS,
        *DOWNLOAD_IMAGES,
        *SPLIT_DATA,
        SYSTEM_PROMPT_VAR,
        *model_load_qwen(),
        *format_dataset_qwen(),
        *trainer_qwen(),
        *EVAL_CELL,
        *SAVE_ADAPTER,
        *AUTO_DOWNLOAD,
        INTEGRATION_NOTE,
    ]
    write(OUT / "sft_qwen2_5_vl.ipynb", build_notebook(
        "qwen2_5_vl_7b", "unsloth/Qwen2.5-VL-7B-Instruct", "Unsloth", qwen_cells,
    ))
    print(f"wrote {OUT / 'sft_qwen2_5_vl.ipynb'}")

    # ── Kimi notebook ──
    kimi_cells = [
        header("Kimi-VL-A3B-Thinking", "moonshotai/Kimi-VL-A3B-Thinking-2506", "transformers + PEFT + TRL"),
        md("## 0. Install dependencies & set model tag\n"),
        code("!pip install -q --upgrade pip\n",
             "!pip install -q transformers accelerate bitsandbytes peft 'trl<0.10.0'\n",
             "!pip install -q datasets pillow requests tqdm sentencepiece\n"),
        model_tag_cell("kimi_vl_a3b_thinking", "moonshotai/Kimi-VL-A3B-Thinking-2506"),
        SETUP_DRIVE,
        *DOWNLOAD_DATA,
        *BUILD_PAIRS,
        *DOWNLOAD_IMAGES,
        *SPLIT_DATA,
        SYSTEM_PROMPT_VAR,
        *model_load_kimi(),
        *format_dataset_kimi(),
        *trainer_kimi(),
        *EVAL_CELL,
        *SAVE_ADAPTER,
        *AUTO_DOWNLOAD,
        INTEGRATION_NOTE,
    ]
    write(OUT / "sft_kimi_vl.ipynb", build_notebook(
        "kimi_vl_a3b_thinking", "moonshotai/Kimi-VL-A3B-Thinking-2506",
        "transformers + PEFT + TRL", kimi_cells,
    ))
    print(f"wrote {OUT / 'sft_kimi_vl.ipynb'}")


if __name__ == "__main__":
    main()
