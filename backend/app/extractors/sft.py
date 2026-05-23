"""SFTExtractor — load the locally-fine-tuned Qwen2.5-VL LoRA bundle and
extract per the same schema the cloud/claude-code/onprem adapters use.

Bundle layout (see backend/models/qwen2_5_vl_7b/):
    backend/models/qwen2_5_vl_7b/
      ├── adapter/         # PEFT adapter + tokenizer + manifest.json
      └── eval_report.json # per-field accuracy from the notebook eval

Heavy ML deps (torch, transformers, peft, bitsandbytes) are imported LAZILY
inside the loader so the rest of the backend (mock / cloud / claude-code /
onprem) doesn't need them installed. To run sft mode locally:

    pip install -r backend/requirements-sft.txt

The extractor returns the same ExtractedLabel shape as every other adapter —
the rules engine then makes match/likely/flag decisions against it.

Runtime selection:
  - CUDA available  → loads in 4-bit via bitsandbytes (matches training)
  - No CUDA (Mac)   → falls back to bf16/fp16 base (~14 GB unified memory)
                      since bitsandbytes is CUDA-only. Slower but works.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from ..models import BeverageType
from .base import (
    ExtractedField,
    ExtractedLabel,
    InferenceError,
    LabelExtractor,
    WarningStyle,
)

logger = logging.getLogger("ttb.sft")


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


# ---------------------------------------------------------------------------
# Manifest reading
# ---------------------------------------------------------------------------

def _read_manifest(model_dir: Path) -> dict[str, Any]:
    """Find manifest.json under model_dir (direct or one level deep)."""
    direct = model_dir / "manifest.json"
    if direct.exists():
        return json.loads(direct.read_text())
    for sub in ("adapter",):
        candidate = model_dir / sub / "manifest.json"
        if candidate.exists():
            return json.loads(candidate.read_text())
    raise InferenceError(
        f"No manifest.json under {model_dir}. Expected {model_dir}/manifest.json "
        f"or {model_dir}/adapter/manifest.json."
    )


def _is_qwen_family(manifest: dict[str, Any]) -> bool:
    tag = (manifest.get("model_tag") or "").lower()
    base = (manifest.get("base_model") or "").lower()
    return "qwen" in tag or "qwen" in base


# ---------------------------------------------------------------------------
# Qwen2.5-VL + LoRA loader
# ---------------------------------------------------------------------------

class _QwenLoader:
    """Lazy-loads Qwen2.5-VL base + LoRA adapter on first call.

    On CUDA hosts: loads in 4-bit via bitsandbytes (matches training).
    On non-CUDA hosts (e.g. Mac M-series): loads base in bf16/fp16 — bnb is
    CUDA-only. Inference is slower but functionally correct.
    """

    def __init__(self, model_dir: Path, manifest: dict[str, Any]):
        self.model_dir = model_dir
        self.adapter_dir = model_dir / "adapter"
        if not self.adapter_dir.exists():
            raise InferenceError(f"Qwen adapter dir missing: {self.adapter_dir}")
        # The bundle's base_model points at the bnb-prequantized weights,
        # which only loadable with bitsandbytes on CUDA. On non-CUDA hosts
        # we substitute the full-precision base of the same model.
        bundle_base = manifest.get("base_model", "unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit")
        self.bundle_base = bundle_base
        self.full_precision_base = "Qwen/Qwen2.5-VL-7B-Instruct"
        self._model = None
        self._processor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # type: ignore
            from peft import PeftModel  # type: ignore
            from transformers import (  # type: ignore
                AutoProcessor,
                Qwen2_5_VLForConditionalGeneration,
            )
        except ImportError as e:
            raise InferenceError(
                "SFT mode requires torch + transformers + peft. "
                "Install with: pip install -r backend/requirements-sft.txt"
            ) from e

        if torch.cuda.is_available():
            self._load_cuda_4bit(torch, PeftModel, AutoProcessor, Qwen2_5_VLForConditionalGeneration)
        else:
            self._load_non_cuda_fp(torch, PeftModel, AutoProcessor, Qwen2_5_VLForConditionalGeneration)

    def _load_cuda_4bit(self, torch, PeftModel, AutoProcessor, Qwen2_5_VLForConditionalGeneration):
        try:
            from transformers import BitsAndBytesConfig  # type: ignore
        except ImportError as e:
            raise InferenceError(
                "CUDA detected but bitsandbytes/BitsAndBytesConfig missing. "
                "pip install bitsandbytes>=0.44"
            ) from e
        logger.info("Loading Qwen2.5-VL 4-bit base %s + LoRA from %s", self.bundle_base, self.adapter_dir)
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.bundle_base,
            quantization_config=bnb,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        self._model = PeftModel.from_pretrained(base, str(self.adapter_dir))
        self._model.eval()
        self._processor = AutoProcessor.from_pretrained(str(self.adapter_dir))
        logger.info("Qwen2.5-VL + LoRA loaded (CUDA, 4-bit).")

    def _load_non_cuda_fp(self, torch, PeftModel, AutoProcessor, Qwen2_5_VLForConditionalGeneration):
        # bnb is CUDA-only. On Mac (MPS) or CPU, load the full-precision base.
        dtype = torch.bfloat16 if torch.backends.mps.is_available() else torch.float32
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(
            "No CUDA — loading FULL-PRECISION base %s (dtype=%s, device=%s) + LoRA. "
            "Inference will be slow (~30-60s/image on Mac M-series).",
            self.full_precision_base, dtype, device,
        )
        base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.full_precision_base,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        ).to(device)
        self._model = PeftModel.from_pretrained(base, str(self.adapter_dir))
        self._model.eval()
        self._processor = AutoProcessor.from_pretrained(str(self.adapter_dir))
        logger.info("Qwen2.5-VL + LoRA loaded (%s, full-precision).", device)

    def generate_json(self, image_bytes: bytes, beverage_type: str) -> str:
        self._ensure_loaded()
        import torch  # type: ignore
        from PIL import Image  # type: ignore

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        messages = [
            {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT}]},
            {"role": "user", "content": [
                {"type": "image", "image": img},
                {"type": "text", "text": f"Beverage type: {beverage_type}. Extract per the schema."},
            ]},
        ]
        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._processor(text=text, images=[img], return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(**inputs, max_new_tokens=512, do_sample=False)
        decoded = self._processor.batch_decode(
            out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )[0]
        return decoded


# ---------------------------------------------------------------------------
# Parsing the raw decoder output into ExtractedLabel
# ---------------------------------------------------------------------------

def _try_parse_json(raw: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON recovery from VLM output.

    Models trained on JSON targets occasionally emit:
      - chain-of-thought prose around the JSON
      - markdown code fences (```json ... ```)
      - trailing commas before } or ]
      - truncated output (missing closing braces)
      - multiple candidate JSON objects
      - smart quotes ("" '') instead of plain ASCII
      - control characters that break json.loads

    We try increasingly aggressive recovery strategies and return the first
    that parses. Returns None only if nothing recoverable.
    """
    if not raw:
        return None

    # Strategy 0: strip markdown code fences if present
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    s = text.find("{")
    e = text.rfind("}")
    if s == -1:
        return None

    # If we never see a closing brace, manufacture one (truncated output)
    if e == -1 or e < s:
        text = text[s:] + "}"
        s = 0
        e = len(text) - 1

    candidate = text[s : e + 1]

    # Normalize common issues before parsing attempts
    def _normalize(c: str) -> str:
        c = c.replace("“", '"').replace("”", '"')   # smart double quotes
        c = c.replace("‘", "'").replace("’", "'")   # smart single quotes
        c = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", c)    # ASCII control chars
        return c

    candidate = _normalize(candidate)

    # Strategy 1: parse as-is
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip trailing commas before } or ]
    cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 3: append missing closing braces (count { vs } and balance)
    opens  = candidate.count("{")
    closes = candidate.count("}")
    if opens > closes:
        balanced = re.sub(r",(\s*[}\]])", r"\1", candidate + "}" * (opens - closes))
        try:
            return json.loads(balanced)
        except json.JSONDecodeError:
            pass

    # Strategy 4: walk the string and try to parse up to each closing brace.
    # Picks the longest prefix that's valid JSON. Useful when the model
    # generates valid JSON then keeps going with garbage.
    for end in range(len(candidate) - 1, max(0, len(candidate) - 5000), -1):
        if candidate[end] != "}":
            continue
        try:
            sub = re.sub(r",(\s*[}\]])", r"\1", candidate[: end + 1])
            return json.loads(sub)
        except json.JSONDecodeError:
            continue

    return None


