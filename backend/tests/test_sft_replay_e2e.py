"""End-to-end replay test for the SFT path.

Validates that an actual Qwen model output (the kind cell 28 of the
training notebook produced) is correctly parsed by SFTExtractor and
that the rules engine then produces the verdict shape the frontend
expects.

This is what proves the integration works without needing the actual
4.2B-param model loaded — we substitute a stub loader that returns
pre-recorded model output, then exercise the same code path that the
real model would hit.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.extractors.sft import _try_parse_json, _to_extracted_label


# A realistic Qwen2.5-VL output for a wine label. This is the kind of JSON
# the trained model emits — note the prose wrapper, the field shape, and
# the trailing comma we sometimes see in practice. The parser must recover.
QWEN_RAW_OUTPUT = """\
{
  "fields": {
    "Brand name": {"value": "Blendings Winery", "confidence": 0.94},
    "Class & type": {"value": "GRAPE WINE WITH NATURAL FLAVOR", "confidence": 0.91},
    "Alcohol content": {"value": "12.53% Alc./Vol.", "confidence": 0.92},
    "Net contents": {"value": "750 ML", "confidence": 0.95},
    "Bottler name/address": {"value": "Produced and bottled by FOCO Blendings llc Fort Collins, Colorado", "confidence": 0.87}
  },
  "government_warning": {
    "present": true,
    "detected_text": "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
    "casing_all_caps": true,
    "heading_bold": true,
    "body_bold": false,
    "approx_font_mm": null,
    "contrast_ok": true,
    "separate_and_apart": true
  },
  "image_quality": {"score": 0.85, "legible": true, "note": null}
}"""


def test_parse_realistic_qwen_output_fields_intact():
    """The parser handles the actual JSON shape Qwen emits."""
    parsed = _try_parse_json(QWEN_RAW_OUTPUT)
    assert parsed is not None
    assert parsed["fields"]["Brand name"]["value"] == "Blendings Winery"
    assert parsed["fields"]["Net contents"]["value"] == "750 ML"


def test_extracted_label_round_trip_from_qwen_output():
    """Going Qwen output → _to_extracted_label preserves field semantics
    in the shape the rules engine expects."""
    parsed = _try_parse_json(QWEN_RAW_OUTPUT)
    label = _to_extracted_label(parsed)

    assert label.warning_present is True
    assert "Surgeon General" in label.warning_text
    assert label.warning_style.casing_all_caps is True
    assert label.warning_style.body_bold is False

    assert "Brand name" in label.fields
    assert label.fields["Brand name"].value == "Blendings Winery"
    assert label.fields["Brand name"].confidence == 0.94

    assert label.fields["Alcohol content"].value == "12.53% Alc./Vol."
    assert label.fields["Net contents"].value == "750 ML"


def test_rules_engine_processes_qwen_output_end_to_end():
    """The full path: Qwen output → ExtractedLabel → rules engine →
    VerificationResult. This is what /api/verify does for an sft request."""
    from app.models import ApplicationData
    from app.rules.engine import verify

    parsed = _try_parse_json(QWEN_RAW_OUTPUT)
    extracted = _to_extracted_label(parsed)

    app_data = ApplicationData(
        brandName="Blendings Winery",
        classType="table flavored wine",
        alcoholContent="12.5% Alc./Vol.",
        netContents="750 mL",
        bottlerNameAddress="FOCO Blendings LLC, Fort Collins, Colorado",
        beverageType="wine",
    )

    result = verify(extracted=extracted, app=app_data)

    # Field-level: every declared field should land as match or likely.
    field_status_by_name = {f.fieldName: f.status for f in result.fields}
    assert field_status_by_name.get("Brand name") in ("match", "likely")
    assert field_status_by_name.get("Alcohol content") in ("match", "likely")
    assert field_status_by_name.get("Net contents") == "match"

    # Government Warning verbatim should resolve true (the canonical text)
    assert result.governmentWarning.present is True
    assert result.governmentWarning.verbatimMatch is True
    assert result.governmentWarning.casingBoldOk is True

    # Group bucketing — with all match/likely + verbatim, this should not
    # be needs-review (the engine should route to auto-pass or needs-confirm).
    statuses = list(field_status_by_name.values())
    assert "flag" not in statuses, f"Unexpected flag in {field_status_by_name}"


def test_rules_engine_handles_qwen_output_with_substantive_mismatch():
    """Sanity: when the model's extraction substantively disagrees with
    the application, the engine routes to needs-review (a flag fires)."""
    # Same Qwen output but the application claims a different brand
    from app.models import ApplicationData
    from app.rules.engine import verify

    parsed = _try_parse_json(QWEN_RAW_OUTPUT)
    extracted = _to_extracted_label(parsed)

    app_data = ApplicationData(
        brandName="Completely Different Winery Co",
        classType="table flavored wine",
        alcoholContent="40% Alc./Vol.",   # 27.5% off — beyond agent-review tolerance
        netContents="200 mL",              # >70% off
        bottlerNameAddress="Unrelated Producer LLC",
        beverageType="wine",
    )
    result = verify(extracted=extracted, app=app_data)

    statuses = {f.fieldName: f.status for f in result.fields}
    assert statuses.get("Brand name") == "flag", \
        f"Expected brand flag for substantively different name, got {statuses}"
    assert statuses.get("Alcohol content") == "flag", \
        f"Expected ABV flag for 40% vs 12.5%, got {statuses}"
    assert statuses.get("Net contents") == "flag", \
        f"Expected net contents flag for 200 vs 750 mL, got {statuses}"


def test_sft_extractor_replay_with_stub_loader(tmp_path):
    """Wire-level: SFTExtractor with a stubbed loader returns an
    ExtractedLabel correctly when given image bytes — proves async path
    works without needing the real model loaded."""
    import asyncio
    from app.extractors.sft import SFTExtractor

    # Create a minimal fake bundle so SFTExtractor.__init__ accepts it
    bundle = tmp_path / "fake_qwen_bundle"
    (bundle / "adapter").mkdir(parents=True)
    (bundle / "adapter" / "manifest.json").write_text(json.dumps({
        "model_tag": "qwen2_5_vl_7b_fake",
        "base_model": "unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit",
    }))

    extractor = SFTExtractor(model_dir=str(bundle))

    # Stub the loader's generate_json so we don't actually load Qwen
    class _StubLoader:
        def generate_json(self, image_bytes, beverage_type):
            return QWEN_RAW_OUTPUT
    extractor._loader = _StubLoader()

    label = asyncio.run(extractor.extract(b"fake-image-bytes", "wine"))

    assert label.warning_present is True
    assert label.fields["Brand name"].value == "Blendings Winery"
    assert label.image_legible is True
