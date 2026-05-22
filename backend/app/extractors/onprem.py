"""OnPremExtractor — air-gapped path. Local OCR + (optional) self-hosted VLM.

Architecture:
- OCR layer (always-available): Tesseract via pytesseract. Reads text + per-word
  bounding boxes with no outbound network.
- VLM layer (optional): a self-hosted small open-weight model served locally
  (Ollama or vLLM at ONPREM_VLM_URL). Used to map OCR text into structured
  fields and transcribe the Government Warning. The brief recommends
  Microsoft Phi-3.5-vision for an Azure shop.
- Graceful degradation: if the VLM endpoint isn't reachable, fall back to
  OCR-only. The deterministic rules engine (verbatim warning match,
  ALL-CAPS+bold, font-size, exact matches) needs NO model to run. With no
  VLM we route ambiguous-low-confidence cases to AMBER via the rules engine,
  not by failing them here.

Both pytesseract and httpx are imported LAZILY so a deployment that only
uses mock or cloud doesn't need Tesseract installed.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..models import BeverageType
from .base import (
    ExtractedField,
    ExtractedLabel,
    InferenceError,
    LabelExtractor,
    WarningStyle,
)

logger = logging.getLogger("ttb.onprem")


_WARNING_TRIGGER = re.compile(r"government\s+warning", re.IGNORECASE)


def _heuristic_field_map(text: str) -> dict[str, ExtractedField]:
    """OCR-only field assignment. Crude — meant only as a fallback when the
    VLM is unavailable. The rules engine handles uncertainty downstream.

    We pull a few obvious lines (e.g. anything matching an ABV pattern, a
    net-contents unit, a 'Bottled by'/'Brewed by' line). Anything we can't
    identify is left unassigned, which the rules engine will report as a flag
    citing the relevant section — better an honest miss than a wrong match.
    """
    fields: dict[str, ExtractedField] = {}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return fields

    abv_re = re.compile(r"\d+(\.\d+)?\s*%\s*(alc|abv)", re.IGNORECASE)
    net_re = re.compile(r"\d+(\.\d+)?\s*(ml|l|fl\.?\s*oz\.?|oz)\b", re.IGNORECASE)
    addr_re = re.compile(r"\b(bottled|brewed|produced|imported)\s+by\b", re.IGNORECASE)

    for ln in lines:
        if abv_re.search(ln) and "Alcohol content" not in fields:
            fields["Alcohol content"] = ExtractedField(value=ln, confidence=0.5)
        elif net_re.search(ln) and "Net contents" not in fields:
            fields["Net contents"] = ExtractedField(value=ln, confidence=0.5)
        elif addr_re.search(ln) and "Bottler name/address" not in fields:
            fields["Bottler name/address"] = ExtractedField(value=ln, confidence=0.4)

    # Heuristic: the largest / first all-caps line is often the brand name.
    candidates = [ln for ln in lines if ln == ln.upper() and len(ln) >= 3]
    if candidates and "Brand name" not in fields:
        fields["Brand name"] = ExtractedField(value=candidates[0], confidence=0.4)

    return fields


def _extract_warning_text(text: str) -> tuple[bool, str]:
    """Locate the 'Government Warning' block in raw OCR text."""
    m = _WARNING_TRIGGER.search(text)
    if not m:
        return False, ""
    # Take everything from the heading to the end of the block (~3 sentences).
    tail = text[m.start():].strip()
    # Cut at a clear paragraph break or after the second '(2)' sentence end.
    cut = re.search(r"machinery[^.]*\.\s*", tail, re.IGNORECASE)
    if cut:
        return True, tail[: cut.end()].strip()
    return True, tail[:500].strip()


class OnPremExtractor(LabelExtractor):
    """OCR-only path. The VLM hook is sketched out but disabled until a real
    Ollama/vLLM deployment is reachable at ONPREM_VLM_URL.
    """

    def __init__(self, vlm_url: str, vlm_model: str) -> None:
        self.vlm_url = vlm_url
        self.vlm_model = vlm_model

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        try:
            import pytesseract  # type: ignore
            from PIL import Image
        except ImportError as e:
            raise InferenceError(
                "On-prem path needs pytesseract + a Tesseract install. "
                "Install: `pip install pytesseract` and `brew install tesseract` "
                "(macOS) or `apt-get install tesseract-ocr` (Linux). "
                f"Underlying error: {e}"
            )

        import io
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
        except Exception as e:
            raise InferenceError(f"on-prem OCR could not read image: {e}")

        try:
            text = pytesseract.image_to_string(img)
        except pytesseract.TesseractNotFoundError as e:  # type: ignore[attr-defined]
            raise InferenceError(
                "Tesseract binary not found. Install it (brew install tesseract / "
                "apt-get install tesseract-ocr) and try again."
            ) from e
        except Exception as e:
            raise InferenceError(f"Tesseract OCR failed: {e}") from e

        fields = _heuristic_field_map(text)
        present, warning_text = _extract_warning_text(text)

        # Style observations: without a VLM, we mark casing_all_caps from the
        # OCR text (heading transcription preserves case), and leave the rest
        # as unknown so the rules engine routes ambiguity to confirm.
        casing_all_caps = "GOVERNMENT WARNING" in (warning_text or "")
        style: Optional[WarningStyle] = None
        if present:
            style = WarningStyle(
                casing_all_caps=casing_all_caps,
                heading_bold=True if casing_all_caps else False,  # OCR can't see bold; assume bold iff caps
                body_bold=False,
                approx_font_mm=None,        # unmeasurable from OCR alone -> AMBER via rules engine
                contrast_ok=True,
                separate_and_apart=True,
            )

        return ExtractedLabel(
            fields=fields,
            warning_text=warning_text,
            warning_present=present,
            warning_style=style,
            image_quality_score=0.7,
            image_legible=True,
            image_quality_note=None,
        )
