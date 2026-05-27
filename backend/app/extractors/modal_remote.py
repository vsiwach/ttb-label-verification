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
    haiku_label: ExtractedLabel | None,
    tesseract: dict | None,
) -> ExtractedLabel:
    """Combine the three observation sources into one ExtractedLabel.

    Precedence (per field, by source):
      Brand / Class / Bottler / Country  ← v2 (trained for these)
      Alcohol content / Net contents     ← Haiku semantic > Tesseract regex fallback
      Government Warning text + casing   ← Haiku (semantic reads casing/contrast)
      Warning bbox                       ← Tesseract (DETERMINISTIC) > Haiku fallback
      Image DPI                          ← Tesseract EXIF > image_pipeline EXIF (main.py)

    Tesseract is the deterministic source for the 16.22 type-size
    inputs (bbox + DPI). When it returns a non-empty bbox we trust it
    over Haiku's bbox so re-running the same image yields the same mm
    measurement. Haiku still owns the semantic warning checks (casing,
    contrast, separate-and-apart) — those need a vision-language model.
    """
    fields: dict[str, ExtractedField] = {
        name: ef for name, ef in v2_label.fields.items() if name in _V2_FIELDS
    }
    tesseract = tesseract or {}

    # ABV / Net contents — prefer Haiku semantic; fall back to Tesseract regex.
    if haiku_label is not None:
        for name in _HAIKU_FIELDS:
            ef = haiku_label.fields.get(name)
            if ef and (ef.value or "").strip():
                fields[name] = ef
    for tess_key, field_name in (("alcohol_content", "Alcohol content"),
                                 ("net_contents",    "Net contents")):
        if field_name in fields:
            continue  # already filled by Haiku
        val = (tesseract.get(tess_key) or "").strip()
        if val:
            fields[field_name] = ExtractedField(value=val, confidence=0.75)

    # Government Warning text + casing — Haiku is the semantic source.
    haiku_warning_text = (haiku_label.warning_text if haiku_label else "") or ""
    tess_warning_text  = (tesseract.get("warning_text") or "").strip()
    warning_text       = haiku_warning_text.strip() or tess_warning_text
    warning_present    = bool(warning_text) or (haiku_label is not None and haiku_label.warning_present)

    # bbox + body_line_count: Tesseract is the deterministic source.
    # Pairing matters — Tesseract returns the preamble word height with
    # body_line_count=0; Haiku returns full-region bbox with its own
    # body_line_count. The rule engine divides bbox.h by (body_line_count
    # + 1) so the pairing must be consistent end-to-end.
    bbox_h_px = tesseract.get("warning_bbox_h_px")
    if bbox_h_px is not None and bbox_h_px > 0:
        bbox_source = "tesseract"
        warning_bbox: tuple[int, int, int, int] | None = (0, 0, 0, int(bbox_h_px))
        body_line_count: int | None = 0  # measurement is the preamble word height
    elif haiku_label and haiku_label.warning_style and haiku_label.warning_style.bbox:
        bbox_source = "haiku"
        warning_bbox = haiku_label.warning_style.bbox
        body_line_count = haiku_label.warning_style.body_line_count
    else:
        bbox_source = "none"
        warning_bbox = None
        body_line_count = None

    # Casing / contrast / separate-and-apart from Haiku when available.
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

    warning_style: WarningStyle | None = None
    if warning_present or warning_bbox is not None:
        warning_style = WarningStyle(
            casing_all_caps=casing_all_caps,
            heading_bold=heading_bold,
            body_bold=body_bold,
            contrast_ok=contrast_ok,
            separate_and_apart=separate_and_apart,
            bbox=warning_bbox,
            body_line_count=body_line_count,
        )

    # DPI from Tesseract's EXIF read (if it found one). image_pipeline
    # in main.py ALSO reads EXIF and overrides this field; we set it
    # here only as a fallback for the SDK path.
    dpi_val = tesseract.get("dpi")
    image_dpi: tuple[int, int] | None = (
        (int(dpi_val), int(dpi_val)) if dpi_val else None
    )

    logger.debug("merge: bbox source=%s, line_count=%s, dpi=%s",
                 bbox_source, body_line_count, image_dpi)

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
        tesseract_url: str = "",
    ):
        if not endpoint_url:
            raise InferenceError(
                "INFERENCE_MODE=modal but MODAL_ENDPOINT_URL is empty. "
                "Set MODAL_ENDPOINT_URL to the deploy's web URL (printed by `modal deploy`)."
            )
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout = timeout
        self.tesseract_url = tesseract_url.rstrip("/") if tesseract_url else ""

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

        logger.info(
            "ModalRemoteExtractor initialized → qwen=%s tesseract=%s",
            self.endpoint_url, self.tesseract_url or "(disabled)",
        )

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

    async def _call_tesseract(self, image_bytes: bytes) -> dict[str, Any]:
        """POST the image to the CPU-only Tesseract Modal function.

        Failures here are non-fatal — we log and return an empty dict
        so the merge falls back to Haiku's bbox. The Tesseract function
        is the *deterministic* source but the engine still works
        without it (just non-deterministic on the bbox/DPI inputs).
        """
        if not self.tesseract_url:
            return {}
        payload = {"image_b64": base64.b64encode(image_bytes).decode("ascii")}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self.tesseract_url, json=payload)
            if r.status_code != 200:
                logger.warning("Tesseract endpoint returned %s: %s", r.status_code, r.text[:200])
                return {}
            body: dict[str, Any] = r.json()
            if "error" in body:
                logger.warning("Tesseract endpoint error: %s", body["error"])
                return {}
            return body
        except Exception as e:
            logger.warning("Tesseract call failed (non-fatal): %s", e)
            return {}

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        # Three-way fan-out — all concurrent under one gather:
        #   1. Modal Qwen (GPU)        : the 4 trained fields (~5s warm)
        #   2. Anthropic Haiku         : ABV / Net + warning casing (~3s)
        #   3. Modal Tesseract (CPU)   : deterministic warning bbox + EXIF DPI (~1s)
        # End-to-end latency is bound by the slowest of the three (Qwen).
        # On cold Modal, Qwen times out (MODAL_TIMEOUT=8s) and the merge
        # falls back to Haiku alone. Tesseract is non-fatal — failure
        # just leaves the merge using Haiku's bbox.
        tasks: list = [self._call_modal(image_bytes, beverage_type)]
        if self._haiku is not None:
            tasks.append(self._haiku.extract(image_bytes, beverage_type))
        if self.tesseract_url:
            tasks.append(self._call_tesseract(image_bytes))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        modal_result = results[0]
        modal_failed = isinstance(modal_result, Exception)

        haiku_result: ExtractedLabel | None = None
        tesseract_result: dict | None = None
        idx = 1
        if self._haiku is not None:
            r = results[idx]; idx += 1
            if isinstance(r, Exception):
                logger.warning("Haiku side-channel failed: %s", r)
            else:
                haiku_result = r
        if self.tesseract_url:
            r = results[idx]; idx += 1
            if isinstance(r, Exception):
                logger.warning("Tesseract side-channel failed: %s", r)
            elif isinstance(r, dict):
                tesseract_result = r

        if modal_failed:
            if haiku_result is None:
                # Both Modal and Haiku failed (or Haiku isn't configured).
                # Re-raise the Modal exception so the caller sees the
                # original root cause (timeout vs HTTP error vs bad JSON).
                raise modal_result  # type: ignore[misc]
            logger.warning("Modal failed (%s); returning Haiku-full + Tesseract", modal_result)
            # Use Haiku's FULL extraction (all 6 fields it reads). The
            # earlier version routed through _merge_label which only
            # took Haiku's ABV/Net and dropped brand/class/bottler
            # because those slots are "Qwen's" — on the fallback path
            # there's no Qwen to fall back to, so Haiku covers everything.
            # Then overlay Tesseract's deterministic bbox + EXIF DPI
            # on top of whatever warning style Haiku reported.
            haiku_result.extractor_source = "haiku-fallback"
            tess = tesseract_result or {}
            bbox_h = tess.get("warning_bbox_h_px")
            if bbox_h and haiku_result.warning_style is not None:
                haiku_result.warning_style.bbox = (0, 0, 0, int(bbox_h))
                haiku_result.warning_style.body_line_count = 0
            dpi = tess.get("dpi")
            if dpi:
                haiku_result.image_dpi = (int(dpi), int(dpi))
            return haiku_result

        # Backwards-compat with the original deploy that returned a single raw_output
        if "raw_output" in modal_result and "raw_v2" not in modal_result:
            v2_label = _to_extracted_label(_try_parse_json(modal_result.get("raw_output", "")))
        else:
            v2_label = _to_extracted_label(_try_parse_json(modal_result.get("raw_v2", "")))

        merged = _merge_label(v2_label, haiku_result, tesseract_result)
        merged.extractor_source = "modal+haiku" if haiku_result is not None else "modal"

        latency = modal_result.get("latency_sec")
        breakdown = modal_result.get("latency_breakdown")
        if latency is not None:
            logger.info(
                "Modal extract latency: %.2fs  breakdown=%s  haiku=%s  tess=%s",
                latency, breakdown,
                "yes" if haiku_result else "no",
                "yes" if tesseract_result else "no",
            )
        return merged
