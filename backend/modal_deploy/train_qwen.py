"""Modal A100 training app for Qwen2.5-VL-7B LoRA v2.

Trains on the stratified TTB-live corpus (~18K labels) using fields-only
targets sourced from TTB Form 5100.31. Mirrors the schema + training
contract of notebooks/sft_qwen2_5_vl.ipynb (system prompt, target JSON
shape, group-aware batching) so v1 vs v2 stays a clean A/B.

Why a single epoch:
  18K × 3 epochs × ~3.5s/step ≈ 50 hrs ≫ budget. 18K unique examples is
  6× more signal than v1's 2-epoch × ~2750-example run; an extra pass
  buys little vs more data. 1 epoch ≈ 17 hrs ≈ $19 on A100-40GB.

One-time setup (locally):
    backend/.venv/bin/modal token current               # confirm auth
    make modal-upload-train-data                        # uploads JSONL + images

Train:
    make modal-train                                    # ~17 hrs
    make modal-download-adapter-v2                      # pulls adapter to Mac

The adapter lands at backend/models/qwen2_5_vl_7b_v2/adapter/ so v1 and
v2 can coexist for the head-to-head eval.

Volumes:
    ttb-qwen-train-data    JSONL splits + images (read-only at train time)
    ttb-qwen-adapter-v2    output LoRA + manifest (writable)
    ttb-qwen-hf-cache      reused HuggingFace cache (shared w/ serve_qwen.py)
"""
from __future__ import annotations

import modal

# ── Image: training deps + matched pins from notebook ──────────────────────
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers==4.51.3",
        "peft>=0.13",
        "torchao>=0.16",
        "trl>=0.12",
        "accelerate>=0.30",
        "bitsandbytes>=0.44",
        "datasets>=2.20",
        "protobuf>=5.27",
        "torch>=2.5",
        "pillow",
        "qwen-vl-utils",
        "numpy>=2.0,<2.2",
        "tqdm",
    )
)

train_data_vol  = modal.Volume.from_name("ttb-qwen-train-data",  create_if_missing=True)
adapter_v2_vol  = modal.Volume.from_name("ttb-qwen-adapter-v2",  create_if_missing=True)
hf_cache_vol    = modal.Volume.from_name("ttb-qwen-hf-cache",    create_if_missing=True)

app = modal.App("ttb-qwen-train-v2")

# Fields-only schema — see test/eval/build_qwen_jsonl.py for ground-truth
# sourcing. v2 is a specialized field extractor; warning + image_quality
# get chained in at the backend layer (separate code path).
_SYSTEM_PROMPT = (
    "You are a careful transcription assistant for U.S. TTB alcohol label review. "
    "You will see a single image that may contain MULTIPLE label panels stacked "
    "vertically (front + back + neck + strip). READ what is printed across ALL panels "
    "and RETURN ONLY a JSON object matching the schema below. Do NOT decide compliance.\n\n"
    "CRITICAL — use ONLY these EXACT field names in the fields object (case-sensitive, "
    "preserve spaces and punctuation):\n"
    "  - 'Brand name'\n"
    "  - 'Class & type'\n"
    "  - 'Bottler name/address'\n"
    "  - 'Country of origin'  (imports only; omit for U.S. labels)\n\n"
    "Do NOT invent variants ('brand_name', 'Volume', 'Bottled_by', 'product_type', "
    "'location', etc). If a field is not clearly visible across the panels, OMIT it "
    "from the fields object entirely. Never guess; never substitute deposit codes "
    "(e.g. 'CA CRV'), NOM IDs, or barcodes.\n\n"
    "Schema: {fields: {<field name>: {value, confidence}}}"
)


