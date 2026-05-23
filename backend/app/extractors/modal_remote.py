"""ModalRemoteExtractor — HTTPS adapter that calls a remote Qwen Modal endpoint.

Lets the local backend route extraction through a Modal-hosted Qwen LoRA
instance (deployed via backend/modal_deploy/serve_qwen.py) without needing
torch/transformers locally. Useful for:
  - Production deployment where the backend runs on a small CPU host and
    Qwen runs on Modal's A10G with scale-to-zero.
  - Demo deployment where the rules engine is the only thing the backend
    does locally; inference is delegated.

Wire it via:
    INFERENCE_MODE=modal
    MODAL_ENDPOINT_URL=https://<user>--ttb-qwen-extractor-extract-web.modal.run

The remote returns the raw Qwen output; we parse it with the same best-effort
parser the local SFT extractor uses, so the resulting ExtractedLabel is shape-
identical and the rules engine doesn't care which model produced it.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from ..models import BeverageType
from .base import (
    ExtractedLabel,
    InferenceError,
    LabelExtractor,
)
from .sft import _try_parse_json, _to_extracted_label

logger = logging.getLogger("ttb.modal_remote")


class ModalRemoteExtractor(LabelExtractor):
    """Calls a Modal-hosted Qwen extractor via HTTPS."""

    def __init__(self, endpoint_url: str, timeout: float = 60.0):
        if not endpoint_url:
            raise InferenceError(
                "INFERENCE_MODE=modal but MODAL_ENDPOINT_URL is empty. "
                "Set MODAL_ENDPOINT_URL to the deploy's web URL (printed by `modal deploy`)."
            )
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout = timeout
        logger.info("ModalRemoteExtractor initialized → %s", self.endpoint_url)

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
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
                f"(first request takes 30-60 s while the 7B base loads). Retry or raise the timeout."
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

        raw = body.get("raw_output", "")
        parsed = _try_parse_json(raw)
        label = _to_extracted_label(parsed)
        if parsed is None and label.image_quality_note:
            snippet = raw[:200].replace("\n", " ")
            label.image_quality_note = f"{label.image_quality_note}: {snippet!r}"
        # Stash the remote latency for observability
        latency = body.get("latency_sec")
        if latency is not None:
            logger.info("Modal extract latency: %.2fs", latency)
        return label
