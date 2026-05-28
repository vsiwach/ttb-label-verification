"""Modal deployment of the TTB inference endpoint — Qwen v2 LoRA + Tesseract.

Single Modal container produces everything needed for the 7 mandatory checks
in one HTTPS call:

  Qwen2.5-VL-7B base + LoRA "v2" (TTB-live N≈8968, 3 epochs)
   → Brand, Class & type, Bottler, Country of origin

  Tesseract OCR (CPU, parallel to LoRA pass)
   → Alcohol content (regex)
   → Net contents (regex)
   → Government Warning verbatim text + casing + bounding-box height
   → image DPI from EXIF (for 27 CFR 16.22 type-size math)

Everything is deterministic on the OCR side; Qwen handles only the four
fields it was trained to extract. No third-party API touches the data.

Cold-start expectation:
    First request after >5 min idle = 30-60s (Qwen 7B base loads from HF
    cache volume; v2 LoRA merges into base for fast inference).
    Subsequent warm requests = ~5-7s.

Deploy:
    backend/.venv/bin/modal deploy backend/modal_deploy/serve_qwen_v2.py
"""
from __future__ import annotations

import modal

# ── Image: ML stack only — Tesseract was dropped to cut warm latency.
# Warning text + bbox + ABV + Net contents are now sourced from Haiku
# (CloudExtractor) running in parallel on the Vercel side; image DPI
# comes from the image_pipeline's EXIF read on the backend. Modal's job
# is exclusively the 4 trained Qwen LoRA fields.
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

adapter_volume_v2 = modal.Volume.from_name("ttb-qwen-adapter-v2", create_if_missing=True)
hf_cache_volume   = modal.Volume.from_name("ttb-qwen-hf-cache",   create_if_missing=True)

app = modal.App("ttb-qwen-extractor-v2")

