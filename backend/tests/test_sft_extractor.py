"""Lightweight tests for the SFT extractor — covers the parts that don't
need torch/transformers installed (manifest dispatch + JSON parsing +
ExtractedLabel construction).

The actual model.generate() calls are only exercised when transformers is
installed; those live in a separate integration test path.
"""

from pathlib import Path

import pytest

from app.extractors.base import InferenceError
from app.extractors.sft import (
    _read_manifest,
    _is_qwen_family,
    _try_parse_json,
    _to_extracted_label,
    _canonicalize_field_name,
    _coerce_confidence,
)


def test_manifest_dispatch_qwen():
    m = {"model_tag": "qwen2_5_vl_7b", "base_model": "unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit"}
    assert _is_qwen_family(m) is True


def test_manifest_dispatch_unknown_returns_false():
    m = {"model_tag": "something_else", "base_model": "random/model"}
    assert _is_qwen_family(m) is False


def test_read_manifest_direct_path(tmp_path):
    (tmp_path / "manifest.json").write_text('{"model_tag": "foo", "base_model": "bar"}')
    m = _read_manifest(tmp_path)
    assert m["model_tag"] == "foo"


def test_read_manifest_under_adapter_subdir(tmp_path):
    (tmp_path / "adapter").mkdir()
    (tmp_path / "adapter" / "manifest.json").write_text('{"model_tag": "qwen_x", "base_model": "z"}')
    m = _read_manifest(tmp_path)
    assert m["model_tag"] == "qwen_x"


def test_read_manifest_missing_raises(tmp_path):
    with pytest.raises(InferenceError, match="No manifest.json"):
        _read_manifest(tmp_path)


def test_parse_clean_json():
    raw = '{"fields": {"Brand name": {"value": "Foo", "confidence": 0.9}}, ' \
          '"government_warning": {"present": true, "detected_text": "...", ' \
          '"casing_all_caps": true, "heading_bold": true, "body_bold": false}, ' \
          '"image_quality": {"score": 0.9, "legible": true}}'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert parsed["fields"]["Brand name"]["value"] == "Foo"


def test_parse_json_with_prose_around():
    raw = 'Sure, here is the extraction:\n\n{"fields": {}, "government_warning": ' \
          '{"present": false, "detected_text": "", "casing_all_caps": false, ' \
          '"heading_bold": false, "body_bold": false}, "image_quality": ' \
          '{"score": 0.7, "legible": true}}\n\nLet me know if you need more.'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert parsed["government_warning"]["present"] is False


def test_parse_json_with_trailing_comma():
    # LMs commonly emit a trailing comma; the parser should recover.
    raw = '{"fields": {"Brand name": {"value": "X", "confidence": 0.8,},}, ' \
          '"government_warning": {"present": false, "detected_text": "", ' \
          '"casing_all_caps": false, "heading_bold": false, "body_bold": false}, ' \
          '"image_quality": {"score": 1, "legible": true}}'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert parsed["fields"]["Brand name"]["value"] == "X"


def test_parse_empty_returns_none():
    assert _try_parse_json("") is None
    assert _try_parse_json("nope, no JSON here") is None


def test_parse_markdown_code_fence():
    raw = '```json\n{"fields": {"Brand name": {"value": "Acme", "confidence": 0.9}}}\n```'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert parsed["fields"]["Brand name"]["value"] == "Acme"


def test_parse_truncated_missing_closing_brace():
    """Model ran out of tokens mid-output — try to balance and parse what we have."""
    raw = '{"fields": {"Brand name": {"value": "Acme", "confidence": 0.9}'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert parsed["fields"]["Brand name"]["value"] == "Acme"


def test_parse_smart_quotes():
    """Some models emit Unicode smart quotes — normalize before parsing."""
    raw = '{“fields”: {“Brand name”: {“value”: “Acme”, “confidence”: 0.9}}}'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert parsed["fields"]["Brand name"]["value"] == "Acme"