def _to_extracted_label(data: Optional[dict[str, Any]]) -> ExtractedLabel:
    if not data:
        return ExtractedLabel(
            warning_text="",
            warning_present=False,
            warning_style=WarningStyle(
                casing_all_caps=False, heading_bold=False, body_bold=False
            ),
            image_quality_score=0.5,
            image_legible=True,
            image_quality_note="SFT model output was not valid JSON",
        )

    fields: dict[str, ExtractedField] = {}
    for name, obs in (data.get("fields") or {}).items():
        if not isinstance(obs, dict):
            continue
        fields[str(name)] = ExtractedField(
            value=str(obs.get("value", "")),
            confidence=float(obs.get("confidence", 0.0) or 0.0),
        )

    gw = data.get("government_warning") or {}
    style = WarningStyle(
        casing_all_caps=bool(gw.get("casing_all_caps", False)),
        heading_bold=bool(gw.get("heading_bold", False)),
        body_bold=bool(gw.get("body_bold", False)),
        approx_font_mm=gw.get("approx_font_mm"),
        contrast_ok=gw.get("contrast_ok"),
        separate_and_apart=gw.get("separate_and_apart"),
    )
    iq = data.get("image_quality") or {}
    return ExtractedLabel(
        fields=fields,
        warning_text=str(gw.get("detected_text", "")),
        warning_present=bool(gw.get("present", False)),
        warning_style=style,
        image_quality_score=float(iq.get("score", 0.7) or 0.7),
        image_legible=bool(iq.get("legible", True)),
        image_quality_note=iq.get("note"),
    )


