"""ClaudeCodeExtractor — vision extraction via the `claude -p` CLI.

This adapter routes inference through Claude Code's headless mode
(`claude -p --output-format json --json-schema ...`) so the extraction
draws from a user's Claude Code / Max subscription **instead of**
pay-per-token API credits.

How it works:
  1. The image bytes are written to a short-lived temp file (the CLI takes a
     file path via the `@/absolute/path` mention syntax that Claude Code's
     Read tool resolves).
  2. We invoke `claude -p` with `--json-schema` (the same shape the cloud
     extractor produces via tool_use) and `--output-format json`.
  3. The CLI returns one JSON envelope per call; we read `structured_output`
     and map it to `ExtractedLabel`.

Trade-offs vs the API path:
  + No ANTHROPIC_API_KEY needed — auth flows through the user's logged-in
    Claude Code session, billed against their Max plan.
  + Same model, same vision capability.
  - Subprocess spawn adds a small per-request fixed cost (~100ms).
  - Output is post-validation via Claude Code's schema layer (still
    deterministic JSON).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import textwrap
from typing import Any

from ..models import BeverageType
from .base import (
    ExtractedField,
    ExtractedLabel,
    InferenceError,
    LabelExtractor,
    WarningStyle,
)

logger = logging.getLogger("ttb.claude_code")


# Same JSON schema as the cloud extractor's tool_use input_schema, expressed
# in plain JSON Schema for `claude -p --json-schema`.
_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "object",
            "description": (
                "Field name -> observation. Field names MUST be exactly: "
                "'Brand name', 'Class & type', 'Alcohol content', 'Net contents', "
                "'Bottler name/address', and optionally 'Country of origin'. "
                "OMIT any field that is not clearly visible on the image."
            ),
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "value":      {"type": "string", "description": "Exact text as printed on the label."},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["value", "confidence"],
            },
        },
        "government_warning": {
            "type": "object",
            "properties": {
                "present":         {"type": "boolean"},
                "detected_text":   {"type": "string", "description": "Government Warning text EXACTLY as printed. Preserve case and any wording errors. Do NOT auto-correct paraphrase."},
                "casing_all_caps": {"type": "boolean"},
                "heading_bold":    {"type": "boolean"},
                "body_bold":       {"type": "boolean"},
                "approx_font_mm":  {"type": ["number", "null"]},
                "contrast_ok":     {"type": "boolean"},
                "separate_and_apart": {"type": "boolean"},
            },
            "required": ["present", "detected_text", "casing_all_caps", "heading_bold", "body_bold"],
        },
        "image_quality": {
            "type": "object",
            "properties": {
                "score":   {"type": "number", "minimum": 0, "maximum": 1},
                "legible": {"type": "boolean"},
                "note":    {"type": ["string", "null"]},
            },
            "required": ["score", "legible"],
        },
    },
    "required": ["fields", "government_warning", "image_quality"],
}


_SYSTEM_PROMPT = textwrap.dedent("""\
    You are a careful transcription assistant for U.S. TTB alcohol label
    review. Given ONE label panel image and the beverage type, you READ
    what is printed on this specific panel and REPORT it. You do NOT decide
    whether the label complies with regulations.

    CRITICAL: real COLAs are MULTI-IMAGE — front, back, neck, strip labels.
    The image you receive may be just one panel. If a mandatory field is not
    clearly present on THIS image, OMIT IT. Never guess; never substitute
    deposit codes (e.g. 'CA CRV', 'ME 15¢'), NOM/lot numbers, barcodes, or
    other regulatory marks for a mandatory field.

    Field definitions (record only when CLEARLY visible on this panel):
      - Brand name: the registered brand on the label.
      - Class & type: the printed class/type designation.
      - Alcohol content: printed as '%' Alc./Vol. / '% ABV' / 'N Proof'.
        NEVER substitute a deposit code or random number.
      - Net contents: printed volume/mass (e.g. '750 mL', '12 FL OZ').
      - Bottler/Producer name & address: the line beginning with
        'Bottled by', 'Brewed by', 'Produced by', 'Distilled by', or
        'Imported by'.
      - Country of origin: imports only; 'Product of <country>'.

    For the Government Warning: transcribe the printed text EXACTLY as it
    appears, INCLUDING any wording errors, case, punctuation, and
    abbreviations. DO NOT auto-correct paraphrased text — paraphrase
    detection depends on you reporting what is actually printed.
""")


class ClaudeCodeExtractor(LabelExtractor):
    """Vision extraction via the `claude -p` headless CLI."""

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        # Write image to a temp file so the CLI can resolve it via the @path mention.
        suffix = ".webp" if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP" else ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(image_bytes)
            img_path = tf.name
        try:
            prompt = (
                f"Read the alcohol label image at @{img_path}. Beverage type "
                f"for this label: {beverage_type}. Extract every visible "
                f"mandatory field plus the Government Warning. Return ONLY "
                f"the JSON object matching the provided schema — no prose."
            )
            cmd = [
                "claude", "-p",
                "--output-format", "json",
                "--model", self.model,
                "--append-system-prompt", _SYSTEM_PROMPT,
                "--json-schema", json.dumps(_JSON_SCHEMA),
                "--add-dir", os.path.dirname(img_path),
                "--allowed-tools", "Read",
                "--dangerously-skip-permissions",
                "--no-session-persistence",
                prompt,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    raise InferenceError("claude-code extractor timed out after 60s")
            except FileNotFoundError as e:
                raise InferenceError(
                    "`claude` CLI not found on PATH. Install Claude Code first."
                ) from e

            if proc.returncode != 0:
                raise InferenceError(
                    f"claude -p exited {proc.returncode}: {stderr.decode()[:500]}"
                )
            return _parse_envelope(stdout.decode())
        finally:
            try:
                os.unlink(img_path)
            except OSError:
                pass


def _parse_envelope(raw: str) -> ExtractedLabel:
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InferenceError(f"claude -p returned non-JSON: {raw[:300]}") from e
    if envelope.get("is_error"):
        raise InferenceError(f"claude -p error: {envelope.get('result', '')[:300]}")
    data = envelope.get("structured_output") or {}
    if not data:
        # Fallback: try to parse the 'result' text as JSON
        try:
            data = json.loads(envelope.get("result") or "{}")
        except Exception:
            raise InferenceError("claude -p envelope had no structured_output")

    fields: dict[str, ExtractedField] = {}
    for name, obs in (data.get("fields") or {}).items():
        if not isinstance(obs, dict):
            continue
        fields[name] = ExtractedField(
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
