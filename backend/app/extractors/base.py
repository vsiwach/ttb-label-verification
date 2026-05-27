"""Abstract LabelExtractor + the typed shape it returns.

The extractor ONLY reads the label image and reports what it sees plus
confidence. It does NOT decide match / likely / flag — that's the rules
engine's job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..models import BeverageType


class InferenceError(Exception):
    """Raised when inference fails (timeout, provider error, bad image)."""


@dataclass
class ExtractedField:
    """One field the model read off the label."""
    value: str
    confidence: float
    bbox: Optional[tuple[int, int, int, int]] = None  # (x, y, w, h), optional


@dataclass
class WarningStyle:
    """Style observations about the Government Warning region."""
    casing_all_caps: bool   # is 'GOVERNMENT WARNING' rendered in all caps?
    heading_bold: bool      # is 'GOVERNMENT WARNING' bold?
    body_bold: bool         # is the body bold? (it should NOT be)
    approx_font_mm: Optional[float] = None  # DEPRECATED — kept for old extractors.
                                            # Use bbox+line_count+DPI instead.
    contrast_ok: Optional[bool] = None      # adequate contrast vs background
    separate_and_apart: Optional[bool] = None  # visually separated from other copy
    bbox: Optional[tuple[int, int, int, int]] = None  # warning text region (px)
    # Number of body-text lines in the warning. Used together with the
    # bbox height and the image's DPI to compute mm per line:
    #   mm = (bbox_height / line_count) / dpi * 25.4
    # The rules engine performs the threshold comparison.
    body_line_count: Optional[int] = None


@dataclass
class ExtractedLabel:
    """Everything the extractor produces from one label image."""
    # field_name -> ExtractedField. Field names mirror VerificationField.fieldName
    # used by the frontend: "Brand name", "Class & type", "Alcohol content",
    # "Net contents", "Bottler name/address".
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    warning_text: str = ""
    warning_present: bool = False
    warning_style: Optional[WarningStyle] = None
    image_quality_score: float = 1.0
    image_legible: bool = True
    image_quality_note: Optional[str] = None
    # DPI of the source image (x, y). Set by the image_pipeline when the
    # JPEG/PNG carries DPI metadata; None for screenshots or stripped
    # images. Enables the deterministic type-size check.
    image_dpi: Optional[tuple[int, int]] = None
    # Which extractor actually produced this read. Surfaces in TimingInfo
    # so the UI can show "modal+haiku" on the warm path or
    # "haiku-fallback" when Modal was cold. Optional — only set by
    # ModalRemoteExtractor; other extractors leave it None and the API
    # layer falls back to settings.inference_mode.
    extractor_source: Optional[str] = None


class LabelExtractor(ABC):
    """Swappable inference interface. Mock / Cloud / OnPrem all implement this."""

    @abstractmethod
    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        """Read the label image and report observations + confidence."""
        ...