# v2 system prompt — the 4 trained fields. Matches train_qwen.py exactly.
_SYSTEM_PROMPT_V2 = (
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
    # A100 (40GB) for warm Qwen-VL-7B BF16 generate. Empirically:
    #   - A10G: ~5-6s warm
    #   - L4:   ~6.8s warm (Lovelace helps FP8 more than BF16)
    #   - A100: ~3.0-3.2s warm wall (Modal-side); ~5s end-to-end through
    #           the Vercel fan-out with Haiku parallel
    #   - H100: tried 2026-05-28; observed ~3s Modal-side (no
    #           meaningful headroom over A100 for BF16-7B) while costing
    #           ~40% more per hour. Reverted in favour of /api/verify/stream
    #           which delivers the perceived-latency win architecturally.
    # Modal hourly rate is ~2.5x A10G but inference completes ~2.5x
    # faster too, so cost per request is comparable while the user-
    # visible warm verify lands decisively under the 5s target.
    gpu="A100",
    volumes={
        "/adapter":                  adapter_volume_v2,
        "/root/.cache/huggingface":  hf_cache_volume,
    },
    scaledown_window=300,
    timeout=900,
    min_containers=0,
)
class QwenExtractor:
    @modal.enter()
    def load_model(self):
        import torch
        from peft import PeftModel
        from transformers import (
            Qwen2_5_VLForConditionalGeneration,
            AutoProcessor,
        )

        BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
        ADAPTER_DIR = "/adapter/adapter"

        print(f"[Modal] Loading {BASE_MODEL} (BF16)...")
        base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            BASE_MODEL,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
        )
        # Single adapter, merge into base for fastest inference.
        print(f"[Modal] Loading v2 LoRA from {ADAPTER_DIR}...")
        self.model = PeftModel.from_pretrained(base, ADAPTER_DIR)
        self.model = self.model.merge_and_unload()
        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(BASE_MODEL)
        print(f"[Modal] Loaded. Free VRAM: "
              f"{torch.cuda.mem_get_info()[0]/1e9:.1f} GB")

        # Warm the GPU kernels with one throwaway inference so the FIRST
        # real /extract request doesn't pay PyTorch's autotune + CUDA
        # graph compile cost. Without this, the first warm request after
        # a cold start still takes 8-10s while kernels JIT, and the
        # Vercel side often times out (MODAL_TIMEOUT=8s) to Haiku-fallback
        # on what should be a Qwen-warm call.
        import io as _io
        import time as _time
        from PIL import Image as _Image
        t_warm = _time.time()
        try:
            dummy = _Image.new("RGB", (560, 560), color=(240, 240, 240))
            self._generate(dummy, "wine")
            print(f"[Modal] Kernel warmup done in {_time.time() - t_warm:.2f}s. Ready.")
        except Exception as e:
            # Non-fatal — first real request will pay the compile cost,
            # but the container is still functional.
            print(f"[Modal] Kernel warmup failed (non-fatal): {e}")

    # ────────────────────────────────────────────────────────────────────
    def _prep_image(self, img):
        from PIL import Image
        # 1.0 M pixel cap (was 1.5 M). Each Qwen-VL visual patch is 28x28
        # px, so ~1.0 M pixels = ~1280 patches = ~1280 vision tokens to
        # prefill. Dropping from 1.5 M to 1.0 M cuts vision-encoder +
        # prefill latency by ~30% on an A10G with negligible impact on
        # text recognition for label-sized typography.
        MAX_PIXELS = 1024 * 1024
        w, h = img.size
        if w * h > MAX_PIXELS:
            scale = (MAX_PIXELS / (w * h)) ** 0.5
            img = img.resize((max(int(w * scale), 28), max(int(h * scale), 28)), Image.LANCZOS)
        w, h = img.size
        w28, h28 = max((w // 28) * 28, 28), max((h // 28) * 28, 28)
        if (w28, h28) != (w, h):
            img = img.resize((w28, h28), Image.LANCZOS)
        return img

    def _generate(self, img, beverage_type: str) -> str:
        import torch
        msgs = [
            {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT_V2}]},
            {"role": "user",   "content": [
                {"type": "image", "image": img},
                {"type": "text",  "text": f"Beverage type: {beverage_type}. Extract per the schema."},
            ]},
        ]
        text = self.processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(
            text=[text], images=[img], padding=True, return_tensors="pt",
        ).to(self.model.device)
        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                # 256 tokens fits the 4-field JSON schema with room to
                # spare on a normal extraction; was 384 which left ~30%
                # idle decode time at the tail. Cuts ~1-1.5 s off warm
                # latency and brings p50 under the 5 s target.
                max_new_tokens=256,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self.processor.tokenizer.eos_token_id,
            )
        return self.processor.batch_decode(
            out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )[0]

    # ────────────────────────────────────────────────────────────────────
    @modal.method()
    def health(self) -> dict:
        """Warm-check probe. Returns immediately when the container is up
        and load_model() has finished, so a caller with a 5s budget can
        decide whether to trust Qwen for the current request or fall
        back to Haiku for this one while Modal finishes warming up.
        """
        return {"ok": True, "model_loaded": True}

    # ────────────────────────────────────────────────────────────────────
    @modal.method()
    def extract(self, image_bytes: bytes, beverage_type: str) -> dict:
        import io
        import time
        from PIL import Image

        t0 = time.time()
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        prepped = self._prep_image(pil_img)
        t_prep = time.time()

        # v2 LoRA on the 4 trained fields. Tesseract was removed from the
        # Modal pass to cut warm latency under 5s — ABV / Net contents /
        # Government Warning text + bbox now come from Haiku (running in
        # parallel on the Vercel side). DPI comes from the backend's
        # image_pipeline EXIF read. Modal's only job here is Qwen.
        raw_v2 = self._generate(prepped, beverage_type)
        t_done = time.time()

        return {
            "raw_v2": raw_v2,
            "tesseract": {},  # kept for backwards-compat with older Vercel clients
            "latency_sec": round(t_done - t0, 3),
            "latency_breakdown": {
                "prep": round(t_prep - t0, 3),
                "qwen": round(t_done - t_prep, 3),
            },
        }


@app.function(image=image, timeout=900)
@modal.fastapi_endpoint(method="POST", docs=True)
def extract_web(payload: dict) -> dict:
    import base64
    img_b64 = payload.get("image_b64")
    beverage = payload.get("beverage_type", "wine")
    if not img_b64:
        return {"error": "missing image_b64 in payload"}
    return QwenExtractor().extract.remote(base64.b64decode(img_b64), beverage)


@app.function(image=image, timeout=120)
@modal.fastapi_endpoint(method="GET", docs=True)
def health_web() -> dict:
    """GET /health_web — warm-check for the Qwen v2 container.

    Caller (the Vercel function's /api/health route) wraps this in a 5s
    httpx timeout. When the GPU container is warm, the round trip is
    sub-second and the caller marks Modal "warm". When the container is
    cold, this call blocks while load_model() runs (30-60s); the caller
    times out and marks Modal "cold". The warmup still completes
    server-side, so the *next* /api/verify finds Qwen ready.
    """
    import time
    t0 = time.time()
    try:
        result = QwenExtractor().health.remote()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "latency_sec": round(time.time() - t0, 3)}
    return {**result, "latency_sec": round(time.time() - t0, 3)}


@app.local_entrypoint()
def main(image_path: str, beverage_type: str = "wine"):
    from pathlib import Path
    image_bytes = Path(image_path).read_bytes()
    result = QwenExtractor().extract.remote(image_bytes, beverage_type)
    print()
    print(f"latency:    {result['latency_sec']}s")
    print(f"  breakdown:{result['latency_breakdown']}")
    print(f"raw_v2:     {result['raw_v2'][:400]}")
    print(f"tesseract:  {result['tesseract']}")