def test_parse_trailing_garbage_after_valid_json():
    """Model emits valid JSON then keeps rambling — recover the prefix."""
    raw = '{"fields": {"Brand name": {"value": "Acme", "confidence": 0.9}}, "image_quality": {"score": 0.9, "legible": true}} and now some prose that follows the JSON which makes the model output past the boundary {invalid stuff'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert parsed["fields"]["Brand name"]["value"] == "Acme"


def test_parse_control_characters_stripped():
    raw = '{"fields": {"Brand name": {"value": "Acme\x01\x02", "confidence": 0.9}}}'
    parsed = _try_parse_json(raw)
    assert parsed is not None
    assert "Acme" in parsed["fields"]["Brand name"]["value"]


# ──────────────────────────────────────────────────────────────────────────────
# Field-name aliasing (model emits snake_case → normalized to canonical)
# ──────────────────────────────────────────────────────────────────────────────

def test_canonicalize_exact_match():
    assert _canonicalize_field_name("Brand name") == "Brand name"
    assert _canonicalize_field_name("Class & type") == "Class & type"

def test_canonicalize_snake_case():
    assert _canonicalize_field_name("brand_name") == "Brand name"
    assert _canonicalize_field_name("alcohol_content") == "Alcohol content"
    assert _canonicalize_field_name("net_contents") == "Net contents"
    assert _canonicalize_field_name("bottler_name_address") == "Bottler name/address"
    assert _canonicalize_field_name("country_of_origin") == "Country of origin"

def test_canonicalize_common_aliases():
    # The Qwen LoRA output from the eval — exact strings the model emitted
    assert _canonicalize_field_name("brand_name") == "Brand name"
    assert _canonicalize_field_name("product_type") == "Class & type"
    assert _canonicalize_field_name("volume") == "Net contents"
    assert _canonicalize_field_name("Volume") == "Net contents"
    assert _canonicalize_field_name("bottled_by") == "Bottler name/address"
    assert _canonicalize_field_name("Producer") == "Bottler name/address"
    assert _canonicalize_field_name("Distiller") == "Bottler name/address"
    assert _canonicalize_field_name("Importer") == "Bottler name/address"
    assert _canonicalize_field_name("ABV") == "Alcohol content"
    assert _canonicalize_field_name("Proof") == "Alcohol content"
    assert _canonicalize_field_name("Origin") == "Country of origin"

def test_canonicalize_unknown_returns_none():
    # Random keys the model invents shouldn't pollute the extracted fields
    assert _canonicalize_field_name("location") is None     # too generic
    assert _canonicalize_field_name("ingredients") is None
    assert _canonicalize_field_name("description") is None
    assert _canonicalize_field_name("") is None
    assert _canonicalize_field_name(None) is None  # type: ignore

def test_to_extracted_label_normalizes_field_names():
    """End-to-end: model emits snake_case → ExtractedLabel has canonical keys."""
    data = {
        "fields": {
            "brand_name":      {"value": "Acme",          "confidence": 0.9},
            "alcohol_content": {"value": "12.5% ABV",      "confidence": 0.92},
            "volume":          {"value": "750 mL",         "confidence": 0.95},
            "bottled_by":      {"value": "Acme Winery",    "confidence": 0.85},
            "location":        {"value": "Sonoma, CA",     "confidence": 0.8},   # dropped — unknown
        },
        "government_warning": {"present": False, "detected_text": "",
                                "casing_all_caps": False, "heading_bold": False, "body_bold": False},
        "image_quality": {"score": 0.9, "legible": True},
    }
    label = _to_extracted_label(data)
    assert "Brand name" in label.fields
    assert label.fields["Brand name"].value == "Acme"
    assert label.fields["Alcohol content"].value == "12.5% ABV"
    assert label.fields["Net contents"].value == "750 mL"
    assert label.fields["Bottler name/address"].value == "Acme Winery"
    # "location" should be dropped as it doesn't map to any canonical field
    assert "location" not in label.fields
    assert "Location" not in label.fields

