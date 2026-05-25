"""Modal deployment of the Qwen2.5-VL LoRA v2 extractor (eval-only).

This is a near-duplicate of serve_qwen.py — same image, same loader, same
HTTP contract — but pointed at the ttb-qwen-adapter-v2 volume produced by
train_qwen.py. Lets v1 and v2 coexist as separate Modal endpoints so the
head-to-head eval (test/eval/eval_holdout.py) can hit them independently
without restarting any infra.

Once v2 wins the head-to-head and is promoted to primary, copy its
adapter to ttb-qwen-adapter (overwriting v1) and serve_qwen.py picks it
up automatically — at which point serve_qwen_v2.py can be deleted.

Deploy:
    modal deploy backend/modal_deploy/serve_qwen_v2.py

Endpoint:
    https://<user>--ttb-qwen-extractor-v2-extract-web.modal.run
"""
from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers==4.51.3",
        "peft>=0.13",
        "torchao>=0.16",
        "accelerate>=0.30",
        "protobuf>=5.27",
        "torch>=2.5",
        "pillow",
        "fastapi[standard]",
        "numpy>=2.0,<2.2",
    )
)

adapter_volume   = modal.Volume.from_name("ttb-qwen-adapter-v2",   create_if_missing=True)
hf_cache_volume  = modal.Volume.from_name("ttb-qwen-hf-cache",     create_if_missing=True)

app = modal.App("ttb-qwen-extractor-v2")

# Fields-only schema. Must match the system prompt used in train_qwen.py
# (training and inference prompts diverging would break LoRA contribution).
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


@app.cls(
    image=image,
    gpu="A10G",
    volumes={
        "/adapter":                  adapter_volume,
        "/root/.cache/huggingface":  hf_cache_volume,
    },
    container_idle_timeout=300,
    timeout=120,
    min_containers=0,
)
class QwenExtractorV2:
    @modal.enter()
    def load_model(self):
        import torch
        from peft import PeftModel
        from transformers import (
            Qwen2_5_VLForConditionalGeneration,
            AutoProcessor,
        )

        BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
        ADAPTER_DIR = "/adapter"

        print(f"[Modal v2] Loading {BASE_MODEL} (BF16)...")
        base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            BASE_MODEL,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
        )
        print(f"[Modal v2] Applying LoRA adapter from {ADAPTER_DIR}...")
        self.model = PeftModel.from_pretrained(base, ADAPTER_DIR)
        self.model = self.model.merge_and_unload()
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(BASE_MODEL)
        print(f"[Modal v2] Ready. Free VRAM: {torch.cuda.mem_get_info()[0]/1e9:.1f} GB")

    @modal.method()
    def extract(self, image_bytes: bytes, beverage_type: str) -> dict:
        import io, time
        import torch
        from PIL import Image

        t0 = time.time()
        # v2 was trained on stacked multi-panel composites — give it a
        # taller image budget than v1 (which was single-panel only).
        # 1.5M pixels matches the training-time MAX_PIXELS in train_qwen.py.
        MAX_PIXELS = 1500 * 1024
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
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
                max_new_tokens=384,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self.processor.tokenizer.eos_token_id,
            )
        decoded = self.processor.batch_decode(
            out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )[0]
        return {"raw_output": decoded, "latency_sec": round(time.time() - t0, 3)}


@app.function(image=image, timeout=120)
@modal.fastapi_endpoint(method="POST", docs=True)
def extract_web(payload: dict) -> dict:
    import base64
    img_b64 = payload.get("image_b64")
    beverage = payload.get("beverage_type", "wine")
    if not img_b64:
        return {"error": "missing image_b64 in payload"}
    return QwenExtractorV2().extract.remote(base64.b64decode(img_b64), beverage)


@app.local_entrypoint()
def main(image_path: str, beverage_type: str = "wine"):
    from pathlib import Path
    image_bytes = Path(image_path).read_bytes()
    result = QwenExtractorV2().extract.remote(image_bytes, beverage_type)
    print()
    print(f"latency:     {result['latency_sec']}s")
    print(f"raw_output:  {result['raw_output'][:500]}...")
