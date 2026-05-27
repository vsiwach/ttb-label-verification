"""Pick a LabelExtractor based on settings.INFERENCE_MODE."""

from __future__ import annotations

from ..config import settings
from .base import InferenceError, LabelExtractor
from .claude_code import ClaudeCodeExtractor
from .cloud import CloudExtractor
from .mock import MockExtractor
from .modal_remote import ModalRemoteExtractor
from .onprem import OnPremExtractor
from .sft import SFTExtractor


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
    if mode == "claude-code":
        return ClaudeCodeExtractor(model=settings.cloud_model)
    if mode == "onprem":
        return OnPremExtractor(vlm_url=settings.onprem_vlm_url, vlm_model=settings.onprem_vlm_model)
    if mode == "sft":
        return SFTExtractor(model_dir=settings.sft_model_dir)
    if mode == "modal":
        return ModalRemoteExtractor(
            endpoint_url=settings.modal_endpoint_url,
            timeout=settings.modal_timeout,
            # If an Anthropic key is set, Modal extraction runs in parallel
            # with a Haiku call that fills the 3 fields v2 doesn't extract
            # (Alcohol content, Net contents, Government Warning). Without
            # the key, those fields come back empty (engine flags them).
            anthropic_api_key=settings.anthropic_api_key,
            cloud_model=settings.cloud_model,
            # CPU-only Tesseract endpoint provides the deterministic
            # warning bbox + EXIF DPI for the 16.22 type-size check.
            tesseract_url=settings.modal_tesseract_url,
        )
    raise InferenceError(f"Unknown INFERENCE_MODE={mode!r}")
