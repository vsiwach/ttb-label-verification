"""SFTExtractor — load the locally-fine-tuned Qwen2.5-VL LoRA bundle and
extract per the same schema the cloud/claude-code/onprem adapters use.

Bundle layout (see backend/models/qwen2_5_vl_7b/):
    backend/models/qwen2_5_vl_7b/
      ├── adapter/         # PEFT adapter + tokenizer + manifest.json
      └── eval_report.json # per-field accuracy from the notebook eval

Heavy ML deps (torch, transformers, peft) are imported LAZILY
inside the loader so the rest of the backend (mock / cloud / claude-code /
onprem) doesn't need them installed. To run sft mode locally:

    pip install -r backend/requirements-sft.txt

The extractor returns the same ExtractedLabel shape as every other adapter —
the rules engine then makes match/likely/flag decisions against it.

Runtime: loads the official BF16 base + applies the LoRA adapter, then
merges LoRA into base for fast inference. Works on CUDA, MPS (Mac), and
CPU — only speed differs (~3 s, ~30 s, ~5 min/image respectively).
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

    Loads the official Qwen base in BF16 (matches training-time dtype) and
    applies the LoRA adapter on top. Then merges LoRA into base for fast
    inference. Works identically on CUDA, MPS, and CPU — only speed differs.
    """

    BASE_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"

    def __init__(self, model_dir: Path, manifest: dict[str, Any]):
        self.model_dir = model_dir
        self.adapter_dir = model_dir / "adapter"
        if not self.adapter_dir.exists():
            raise InferenceError(f"Qwen adapter dir missing: {self.adapter_dir}")
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
            device, attn = "auto", "sdpa"
        elif torch.backends.mps.is_available():
            device, attn = "mps", "eager"
        else:
            device, attn = "cpu", "eager"

        logger.info("Loading %s (BF16, device=%s) + LoRA from %s",
                    self.BASE_MODEL, device, self.adapter_dir)
        base = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.BASE_MODEL,
            torch_dtype=torch.bfloat16,
            device_map=device if device == "auto" else None,
            low_cpu_mem_usage=True,
            attn_implementation=attn,
        )
        if device != "auto":
            base = base.to(device)
        self._model = PeftModel.from_pretrained(base, str(self.adapter_dir))
        # Merge LoRA into base — eliminates per-call LoRA overhead. Safe in BF16.
        self._model = self._model.merge_and_unload()
        self._model.eval()
        self._processor = AutoProcessor.from_pretrained(self.BASE_MODEL)
        logger.info("Qwen2.5-VL + LoRA loaded and merged.")

    def generate_json(self, image_bytes: bytes, beverage_type: str) -> str:
        self._ensure_loaded()
        import torch  # type: ignore
        from PIL import Image  # type: ignore

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Cap image resolution: Qwen2.5-VL otherwise tiles at native res and
        # produces 4000+ visual tokens → quadratic-slow attention. 640x640
        # area ≈ 400 visual tokens, plenty for label OCR. Matches the
        # _resize_for_eval in notebooks/eval_qwen_drive.ipynb and the
        # equivalent in backend/modal_deploy/serve_qwen_v2.py (the active
        # production endpoint; v1 lives in archive/modal_deploy/).
        MAX_PIXELS = 640 * 640
        w, h = img.size
        if w * h > MAX_PIXELS:
            scale = (MAX_PIXELS / (w * h)) ** 0.5
            img = img.resize((max(int(w * scale), 28), max(int(h * scale), 28)), Image.LANCZOS)
        w, h = img.size
        w28, h28 = max((w // 28) * 28, 28), max((h // 28) * 28, 28)
        if (w28, h28) != (w, h):
            img = img.resize((w28, h28), Image.LANCZOS)

        messages = [
            {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT}]},
            {"role": "user", "content": [
                {"type": "image", "image": img},
                {"type": "text", "text": f"Beverage type: {beverage_type}. Extract per the schema."},
            ]},
        ]
        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._processor(text=[text], images=[img], padding=True, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=384,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=self._processor.tokenizer.eos_token_id,
            )
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