def test_to_extracted_label_higher_confidence_wins_on_duplicate():
    """If the model emits both 'brand_name' AND 'Brand name', keep the higher."""
    data = {
        "fields": {
            "brand_name": {"value": "Foo", "confidence": 0.5},
            "Brand name": {"value": "Bar", "confidence": 0.9},
        },
        "government_warning": {"present": False, "detected_text": "",
                                "casing_all_caps": False, "heading_bold": False, "body_bold": False},
        "image_quality": {"score": 0.9, "legible": True},
    }
    label = _to_extracted_label(data)
    assert label.fields["Brand name"].value == "Bar"
    assert label.fields["Brand name"].confidence == 0.9


# ──────────────────────────────────────────────────────────────────────────────
# Confidence coercion — models emit 'high'/'0.9'/'90%'/None
# ──────────────────────────────────────────────────────────────────────────────

def test_coerce_confidence_numeric():
    assert _coerce_confidence(0.9) == 0.9
    assert _coerce_confidence(1) == 1.0
    assert _coerce_confidence(0) == 0.0
    assert _coerce_confidence(2.0) == 1.0    # clamped
    assert _coerce_confidence(-0.5) == 0.0   # clamped

def test_coerce_confidence_descriptor_strings():
    assert _coerce_confidence("high") == 0.90
    assert _coerce_confidence("HIGH") == 0.90
    assert _coerce_confidence("medium") == 0.70
    assert _coerce_confidence("low") == 0.40
    assert _coerce_confidence("unknown_word") == 0.70  # default

def test_coerce_confidence_numeric_strings():
    assert _coerce_confidence("0.9") == 0.9
    assert _coerce_confidence("90") == 0.9
    assert _coerce_confidence("90%") == 0.9

def test_coerce_confidence_none():
    assert _coerce_confidence(None) == 0.0


def test_to_extracted_label_handles_missing_data():
    label = _to_extracted_label(None)
    assert label.warning_present is False
    assert label.fields == {}
    assert "not valid JSON" in (label.image_quality_note or "")


def test_to_extracted_label_round_trip():
    data = {
        "fields": {
            "Brand name": {"value": "Acme", "confidence": 0.95},
            "Alcohol content": {"value": "5.5% ABV", "confidence": 0.9},
        },
        "government_warning": {
            "present": True,
            "detected_text": "GOVERNMENT WARNING: (1)...",
            "casing_all_caps": True,
            "heading_bold": True,
            "body_bold": False,
            "approx_font_mm": 2.1,
            "contrast_ok": True,
            "separate_and_apart": True,
        },
        "image_quality": {"score": 0.88, "legible": True, "note": None},
    }
    label = _to_extracted_label(data)
    assert label.warning_present is True
    assert label.warning_style.casing_all_caps is True
    assert label.warning_style.body_bold is False
    assert label.warning_style.approx_font_mm == 2.1
    assert label.fields["Brand name"].value == "Acme"
    assert label.fields["Brand name"].confidence == 0.95
    assert label.fields["Alcohol content"].value == "5.5% ABV"
    assert label.image_quality_score == 0.88
    assert label.image_legible is True


def test_to_extracted_label_skips_malformed_field_entries():
    data = {
        "fields": {
            "Brand name": "not-a-dict",          # malformed: skipped
            "Class & type": {"value": "Beer"},   # missing confidence: defaults to 0.0
        },
        "government_warning": {"present": False, "detected_text": "",
                                "casing_all_caps": False, "heading_bold": False,
                                "body_bold": False},
        "image_quality": {"score": 0.5, "legible": True},
    }
    label = _to_extracted_label(data)
    assert "Brand name" not in label.fields
    assert label.fields["Class & type"].value == "Beer"
    assert label.fields["Class & type"].confidence == 0.0
