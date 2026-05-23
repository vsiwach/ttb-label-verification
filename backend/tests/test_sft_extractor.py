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
    _is_donut_family,
    _try_parse_json,
    _to_extracted_label,
)


def test_manifest_dispatch_qwen():
    m = {"model_tag": "qwen2_5_vl_7b", "base_model": "unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit"}
    assert _is_qwen_family(m) is True
    assert _is_donut_family(m) is False


def test_manifest_dispatch_donut():
    m = {"model_tag": "donut", "base_model": "naver-clova-ix/donut-base"}
    assert _is_donut_family(m) is True
    assert _is_qwen_family(m) is False


def test_manifest_dispatch_unknown_returns_false_both():
    m = {"model_tag": "something_else", "base_model": "random/model"}
    assert _is_qwen_family(m) is False
    assert _is_donut_family(m) is False


def test_read_manifest_direct_path(tmp_path):
    (tmp_path / "manifest.json").write_text('{"model_tag": "foo", "base_model": "bar"}')
    m = _read_manifest(tmp_path)
    assert m["model_tag"] == "foo"


def test_read_manifest_under_adapter_subdir(tmp_path):
    (tmp_path / "adapter").mkdir()
    (tmp_path / "adapter" / "manifest.json").write_text('{"model_tag": "qwen_x", "base_model": "z"}')
    m = _read_manifest(tmp_path)
    assert m["model_tag"] == "qwen_x"


def test_read_manifest_under_model_subdir(tmp_path):
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "manifest.json").write_text('{"model_tag": "donut", "base_model": "z"}')
    m = _read_manifest(tmp_path)
    assert m["model_tag"] == "donut"


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
