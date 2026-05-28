"""Modal deployment of the Qwen2.5-VL LoRA extractor.

One-time setup (locally):
    pip install modal
    modal token new                           # auth
    modal volume create ttb-qwen-adapter      # adapter weights live here
    modal volume put ttb-qwen-adapter \\
        backend/models/qwen2_5_vl_7b/adapter /adapter

Deploy:
    modal deploy backend/modal_deploy/serve_qwen.py

The deploy prints an HTTPS endpoint like:
    https://<user>--ttb-qwen-extractor-extract-web.modal.run

Point the backend at it by setting:
    INFERENCE_MODE=modal
    MODAL_ENDPOINT_URL=https://<user>--ttb-qwen-extractor-extract-web.modal.run

Cost model (A10G):
    - $0.40/hr active
    - $0 idle (scale-to-zero after container_idle_timeout)
    - ~3-5 s per inference
    - Demo usage (~10 req/day): well within Modal's $30/mo free tier
"""

from __future__ import annotations

import modal

# ── Image + dependencies ────────────────────────────────────────────────────
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # Matches notebooks/eval_qwen_drive.ipynb stack — verified end-to-end:
        "transformers==4.51.3",       # has Qwen2.5-VL + 4.49 config-regression fix
        "peft>=0.13",
        "torchao>=0.16",              # peft asserts this
        "accelerate>=0.30",
        "protobuf>=5.27",             # transformers 4.48+ needs runtime_version
        "torch>=2.5",
        "pillow",
        "fastapi[standard]",
        "numpy>=2.0,<2.2",
    )
)

# Persistent volume for the LoRA adapter (uploaded out-of-band; see header).
adapter_volume = modal.Volume.from_name("ttb-qwen-adapter", create_if_missing=True)
# HF cache volume so the 5 GB Qwen base downloads once, not per container.
hf_cache_volume = modal.Volume.from_name("ttb-qwen-hf-cache", create_if_missing=True)

app = modal.App("ttb-qwen-extractor")


_SYSTEM_PROMPT = (
    "You are a careful transcription assistant for U.S. TTB alcohol label review. "
    "Given ONE label panel image and the beverage type, READ what is printed and "
    "RETURN ONLY a JSON object matching the schema below. Do NOT decide compliance.\n\n"
    "If a field is not clearly visible, OMIT it from the fields object. Never guess; "
    "never substitute deposit codes (e.g. \"CA CRV\"), NOM IDs, or barcodes. Transcribe "
    "the Government Warning EXACTLY as printed (preserve case, punctuation, errors).\n\n"
    "Schema: {fields: {<field name>: {value, confidence}}, government_warning: "
    "{present, detected_text, casing_all_caps, heading_bold, body_bold, approx_font_mm, "
    "contrast_ok, separate_and_apart}, image_quality: {score, legible, note}}"
)


@app.cls(
    image=image,
    gpu="A10G",                          # 24 GB, $0.40/hr — fits Qwen 7B BF16 + LoRA comfortably
    volumes={
        "/adapter":                  adapter_volume,
        "/root/.cache/huggingface":  hf_cache_volume,
    },
    container_idle_timeout=300,          # scale to zero after 5 min idle
    timeout=120,                          # max 2 min per inference
    min_containers=0,                     # truly scale-to-zero (no warm pool)
)
class QwenExtractor:
    """Loads Qwen2.5-VL base + LoRA adapter once per container, reuses across requests."""

    @modal.enter()
    def load_model(self):
        import torch
        from peft import PeftModel
        from transformers import (
            Qwen2_5_VLForConditionalGeneration,
            AutoProcessor,
        )

        # Match the BF16 training setup (notebooks/sft_qwen2_5_vl.ipynb):
        # Official Qwen base in BF16 + LoRA adapter applied + merged.
        # Training-time and inference-time dtypes must match for LoRA to
        # contribute correctly.
        BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
        ADAPTER_DIR = "/adapter"

        print(f"[Modal] Loading {BASE_MODEL} (BF16)...")
        base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            BASE_MODEL,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
        )
        print(f"[Modal] Applying LoRA adapter from {ADAPTER_DIR}...")
        self.model = PeftModel.from_pretrained(base, ADAPTER_DIR)
        # Merge LoRA into base for inference — safe in BF16, eliminates the
        # ~15% per-call LoRA overhead. We're done training, won't need to
        # save the adapter back, so destroying the PEFT wrapper is fine.
        self.model = self.model.merge_and_unload()
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(BASE_MODEL)
        print(f"[Modal] Ready. Free VRAM: {torch.cuda.mem_get_info()[0]/1e9:.1f} GB")

    @modal.method()
    def extract(self, image_bytes: bytes, beverage_type: str) -> dict:
        """Returns {raw_output: str, latency_sec: float}. Parsing happens client-side."""
        import io, json, time
        import torch
        from PIL import Image

        t0 = time.time()
        # Cap image resolution: Qwen2.5-VL otherwise tiles at native res and
        # generates 4000+ visual tokens per image → quadratic-slow attention.
        # 640x640 area = ~400 visual tokens, plenty for label OCR, ~3s/image
        # on A10G instead of ~12s. Matches the eval notebook's _resize_for_eval.
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        MAX_PIXELS = 640 * 640
        w, h = img.size
        if w * h > MAX_PIXELS:
            scale = (MAX_PIXELS / (w * h)) ** 0.5
            img = img.resize((max(int(w * scale), 28), max(int(h * scale), 28)), Image.LANCZOS)
        w, h = img.size
        w28, h28 = max((w // 28) * 28, 28), max((h // 28) * 28, 28)
        if (w28, h28) != (w, h):
            img = img.resize((w28, h28), Image.LANCZOS)

        msgs = [
            {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT}]},
            {"role": "user",   "content": [
                {"type": "image", "image": img},
                {"type": "text",  "text": f"Beverage type: {beverage_type}. Extract per the schema."},
            ]},
        ]
        text = self.processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[img], padding=True, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                max_new_tokens=384,       # tight cap; our outputs are ~200-300 tokens
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self.processor.tokenizer.eos_token_id,
            )
        decoded = self.processor.batch_decode(
            out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )[0]
        return {"raw_output": decoded, "latency_sec": round(time.time() - t0, 3)}


# ── HTTPS endpoint (so the backend can hit it from anywhere) ─────────────────

@app.function(image=image, timeout=120)
@modal.fastapi_endpoint(method="POST", docs=True)
def extract_web(payload: dict) -> dict:
    """POST {image_b64: <base64>, beverage_type: "wine"} → {raw_output, latency_sec}.

    We base64-encode the image because Modal's fastapi_endpoint expects JSON.
    """
    import base64

    img_b64 = payload.get("image_b64")
    beverage = payload.get("beverage_type", "wine")
    if not img_b64:
        return {"error": "missing image_b64 in payload"}
    image_bytes = base64.b64decode(img_b64)
    return QwenExtractor().extract.remote(image_bytes, beverage)


# ── Local dev: run a single inference from CLI ──────────────────────────────

@app.local_entrypoint()
def main(image_path: str, beverage_type: str = "wine"):
    """Test the deployment from your laptop:
        modal run backend/modal_deploy/serve_qwen.py \\
            --image-path test/eval/data/images/25240001000020_0.webp
    """
    from pathlib import Path
    image_bytes = Path(image_path).read_bytes()
    result = QwenExtractor().extract.remote(image_bytes, beverage_type)
    print()
    print(f"latency:     {result['latency_sec']}s")
    print(f"raw_output:  {result['raw_output'][:500]}...")