# ---------------------------------------------------------------------------
# Public extractor
# ---------------------------------------------------------------------------

class SFTExtractor(LabelExtractor):
    """Routes inference to the locally-fine-tuned Qwen2.5-VL LoRA bundle."""

    def __init__(self, model_dir: str):
        d = Path(model_dir).expanduser().resolve()
        if not d.exists():
            raise InferenceError(f"SFT model_dir does not exist: {d}")
        self.model_dir = d
        manifest = _read_manifest(d)
        self.manifest = manifest

        if not _is_qwen_family(manifest):
            raise InferenceError(
                f"Unsupported SFT model family in manifest: {manifest!r}. "
                f"This extractor currently only supports Qwen2.5-VL LoRA bundles."
            )
        self._loader: Any = _QwenLoader(d, manifest)
        self._family = "qwen"
        logger.info("SFTExtractor initialized: family=%s dir=%s", self._family, d)

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        # Inference is blocking + CPU/GPU heavy; run in a thread so the event loop
        # stays responsive (matches the pattern in claude_code.py and cloud.py).
        loop = asyncio.get_running_loop()
        try:
            raw = await loop.run_in_executor(
                None, self._loader.generate_json, image_bytes, str(beverage_type)
            )
        except InferenceError:
            raise
        except Exception as e:  # noqa: BLE001
            raise InferenceError(f"SFT generation failed: {type(e).__name__}: {e}") from e

        parsed = _try_parse_json(raw)
        label = _to_extracted_label(parsed)
        if parsed is None and label.image_quality_note:
            snippet = (raw or "")[:200].replace("\n", " ")
            label.image_quality_note = f"{label.image_quality_note}: {snippet!r}"
        return label
