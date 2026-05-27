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

# ── Image: ML stack + Tesseract for the warning bbox + DPI observation ──────
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("tesseract-ocr", "libtesseract-dev")
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
        "pytesseract>=0.3.10",
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
    gpu="A10G",
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
        print(f"[Modal] Ready. Free VRAM: "
              f"{torch.cuda.mem_get_info()[0]/1e9:.1f} GB")

    # ────────────────────────────────────────────────────────────────────
    def _prep_image(self, img):
        from PIL import Image
        MAX_PIXELS = 1500 * 1024
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
                max_new_tokens=384,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self.processor.tokenizer.eos_token_id,
            )
        return self.processor.batch_decode(
            out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )[0]

    # ────────────────────────────────────────────────────────────────────
    # Tesseract — Alcohol content / Net contents / GW text + bbox + DPI
    # ────────────────────────────────────────────────────────────────────
    def _tesseract_observe(self, _qwen_img, raw_image_bytes: bytes) -> dict:
        """One OCR pass yields four observations:

          - alcohol_content (regex)
          - net_contents (regex)
          - warning_text (verbatim string from "GOVERNMENT WARNING:" onward)
          - warning_bbox_h_px (pixel height of the preamble — for 16.22 type-size)
          - dpi (from PIL EXIF; some scans expose it, phone photos usually don't)

        Tesseract gets the FULL-resolution image (not Qwen's downsized one).
        Tesseract degrades sharply below ~1200px tall on label-sized text;
        Qwen's 1.5M-pixel cap drops resolution far below that.
        """
        import io
        import re
        import pytesseract
        from PIL import Image
        from pytesseract import Output

        out = {
            "alcohol_content":   "",
            "net_contents":      "",
            "warning_text":      "",
            "warning_bbox_h_px": None,
            "dpi":               None,
        }

        # Open the original (full-res) image specifically for OCR.
        try:
            ocr_img = Image.open(io.BytesIO(raw_image_bytes)).convert("RGB")
            # Cap *up* — Tesseract benefits from at least 1200px tall when
            # body text is ~12-16px on the original. If the image is huge,
            # cap at 3000px to keep OCR latency bounded.
            w, h = ocr_img.size
            if h < 1200:
                scale = 1200 / h
                ocr_img = ocr_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            elif h > 3000:
                scale = 3000 / h
                ocr_img = ocr_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        except Exception as e:
            out["tesseract_error"] = f"open: {e}"
            return out

        # DPI from EXIF (read from raw bytes, not the resized OCR image)
        try:
            exif_img = Image.open(io.BytesIO(raw_image_bytes))
            dpi = exif_img.info.get("dpi")
            if dpi and isinstance(dpi, tuple) and dpi[1] > 0:
                out["dpi"] = float(dpi[1])
        except Exception:
            pass

        try:
            data = pytesseract.image_to_data(ocr_img, output_type=Output.DICT)
        except Exception as e:
            out["tesseract_error"] = str(e)
            return out

        words = data.get("text", [])
        n = len(words)
        full_text = " ".join(w for w in words if (w or "").strip())

        # ABV — match "X.X% Alc./Vol.", "X.X% ALC/VOL", "X% by vol", etc.
        # Tolerates comma decimals ("12,5%") and various Alc/Vol spellings.
        abv_m = re.search(
            r"(\d+(?:[.,]\d+)?)\s*%\s*(?:Alc\.?\s*(?:/|by\s+)?Vol\.?(?:ume)?|ALC\.?\s*/?\s*VOL\.?|alc\.?\s*/?\s*vol\.?)",
            full_text,
            flags=re.IGNORECASE,
        )
        if abv_m:
            value = abv_m.group(1).replace(",", ".")
            out["alcohol_content"] = f"{value}% Alc./Vol."
        else:
            # Proof fallback (US spirits): "94 Proof" or "90 PROOF"
            proof_m = re.search(r"(\d+(?:[.,]\d+)?)\s*Proof\b", full_text, flags=re.IGNORECASE)
            if proof_m:
                value = proof_m.group(1).replace(",", ".")
                out["alcohol_content"] = f"{value} Proof"

        # Net contents — match "750 mL", "12 fl oz", "1.5 L", "0.75 L", "1 pint"
        net_m = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(mL|ml|ML|L\b|fl\.?\s*oz|FL\.?\s*OZ|pints?|gal(?:lons?)?|liter|litre)",
            full_text,
        )
        if net_m:
            value = net_m.group(1).replace(",", ".")
            unit = net_m.group(2)
            # Normalize unit casing for readability
            unit_norm = re.sub(r"\s+", " ", unit).strip()
            if re.match(r"^ml$", unit_norm, flags=re.IGNORECASE):
                unit_norm = "mL"
            elif re.match(r"^l$", unit_norm, flags=re.IGNORECASE):
                unit_norm = "L"
            elif re.match(r"^fl\.?\s*oz$", unit_norm, flags=re.IGNORECASE):
                unit_norm = "fl oz"
            out["net_contents"] = f"{value} {unit_norm}"

        # Government Warning — find "GOVERNMENT" then the next non-empty
        # token starting with "WARNING". Tesseract sprinkles empty strings
        # between real words; we walk past them.
        warning_start_idx = None
        for i in range(n):
            wi = (words[i] or "").strip().upper()
            if wi != "GOVERNMENT":
                continue
            # Find next non-empty token
            for j in range(i + 1, n):
                wj = (words[j] or "").strip().upper()
                if not wj:
                    continue
                if wj.startswith("WARNING"):
                    warning_start_idx = i
                    h = max(int(data["height"][i] or 0), int(data["height"][j] or 0))
                    if h > 0:
                        out["warning_bbox_h_px"] = h
                break
            if warning_start_idx is not None:
                break

        if warning_start_idx is not None:
            # Collect from the preamble through end-of-OCR, dropping when we
            # drift far below the preamble vertically (heuristic for "left
            # the warning region").
            preamble_h = max(int(data["height"][warning_start_idx] or 0), 1)
            text_words = []
            last_y = int(data["top"][warning_start_idx] or 0)
            for k in range(warning_start_idx, n):
                w = (words[k] or "").strip()
                if not w:
                    continue
                y = int(data["top"][k] or 0)
                if y - last_y > preamble_h * 6:
                    break
                text_words.append(w)
                last_y = y
            out["warning_text"] = " ".join(text_words)

        return out

    # ────────────────────────────────────────────────────────────────────
    @modal.method()
    def extract(self, image_bytes: bytes, beverage_type: str) -> dict:
        import io
        import time
        from PIL import Image

        t0 = time.time()
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        prepped = self._prep_image(pil_img)

        # Pass 1 — v2 LoRA: the 4 trained fields
        raw_v2 = self._generate(prepped, beverage_type)
        t_v2 = time.time()

        # Pass 2 — Tesseract on CPU (could be moved to a thread for true
        # parallelism with the GPU pass; on a single warm A10G request the
        # GIL won't matter much since GPU work releases the GIL).
        tess = self._tesseract_observe(prepped, image_bytes)
        t_tess = time.time()

        return {
            "raw_v2": raw_v2,
            "tesseract": tess,
            "latency_sec": round(t_tess - t0, 3),
            "latency_breakdown": {
                "v2":        round(t_v2 - t0,    3),
                "tesseract": round(t_tess - t_v2, 3),
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
