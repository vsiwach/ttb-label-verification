"""CloudExtractor — calls a hosted vision LLM (Anthropic / OpenAI / Google).

Stubbed for now; full implementation lands in a later step. The shape is here
so the factory wiring and config are real.
"""

from __future__ import annotations

from ..models import BeverageType
from .base import ExtractedLabel, InferenceError, LabelExtractor


class CloudExtractor(LabelExtractor):
    def __init__(self, provider: str, model: str, api_key: str) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        raise InferenceError(
            f"CloudExtractor (provider={self.provider}) not yet implemented. "
            "Use INFERENCE_MODE=mock for now."
        )
