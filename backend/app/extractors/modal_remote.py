"""ModalRemoteExtractor — hybrid Modal (Qwen v2) + Haiku adapter.

The TTB take-home reality after iteration:

  * We have clean labeled training data (TTB Public COLA Registry, N≈8,968)
    for 4 fields: Brand name, Class & type, Bottler name/address, Country of
    origin. Qwen2.5-VL-7B + v2 LoRA on Modal handles these end-to-end
    on-prem (privacy-first, validated 78% micro accuracy with the b817f82
    scorer, 2× better than Haiku zero-shot).

  * We do NOT have labeled training data of comparable scale for
    Alcohol content / Net contents / Government Warning. The COLA Cloud
    sample (~1,400 rows with those fields) was tried and produced v1, but
    v1 was worse than v2 on Brand/Class and hallucinated the warning.

  * So for those three fields, this extractor calls Anthropic Haiku in
    parallel with Modal. Tesseract on Modal still provides the warning
    bounding-box + image DPI used for the 27 CFR 16.22 type-size check.

Design story (Treasury-defensible):
  "When agencies provide clean labeled data for ABV / Net contents /
   Government Warning, those fields move on-prem via the same LoRA
   pipeline that already serves the four trained fields. Until then,
   the Haiku call is the bridge — flagged as an external dependency
   and accounted for in the data-handling section."

Wire it via:
    INFERENCE_MODE=modal
    MODAL_ENDPOINT_URL=https://<user>--ttb-qwen-extractor-v2-extract-web.modal.run
    ANTHROPIC_API_KEY=sk-ant-...    (enables the Haiku fallback for the 3 fields)
    CLOUD_MODEL=claude-haiku-4-5    (or any Anthropic vision model)

If ANTHROPIC_API_KEY is unset, ModalRemoteExtractor still works but
ABV / Net contents / Warning will come back empty (engine routes them
to needs-confirm — agent fills in manually).
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx

from ..models import BeverageType
from .base import (
    ExtractedField,
    ExtractedLabel,
    InferenceError,
    LabelExtractor,
    WarningStyle,
)
from .sft import _try_parse_json, _to_extracted_label

logger = logging.getLogger("ttb.modal_remote")


# Fields v2 is authoritative on.
_V2_FIELDS = {"Brand name", "Class & type", "Bottler name/address", "Country of origin"}
# Fields Haiku fills in (not in v2's training schema).
_HAIKU_FIELDS = {"Alcohol content", "Net contents"}


def _merge_label(
    v2_label: ExtractedLabel,
    tesseract: dict,
    haiku_label: ExtractedLabel | None,
) -> ExtractedLabel:
    """Combine the three observation sources into one ExtractedLabel.

    Precedence (per field, by source):
      Brand / Class / Bottler / Country  ← v2 (trained for these)
      Alcohol content / Net contents     ← Haiku (if available)
      Government Warning text + casing   ← Haiku (if available, else Tesseract)
      Warning bbox + DPI                 ← Tesseract (deterministic OCR + EXIF)
    """
    fields: dict[str, ExtractedField] = {
        name: ef for name, ef in v2_label.fields.items() if name in _V2_FIELDS
    }

    # ABV / Net contents — prefer Haiku, fall back to Tesseract regex if no Haiku.
    if haiku_label is not None:
        for name in _HAIKU_FIELDS:
            ef = haiku_label.fields.get(name)
            if ef and (ef.value or "").strip():
                fields[name] = ef
    # Tesseract regex fallback
    for tess_key, field_name in (("alcohol_content", "Alcohol content"),
                                 ("net_contents",    "Net contents")):
        if field_name in fields:
            continue  # already filled by Haiku
        val = (tesseract.get(tess_key) or "").strip()
        if val:
            fields[field_name] = ExtractedField(value=val, confidence=0.75)

    # Government Warning — prefer Haiku's verbatim transcription; fall back to
    # Tesseract OCR text when Haiku isn't configured.
    haiku_warning_text = (haiku_label.warning_text if haiku_label else "") or ""
    tess_warning_text  = (tesseract.get("warning_text") or "").strip()
    warning_text = haiku_warning_text.strip() or tess_warning_text
    warning_present = bool(warning_text) or (haiku_label is not None and haiku_label.warning_present)

    # Casing: Haiku has self-reported casing_all_caps from its tool output;
    # if missing or Haiku absent, derive from whatever text we have.
    haiku_style = haiku_label.warning_style if haiku_label else None
    if haiku_style is not None and warning_text:
        casing_all_caps = bool(haiku_style.casing_all_caps)
        heading_bold = bool(haiku_style.heading_bold)
        body_bold = bool(haiku_style.body_bold)
        contrast_ok = haiku_style.contrast_ok
        separate_and_apart = haiku_style.separate_and_apart
    else:
        casing_all_caps = warning_present and ("GOVERNMENT WARNING" in warning_text)
        heading_bold = False
        body_bold = False
        contrast_ok = None
        separate_and_apart = None

    # Bounding box for 27 CFR 16.22 type-size — Tesseract is the source.
    bbox_h_px = tesseract.get("warning_bbox_h_px")
    warning_bbox: tuple[int, int, int, int] | None = None
    if bbox_h_px is not None:
        warning_bbox = (0, 0, 0, int(bbox_h_px))

    warning_style: WarningStyle | None = None
    if warning_present or bbox_h_px is not None:
        warning_style = WarningStyle(
            casing_all_caps=casing_all_caps,
            heading_bold=heading_bold,
            body_bold=body_bold,
            contrast_ok=contrast_ok,
            separate_and_apart=separate_and_apart,
            bbox=warning_bbox,
            body_line_count=0,  # measurement is the preamble word height
        )

    dpi_val = tesseract.get("dpi")
    image_dpi = (int(dpi_val), int(dpi_val)) if dpi_val else None

    return ExtractedLabel(
        fields=fields,
        warning_text=warning_text,
        warning_present=warning_present,
        warning_style=warning_style,
        image_quality_score=v2_label.image_quality_score,
        image_legible=v2_label.image_legible,
        image_quality_note=v2_label.image_quality_note,
        image_dpi=image_dpi,
    )


class ModalRemoteExtractor(LabelExtractor):
    """Calls Modal (Qwen v2 + Tesseract) and optionally Anthropic Haiku in
    parallel; merges the two observation sources via asyncio.gather."""

    def __init__(
        self,
        endpoint_url: str,
        timeout: float = 60.0,
        anthropic_api_key: str = "",
        cloud_model: str = "claude-haiku-4-5",
    ):
        if not endpoint_url:
            raise InferenceError(
                "INFERENCE_MODE=modal but MODAL_ENDPOINT_URL is empty. "
                "Set MODAL_ENDPOINT_URL to the deploy's web URL (printed by `modal deploy`)."
            )
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout = timeout

        # Optional Haiku side-channel. If no key, the extractor still works —
        # just leaves the 3 cloud-tier fields empty (engine handles gracefully).
        self._haiku: LabelExtractor | None = None
        if anthropic_api_key:
            try:
                from .cloud import CloudExtractor  # lazy import — avoids hard SDK dep
                self._haiku = CloudExtractor(
                    provider="anthropic", model=cloud_model, api_key=anthropic_api_key,
                )
                logger.info("ModalRemoteExtractor: Haiku side-channel enabled (model=%s)", cloud_model)
            except Exception as e:
                logger.warning("Haiku side-channel disabled: %s", e)

        logger.info("ModalRemoteExtractor initialized → %s", self.endpoint_url)

    async def _call_modal(self, image_bytes: bytes, beverage_type: BeverageType) -> dict[str, Any]:
        payload = {
            "image_b64":     base64.b64encode(image_bytes).decode("ascii"),
            "beverage_type": str(beverage_type),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self.endpoint_url, json=payload)
        except httpx.TimeoutException as e:
            raise InferenceError(
                f"Modal endpoint timed out after {self.timeout}s. The container may be cold-starting "
                f"(first request takes 30-60 s while the 7B base loads). Retry or raise MODAL_TIMEOUT."
            ) from e
        except httpx.HTTPError as e:
            raise InferenceError(f"Modal HTTP error: {e}") from e

        if r.status_code != 200:
            raise InferenceError(f"Modal endpoint returned {r.status_code}: {r.text[:300]}")

        try:
            body: dict[str, Any] = r.json()
        except Exception as e:
            raise InferenceError(f"Modal endpoint returned non-JSON: {r.text[:300]}") from e

        if "error" in body:
            raise InferenceError(f"Modal endpoint error: {body['error']}")
        return body

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        # Fan out: Modal (Qwen v2 + Tesseract) and optionally Haiku — concurrently.
        tasks: list = [self._call_modal(image_bytes, beverage_type)]
        if self._haiku is not None:
            tasks.append(self._haiku.extract(image_bytes, beverage_type))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        modal_result = results[0]
        if isinstance(modal_result, Exception):
            raise modal_result

        haiku_result: ExtractedLabel | None = None
        if len(results) > 1:
            if isinstance(results[1], Exception):
                logger.warning("Haiku side-channel failed: %s", results[1])
            else:
                haiku_result = results[1]

        # Backwards-compat with the original deploy that returned a single raw_output
        if "raw_output" in modal_result and "raw_v2" not in modal_result:
            v2_label = _to_extracted_label(_try_parse_json(modal_result.get("raw_output", "")))
            tesseract = {}
        else:
            v2_label = _to_extracted_label(_try_parse_json(modal_result.get("raw_v2", "")))
            tesseract = modal_result.get("tesseract") or {}

        merged = _merge_label(v2_label, tesseract, haiku_result)

        latency = modal_result.get("latency_sec")
        breakdown = modal_result.get("latency_breakdown")
        if latency is not None:
            logger.info("Modal extract latency: %.2fs  breakdown=%s  haiku=%s",
                        latency, breakdown, "yes" if haiku_result else "no")
        return merged
