"""Pick a LabelExtractor based on settings.INFERENCE_MODE."""

from __future__ import annotations

from ..config import settings
from .base import InferenceError, LabelExtractor
from .cloud import CloudExtractor
from .mock import MockExtractor
from .onprem import OnPremExtractor


def get_extractor(brand_hint: str = "") -> LabelExtractor:
    mode = settings.inference_mode
    if mode == "mock":
        return MockExtractor(brand_hint=brand_hint)
    if mode == "cloud":
        keys = {
            "anthropic": settings.anthropic_api_key,
            "openai": settings.openai_api_key,
            "google": settings.google_api_key,
        }
        key = keys.get(settings.cloud_provider, "")
        if not key:
            raise InferenceError(
                f"INFERENCE_MODE=cloud but no API key set for provider "
                f"{settings.cloud_provider!r}. Set the matching *_API_KEY env var."
            )
        return CloudExtractor(provider=settings.cloud_provider, model=settings.cloud_model, api_key=key)
    if mode == "onprem":
        return OnPremExtractor(vlm_url=settings.onprem_vlm_url, vlm_model=settings.onprem_vlm_model)
    raise InferenceError(f"Unknown INFERENCE_MODE={mode!r}")
