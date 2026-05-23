"""Tests for ModalRemoteExtractor — covers HTTP path with mocked endpoint
so we don't need an actual Modal deployment running."""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest

from app.extractors.base import InferenceError
from app.extractors.modal_remote import ModalRemoteExtractor


def _make_extractor_with_handler(handler):
    """Build a ModalRemoteExtractor whose httpx client routes through a
    user-supplied handler instead of real network."""
    transport = httpx.MockTransport(handler)
    extractor = ModalRemoteExtractor(endpoint_url="https://fake.modal.run", timeout=10)

    # Monkey-patch the AsyncClient used inside extract() via httpx default
    # by patching the class's __init__... easier: swap the extract method
    # to use a client built from the mock transport.
    original_extract = extractor.extract

    async def patched_extract(image_bytes, beverage_type):
        payload = {
            "image_b64":     base64.b64encode(image_bytes).decode("ascii"),
            "beverage_type": str(beverage_type),
        }
        async with httpx.AsyncClient(transport=transport, timeout=extractor.timeout) as client:
            r = await client.post(extractor.endpoint_url, json=payload)
        if r.status_code != 200:
            raise InferenceError(f"Modal endpoint returned {r.status_code}: {r.text[:300]}")
        body = r.json()
        if "error" in body:
            raise InferenceError(f"Modal endpoint error: {body['error']}")
        from app.extractors.sft import _try_parse_json, _to_extracted_label
        raw = body.get("raw_output", "")
        parsed = _try_parse_json(raw)
        label = _to_extracted_label(parsed)
        if parsed is None and label.image_quality_note:
            snippet = raw[:200].replace("\n", " ")
            label.image_quality_note = f"{label.image_quality_note}: {snippet!r}"
        return label

    extractor.extract = patched_extract  # type: ignore
    return extractor


def test_missing_endpoint_url_raises():
    with pytest.raises(InferenceError, match="MODAL_ENDPOINT_URL"):
        ModalRemoteExtractor(endpoint_url="")


def test_happy_path_parses_qwen_json_output():
    """Mocked Modal returns realistic Qwen output → ExtractedLabel populated."""
    qwen_response = {
        "raw_output": json.dumps({
            "fields": {
                "Brand name":      {"value": "Acme Wines", "confidence": 0.94},
                "Alcohol content": {"value": "12.5% Alc./Vol.", "confidence": 0.92},
            },
            "government_warning": {
                "present":            True,
                "detected_text":      "GOVERNMENT WARNING: ...",
                "casing_all_caps":    True,
                "heading_bold":       True,
                "body_bold":          False,
                "approx_font_mm":     None,
                "contrast_ok":        True,
                "separate_and_apart": True,
            },
            "image_quality": {"score": 0.9, "legible": True, "note": None},
        }),
        "latency_sec": 2.4,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # Sanity: image got base64'd and beverage forwarded
        assert "image_b64" in body
        assert body["beverage_type"] == "wine"
        return httpx.Response(200, json=qwen_response)

    extractor = _make_extractor_with_handler(handler)
    label = asyncio.run(extractor.extract(b"fake-image-bytes", "wine"))

    assert label.warning_present is True
    assert label.fields["Brand name"].value == "Acme Wines"
    assert label.fields["Alcohol content"].value == "12.5% Alc./Vol."
    assert label.warning_style.casing_all_caps is True


def test_unparseable_output_returns_empty_label_with_note():
    """If Qwen emits garbage, we still get an ExtractedLabel — the rules
    engine will route it to needs-review via the missing-field path."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"raw_output": "totally not json", "latency_sec": 1.0})

    extractor = _make_extractor_with_handler(handler)
    label = asyncio.run(extractor.extract(b"x", "wine"))

    assert label.fields == {}
    assert label.warning_present is False
    assert "not valid JSON" in (label.image_quality_note or "")


def test_500_response_raises_inference_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal modal error: GPU OOM")

    extractor = _make_extractor_with_handler(handler)
    with pytest.raises(InferenceError, match="500"):
        asyncio.run(extractor.extract(b"x", "wine"))


def test_endpoint_error_payload_raises():
    """When the endpoint returns 200 with {"error": ...} (e.g. from our
    extract_web's missing-image-b64 branch), surface it as InferenceError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "missing image_b64 in payload"})

    extractor = _make_extractor_with_handler(handler)
    with pytest.raises(InferenceError, match="missing image_b64"):
        asyncio.run(extractor.extract(b"x", "wine"))
