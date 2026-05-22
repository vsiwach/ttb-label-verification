"""CloudExtractor — single-pass structured extraction from a hosted vision LLM.

Default provider is Anthropic Claude (model: claude-sonnet-4-6). The brief
also mentions OpenAI and Google as drop-in alternatives — those routes raise
a clear error pointing at this module for now.

Key design points:
- ONE API call per label. Tool-use guarantees a typed JSON response that
  maps straight onto ExtractedLabel.
- The system prompt is cached: the prompt is identical for every label, so
  prompt caching cuts cost and latency materially across a session/batch.
- The model is told to TRANSCRIBE the Government Warning EXACTLY, including
  any wording errors and the rendered case — paraphrase detection depends on
  the model NOT auto-correcting.
- The model reports observations + confidence only. It does NOT make a
  match/likely/flag decision — the rules engine does that.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from ..models import BeverageType
from .base import (
    ExtractedField,
    ExtractedLabel,
    InferenceError,
    LabelExtractor,
    WarningStyle,
)

logger = logging.getLogger("ttb.cloud")

_REPORT_TOOL = {
    "name": "report_label_extraction",
    "description": (
        "Report every field observed on the alcohol label image, plus the "
        "Government Warning text and style observations. You ONLY transcribe "
        "and report — do NOT decide whether the label is compliant."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "description": "Field name -> observation. Field names MUST be exactly: 'Brand name', 'Class & type', 'Alcohol content', 'Net contents', 'Bottler name/address', and optionally 'Country of origin'. If a field is not visible on the label, OMIT IT.",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "value":      {"type": "string", "description": "Exact text as printed on the label."},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "bbox":       {"type": "array",  "items": {"type": "integer"}, "minItems": 4, "maxItems": 4, "description": "[x, y, w, h] in pixels, optional"},
                    },
                    "required": ["value", "confidence"],
                },
            },
            "government_warning": {
                "type": "object",
                "properties": {
                    "present":         {"type": "boolean"},
                    "detected_text":   {"type": "string",  "description": "Government Warning text EXACTLY as printed. Preserve case and any wording errors. Do NOT auto-correct."},
                    "casing_all_caps": {"type": "boolean", "description": "Is the literal text 'GOVERNMENT WARNING' rendered in ALL CAPS?"},
                    "heading_bold":    {"type": "boolean", "description": "Is 'GOVERNMENT WARNING' bold?"},
                    "body_bold":       {"type": "boolean", "description": "Is the warning body (after the heading) bold? (It should NOT be.)"},
                    "approx_font_mm":  {"type": ["number", "null"], "description": "Estimated text height of the warning body in mm, if measurable from the image. null if uncertain."},
                    "contrast_ok":     {"type": "boolean"},
                    "separate_and_apart": {"type": "boolean"},
                    "bbox":            {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                },
                "required": ["present", "detected_text", "casing_all_caps", "heading_bold", "body_bold"],
            },
            "image_quality": {
                "type": "object",
                "properties": {
                    "score":   {"type": "number", "minimum": 0, "maximum": 1, "description": "Subjective legibility 0..1"},
                    "legible": {"type": "boolean"},
                    "note":    {"type": ["string", "null"]},
                },
                "required": ["score", "legible"],
            },
        },
        "required": ["fields", "government_warning", "image_quality"],
    },
}

_SYSTEM_PROMPT = (
    "You are a careful transcription assistant for U.S. TTB alcohol label review. "
    "Given ONE label panel image and the beverage type, you READ what is printed on "
    "this specific panel and REPORT it. You do NOT decide whether the label complies "
    "with regulations.\n\n"
    "CRITICAL: real COLAs are MULTI-IMAGE — front, back, neck, strip labels. The "
    "image you receive may be just one panel. If a mandatory field is not clearly "
    "present on THIS image, OMIT IT. Never guess; never substitute deposit codes "
    "(e.g. 'CA CRV', 'ME 15¢', 'IA 5c'), NOM/lot numbers, barcodes, or other "
    "regulatory marks for a mandatory field. Omission is correct when the field is "
    "on a panel you cannot see.\n\n"
    "Field definitions (record only when CLEARLY visible on this panel):\n"
    "  - Brand name: the registered brand/winery/distillery/brewery name on the "
    "label (often, but not always, less prominent than the SKU/product name).\n"
    "  - Class & type: the printed class/type designation (e.g. 'Kentucky Straight "
    "Bourbon Whiskey', 'India Pale Ale', 'California Red Table Wine').\n"
    "  - Alcohol content: printed as '%' Alc./Vol. / '% ABV' / 'Alc. N% by Vol.' / "
    "'N Proof'. NEVER substitute a deposit code or random number.\n"
    "  - Net contents: printed volume/mass (e.g. '750 mL', '12 FL OZ', '1 PINT'). "
    "Multi-unit displays like '1 PINT (16 FL OZ)' are normal — transcribe as printed. "
    "NEVER substitute a barcode, lot code, or 'CA CRV'-style deposit info.\n"
    "  - Bottler/Producer name & address: the line that begins with or contains "
    "'Bottled by', 'Brewed by', 'Produced by', 'Distilled by', or 'Imported by'.\n"
    "  - Country of origin: imports only; usually 'Product of <country>'.\n\n"
    "For the Government Warning panel: transcribe the printed text EXACTLY as it "
    "appears, INCLUDING any wording errors, case (UPPER, Title, lower), punctuation, "
    "and abbreviations. DO NOT auto-correct paraphrased text — paraphrase detection "
    "depends on you reporting what is actually printed. Then report:\n"
    '  - whether "GOVERNMENT WARNING" is rendered in all capital letters,\n'
    "  - whether the heading is bold,\n"
    "  - whether the body is bold (it should NOT be),\n"
    "  - an estimated body text height in mm if measurable, null if not,\n"
    "  - whether the warning has adequate contrast against the background,\n"
    "  - whether the warning is visually separate from other label copy.\n\n"
    "Call the report_label_extraction tool with your structured findings. Do not "
    "respond in plain text."
)


def _image_media_type(image_bytes: bytes) -> str:
    """Pragmatic content-type sniff for the four common label formats."""
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"GIF8"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # safe default for Anthropic vision


class CloudExtractor(LabelExtractor):
    def __init__(self, provider: str, model: str, api_key: str) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        if provider != "anthropic":
            # OpenAI / Google paths are intentionally not implemented in the
            # prototype. The seam is here when you need them.
            raise InferenceError(
                f"Cloud provider {provider!r} is not implemented in the prototype. "
                "Set CLOUD_PROVIDER=anthropic, or implement the adapter in "
                "backend/app/extractors/cloud.py."
            )
        # Lazy import: the SDK is only required when this path runs, so mock
        # / on-prem deployments don't need it installed.
        try:
            from anthropic import AsyncAnthropic  # type: ignore
        except ImportError as e:
            raise InferenceError(
                "anthropic SDK not installed. Run: pip install anthropic"
            ) from e
        self._client = AsyncAnthropic(api_key=api_key)

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        media_type = _image_media_type(image_bytes)
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")

        try:
            # 30s ceiling so a hung provider doesn't block the request thread.
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    # Cache the static system + tool definition. Prompt caching
                    # is a sizable cost/latency win across a session/batch.
                    system=[{
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    tools=[{**_REPORT_TOOL, "cache_control": {"type": "ephemeral"}}],
                    tool_choice={"type": "tool", "name": _REPORT_TOOL["name"]},
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                            {"type": "text", "text": f"Beverage type for this label: {beverage_type}. Call the tool with your findings."},
                        ],
                    }],
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError as e:
            raise InferenceError("cloud extractor timed out after 30s") from e
        except Exception as e:
            raise InferenceError(f"cloud extractor request failed: {e}") from e

        return _parse_response(response)


def _parse_response(response: Any) -> ExtractedLabel:
    """Pull the tool_use block out of the Claude response and map it into
    our internal ExtractedLabel dataclass."""
    tool_block = None
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", "") == _REPORT_TOOL["name"]:
            tool_block = block
            break
    if tool_block is None:
        raise InferenceError("cloud extractor returned no tool_use block")

    data: dict[str, Any] = tool_block.input if isinstance(tool_block.input, dict) else json.loads(tool_block.input or "{}")

    fields: dict[str, ExtractedField] = {}
    for name, obs in (data.get("fields") or {}).items():
        if not isinstance(obs, dict):
            continue
        bbox = obs.get("bbox")
        fields[name] = ExtractedField(
            value=str(obs.get("value", "")),
            confidence=float(obs.get("confidence", 0.0) or 0.0),
            bbox=tuple(bbox) if isinstance(bbox, list) and len(bbox) == 4 else None,  # type: ignore[arg-type]
        )

    gw = data.get("government_warning") or {}
    style = WarningStyle(
        casing_all_caps=bool(gw.get("casing_all_caps", False)),
        heading_bold=bool(gw.get("heading_bold", False)),
        body_bold=bool(gw.get("body_bold", False)),
        approx_font_mm=gw.get("approx_font_mm") if gw.get("approx_font_mm") is not None else None,
        contrast_ok=gw.get("contrast_ok") if gw.get("contrast_ok") is not None else None,
        separate_and_apart=gw.get("separate_and_apart") if gw.get("separate_and_apart") is not None else None,
        bbox=tuple(gw.get("bbox")) if isinstance(gw.get("bbox"), list) and len(gw.get("bbox", [])) == 4 else None,  # type: ignore[arg-type]
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