# Canonical field names the rules engine expects. Models often emit snake_case
# or alternative names (brand_name, volume, bottled_by, product_type, etc).
# This map normalizes them to the schema names so the engine + scorer see
# consistent keys regardless of which model produced the JSON.
_FIELD_ALIASES = {
    "Brand name": (
        "brand_name", "brand", "name", "product_name", "brewery_name",
        "winery_name", "distillery_name", "brewery", "distillery",
        "sub_brand", "fanciful_name",
    ),
    "Class & type": (
        "class_type", "class", "type", "product_type", "beverage_type",
        "wine_type", "beer_style", "spirit_type", "style", "varietal",
        "category", "designation",
    ),
    "Alcohol content": (
        "alcohol_content", "alcohol", "abv", "alc", "alc_vol", "alcohol_by_volume",
        "alcoholic_strength", "proof",
    ),
    "Net contents": (
        "net_contents", "volume", "net_volume", "contents", "size",
        "volume_ml", "fluid_volume", "fill", "package_size",
    ),
    "Bottler name/address": (
        "bottler_name_address", "bottler", "bottled_by", "producer",
        "produced_by", "distiller", "distilled_by", "importer", "imported_by",
        "manufacturer", "producer_address", "bottler_address",
        "produced_and_bottled_by", "distilled_and_bottled_by",
    ),
    "Country of origin": (
        "country_of_origin", "origin", "country", "product_of", "imported_from",
        "product_origin", "made_in",
    ),
}

# Build reverse lookup: alias_lowercase → canonical
_REVERSE_ALIASES: dict[str, str] = {}
for canonical, aliases in _FIELD_ALIASES.items():
    _REVERSE_ALIASES[canonical.lower()] = canonical
    _REVERSE_ALIASES[canonical.lower().replace(" ", "_")] = canonical
    _REVERSE_ALIASES[canonical.lower().replace(" & ", "_")] = canonical
    _REVERSE_ALIASES[canonical.lower().replace(" ", "")] = canonical
    for a in aliases:
        _REVERSE_ALIASES[a.lower()] = canonical
        _REVERSE_ALIASES[a.lower().replace("_", " ")] = canonical
        _REVERSE_ALIASES[a.lower().replace("_", "")] = canonical


def _canonicalize_field_name(name: str) -> Optional[str]:
    """Map a model-emitted field key to the rules-engine canonical name.
    Returns None if the name doesn't match any known field — caller drops it.
    Case-insensitive, snake_case-insensitive, '&'-vs-'and'-insensitive."""
    if not name:
        return None
    key = name.strip().lower()
    if key in _REVERSE_ALIASES:
        return _REVERSE_ALIASES[key]
    # Try without underscores / extra spaces
    nuked = re.sub(r"[\s_\-]+", "", key)
    for k, v in _REVERSE_ALIASES.items():
        if re.sub(r"[\s_\-]+", "", k) == nuked:
            return v
    return None


def _coerce_confidence(v: Any) -> float:
    """Models sometimes emit confidence as a string ('high', '0.9', '90%')
    or as None; coerce to a float in [0, 1]. Unknown strings default to 0.7
    (treated as moderate confidence — the rules engine still demotes low-
    confidence matches via its own < 0.60 threshold)."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return max(0.0, min(1.0, float(v)))
    if isinstance(v, str):
        s = v.strip().lower().rstrip("%")
        # Numeric string ("0.9", "90")
        try:
            n = float(s)
            if n > 1.0:
                n /= 100.0
            return max(0.0, min(1.0, n))
        except ValueError:
            pass
        # Descriptor strings
        return {
            "high":     0.90, "very high": 0.95, "certain": 0.99,
            "medium":   0.70, "moderate":  0.70, "average":  0.70,
            "low":      0.40, "uncertain": 0.30, "unsure":   0.30,
        }.get(s, 0.70)
    return 0.7


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
    for raw_name, obs in (data.get("fields") or {}).items():
        if not isinstance(obs, dict):
            continue
        # Normalize the model's field key to the canonical schema name.
        # If it doesn't match anything we know, drop it — the engine only
        # scores against known field names, so unknown extras are noise.
        canonical = _canonicalize_field_name(str(raw_name))
        if canonical is None:
            continue
        # If we already have a value for this canonical name (e.g. model
        # emitted both "brand_name" AND "Brand name"), keep the higher
        # confidence one.
        new_field = ExtractedField(
            value=str(obs.get("value", "")),
            confidence=_coerce_confidence(obs.get("confidence")),
        )
        existing = fields.get(canonical)
        if existing is None or new_field.confidence > existing.confidence:
            fields[canonical] = new_field

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
