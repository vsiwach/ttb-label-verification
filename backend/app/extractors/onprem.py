"""OnPremExtractor — local OCR + self-hosted small VLM (Phi-3.5-vision).

Stubbed for now; full implementation lands in a later step.
"""

from __future__ import annotations

from ..models import BeverageType
from .base import ExtractedLabel, InferenceError, LabelExtractor


class OnPremExtractor(LabelExtractor):
    def __init__(self, vlm_url: str, vlm_model: str) -> None:
        self.vlm_url = vlm_url
        self.vlm_model = vlm_model

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        raise InferenceError(
            "OnPremExtractor not yet implemented. Use INFERENCE_MODE=mock for now."
        )
