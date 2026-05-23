"""SFTExtractor — load a locally-fine-tuned VLM and extract per the same schema
the cloud/claude-code/onprem adapters use.

Supports two model families, dispatched by reading the bundle's manifest.json:

  - Qwen2.5-VL (LoRA over base 4-bit):
      backend/models/qwen2_5_vl_7b/
        ├── adapter/         # PEFT adapter + tokenizer + manifest
        └── eval_report.json

  - Donut (full fine-tune):
      backend/models/donut/
        ├── model/           # safetensors + processor + manifest
        └── eval_report.json

Heavy ML deps (torch, transformers, peft, bitsandbytes) are imported LAZILY
inside the loader so the rest of the backend (mock / cloud / claude-code /
onprem) doesn't need them installed. To run sft mode locally:

    pip install -r backend/requirements-sft.txt

The extractor returns the same ExtractedLabel shape as every other adapter —
the rules engine then makes match/likely/flag decisions against it.
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
# Dispatch + manifest reading
# ---------------------------------------------------------------------------

def _read_manifest(model_dir: Path) -> dict[str, Any]:
    """Find manifest.json under model_dir (one level deep)."""
    direct = model_dir / "manifest.json"
    if direct.exists():
        return json.loads(direct.read_text())
    for sub in ("adapter", "model"):
        candidate = model_dir / sub / "manifest.json"
        if candidate.exists():
            return json.loads(candidate.read_text())
    raise InferenceError(
        f"No manifest.json under {model_dir}. Expected {model_dir}/manifest.json "
        f"or {model_dir}/(adapter|model)/manifest.json."
    )


def _is_qwen_family(manifest: dict[str, Any]) -> bool:
    tag = (manifest.get("model_tag") or "").lower()
    base = (manifest.get("base_model") or "").lower()
    return "qwen" in tag or "qwen" in base


def _is_donut_family(manifest: dict[str, Any]) -> bool:
    tag = (manifest.get("model_tag") or "").lower()
    base = (manifest.get("base_model") or "").lower()
    return "donut" in tag or "donut" in base


# ---------------------------------------------------------------------------
# Qwen2.5-VL + LoRA loader
# ---------------------------------------------------------------------------

class _QwenLoader:
    """Lazy-loads Qwen2.5-VL base + LoRA adapter on first call."""

    def __init__(self, model_dir: Path, manifest: dict[str, Any]):
        self.model_dir = model_dir
        self.adapter_dir = model_dir / "adapter"
        if not self.adapter_dir.exists():
            raise InferenceError(f"Qwen adapter dir missing: {self.adapter_dir}")
        self.base_model_id = manifest.get("base_model", "unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit")
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
                BitsAndBytesConfig,
                Qwen2_5_VLForConditionalGeneration,
            )
        except ImportError as e:
            raise InferenceError(
                "SFT mode (Qwen) requires torch + transformers + peft + bitsandbytes. "
                "Install with: pip install -r backend/requirements-sft.txt"
            ) from e

        logger.info("Loading Qwen2.5-VL base %s + LoRA from %s", self.base_model_id, self.adapter_dir)
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.base_model_id,
            quantization_config=bnb,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        self._model = PeftModel.from_pretrained(base, str(self.adapter_dir))
        self._model.eval()
        self._processor = AutoProcessor.from_pretrained(str(self.adapter_dir))
        logger.info("Qwen2.5-VL + LoRA loaded.")

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
# Donut loader
# ---------------------------------------------------------------------------

class _DonutLoader:
    """Lazy-loads the fine-tuned Donut weights on first call."""

    def __init__(self, model_dir: Path, manifest: dict[str, Any]):
        self.model_dir = model_dir
        self.weights_dir = model_dir / "model"
        if not self.weights_dir.exists():
            raise InferenceError(f"Donut weights dir missing: {self.weights_dir}")
        self._model = None
        self._processor = None
        self._task_token_id: Optional[int] = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                DonutProcessor,
                VisionEncoderDecoderModel,
            )
        except ImportError as e:
            raise InferenceError(
                "SFT mode (Donut) requires torch + transformers. "
                "Install with: pip install -r backend/requirements-sft.txt"
            ) from e

        logger.info("Loading fine-tuned Donut from %s", self.weights_dir)
        self._processor = DonutProcessor.from_pretrained(str(self.weights_dir))
        self._model = VisionEncoderDecoderModel.from_pretrained(
            str(self.weights_dir), torch_dtype=torch.bfloat16
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = self._model.to(device)
        self._model.eval()
        # The fine-tune added <s_ttb> as the decoder start token.
        self._task_token_id = self._model.config.decoder_start_token_id
        logger.info("Donut loaded on %s.", device)

    def generate_json(self, image_bytes: bytes, beverage_type: str) -> str:
        self._ensure_loaded()
        import torch  # type: ignore
        from PIL import Image  # type: ignore

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        pixel_values = self._processor(images=[img], return_tensors="pt").pixel_values.to(
            self._model.dtype
        ).to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                pixel_values,
                decoder_start_token_id=self._task_token_id,
                max_length=768,
                do_sample=False,
                num_beams=1,
                early_stopping=True,
                eos_token_id=self._processor.tokenizer.eos_token_id,
                pad_token_id=self._processor.tokenizer.pad_token_id,
            )
        return self._processor.tokenizer.decode(out[0], skip_special_tokens=True)


# ---------------------------------------------------------------------------
# Parsing the raw decoder output into ExtractedLabel
# ---------------------------------------------------------------------------

def _try_parse_json(raw: str) -> Optional[dict[str, Any]]:
    """Best-effort: find the outermost {...} and json.loads it. Some models
    emit chain-of-thought or stray prose around the JSON."""
    if not raw:
        return None
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    try:
        return json.loads(raw[s : e + 1])
    except json.JSONDecodeError:
        # Strip trailing commas — common LM mistake
        cleaned = re.sub(r",(\s*[}\]])", r"\1", raw[s : e + 1])
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
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
    """Routes inference to a locally-fine-tuned VLM bundle."""

    def __init__(self, model_dir: str):
        d = Path(model_dir).expanduser().resolve()
        if not d.exists():
            raise InferenceError(f"SFT model_dir does not exist: {d}")
        self.model_dir = d
        manifest = _read_manifest(d)
        self.manifest = manifest

        if _is_qwen_family(manifest):
            self._loader: Any = _QwenLoader(d, manifest)
            self._family = "qwen"
        elif _is_donut_family(manifest):
            self._loader = _DonutLoader(d, manifest)
            self._family = "donut"
        else:
            raise InferenceError(
                f"Unknown SFT model family in manifest: {manifest!r}. "
                f"Supported: qwen, donut."
            )
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
            # Attach a truncated debug snippet so the operator can see what came back
            snippet = (raw or "")[:200].replace("\n", " ")
            label.image_quality_note = f"{label.image_quality_note}: {snippet!r}"
        return label