@app.function(
    image=image,
    gpu="A100-40GB",
    volumes={
        "/data":                      train_data_vol,
        "/out":                       adapter_v2_vol,
        "/root/.cache/huggingface":   hf_cache_vol,
    },
    timeout=24 * 3600,   # 24 hr ceiling; expected ~17 hr
)
def train(epochs: int = 1, lora_rank: int = 16, lr: float = 1e-4) -> dict:
    """Run the full SFT loop. Returns a manifest dict summarizing the run."""
    import json
    import os
    import time
    from pathlib import Path

    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, TaskType
    from PIL import Image
    from transformers import (
        AutoProcessor,
        Qwen2_5_VLForConditionalGeneration,
        TrainingArguments,
        Trainer,
    )

    BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
    DATA_DIR = Path("/data")
    OUT_DIR  = Path("/out")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Load JSONL splits ────────────────────────────────────────────────
    def _load_jsonl(path: Path) -> list[dict]:
        return [json.loads(l) for l in open(path) if l.strip()]

    train_ex = _load_jsonl(DATA_DIR / "train.jsonl")
    val_ex   = _load_jsonl(DATA_DIR / "val.jsonl")
    print(f"[data] train={len(train_ex)}  val={len(val_ex)}", flush=True)

    # ─── Load Qwen base + apply LoRA ──────────────────────────────────────
    print(f"[model] loading {BASE_MODEL} BF16...", flush=True)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa",
    )
    processor = AutoProcessor.from_pretrained(BASE_MODEL)

    # LoRA targets the language tower only — keeps the vision encoder frozen.
    # rank 16 matches v1; alpha 32 = 2x rank is the standard scaling.
    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=lora_rank,
        lora_alpha=lora_rank * 2,
        lora_dropout=0.05,
        bias="none",
        target_modules=["q_proj","k_proj","v_proj","o_proj",
                        "gate_proj","up_proj","down_proj"],
    )
    model = get_peft_model(model, lora_cfg)
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[model] LoRA trainable params: {n_trainable/1e6:.1f}M", flush=True)

    # ─── Image preprocessing ──────────────────────────────────────────────
    # Composites are multi-panel (~2-3x taller than single-panel v1 inputs).
    # Cap at ~1.5M pixels — keeps visual-token count manageable (~1500
    # tokens) without losing panel readability. v1 capped at 1M for
    # single-panel; composites need more headroom.
    MAX_PIXELS = 1500 * 1024
    def _resize(img: Image.Image) -> Image.Image:
        w, h = img.size
        if w * h > MAX_PIXELS:
            scale = (MAX_PIXELS / (w * h)) ** 0.5
            img = img.resize((max(int(w * scale), 28), max(int(h * scale), 28)),
                             Image.LANCZOS)
        w, h = img.size
        w28, h28 = max((w // 28) * 28, 28), max((h // 28) * 28, 28)
        if (w28, h28) != (w, h):
            img = img.resize((w28, h28), Image.LANCZOS)
        return img

    # ─── HF Dataset + per-example collator (Qwen-VL needs batch_size=1) ──
    def _flatten(ex):
        # The JSONL `image_path` is repo-relative; on Modal we strip the
        # leading "test/eval/data/" so it resolves under /data/...
        rel = ex["image_path"]
        for prefix in ("test/eval/data/ttb_live/", "test/eval/data/"):
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                break
        return {
            "image_path":    f"/data/images/{Path(rel).name}",
            "beverage_type": ex["beverage_type"],
            "target_json":   json.dumps(ex["target"]),
        }

    train_ds = Dataset.from_list([_flatten(ex) for ex in train_ex])
    val_ds   = Dataset.from_list([_flatten(ex) for ex in val_ex])

    def _collate(batch):
        assert len(batch) == 1, "Qwen2.5-VL collator expects batch_size=1"
        ex = batch[0]
        img = _resize(Image.open(ex["image_path"]).convert("RGB"))
        msgs = [
            {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT}]},
            {"role": "user",   "content": [
                {"type": "image", "image": img},
                {"type": "text",  "text": f"Beverage type: {ex['beverage_type']}. Extract per the schema."},
            ]},
            {"role": "assistant", "content": [{"type": "text", "text": ex["target_json"]}]},
        ]
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        enc = processor(text=[text], images=[img], padding=True, return_tensors="pt",
                        truncation=True, max_length=2048)
        labels = enc["input_ids"].clone()
        pad_id = processor.tokenizer.pad_token_id
        if pad_id is not None:
            labels[labels == pad_id] = -100
        enc["labels"] = labels
        return enc

    # ─── Training arguments ───────────────────────────────────────────────
    args = TrainingArguments(
        output_dir=str(OUT_DIR / "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=4,    # effective batch 4
        learning_rate=lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=20,
        eval_strategy="steps",
        eval_steps=500,
        save_strategy="steps",
        save_steps=1000,
        save_total_limit=3,
        bf16=True,
        gradient_checkpointing=True,
        report_to="none",
        remove_unused_columns=False,
        dataloader_num_workers=2,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=_collate,
    )

    print(f"[train] starting — epochs={epochs}, rank={lora_rank}, lr={lr}", flush=True)
    t0 = time.time()
    trainer.train()
    train_seconds = time.time() - t0
    print(f"[train] done in {train_seconds/3600:.2f} hr", flush=True)

    # ─── Save adapter + manifest ──────────────────────────────────────────
    adapter_dir = OUT_DIR / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    try:
        processor.save_pretrained(str(adapter_dir))
    except Exception:
        pass

    manifest = {
        "model_tag":        "qwen2_5_vl_7b_v2_bf16",
        "base_model":       BASE_MODEL,
        "trained_on":       "TTB-live stratified 18K (fields-only targets)",
        "lora_rank":        lora_rank,
        "lora_alpha":       lora_rank * 2,
        "epochs":           epochs,
        "lr":               lr,
        "n_train_examples": len(train_ex),
        "n_val_examples":   len(val_ex),
        "train_seconds":    int(train_seconds),
        "training_dtype":   "bf16",
        "schema":           "fields-only (no government_warning, no image_quality)",
    }
    (adapter_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    adapter_v2_vol.commit()    # flush to persistent storage

    print(f"[done] adapter saved to volume ttb-qwen-adapter-v2 at /adapter", flush=True)
    return manifest


@app.local_entrypoint()
def main(epochs: int = 1, lora_rank: int = 16, lr: float = 1e-4):
    """Kick off the training run from the laptop.

    Usage:
        modal run backend/modal_deploy/train_qwen.py
        modal run backend/modal_deploy/train_qwen.py --epochs 2

    The run streams logs back; safe to ctrl-c (run keeps going on Modal).
    """
    manifest = train.remote(epochs=epochs, lora_rank=lora_rank, lr=lr)
    print("\n=== TRAINING MANIFEST ===")
    import json as _j
    print(_j.dumps(manifest, indent=2))
