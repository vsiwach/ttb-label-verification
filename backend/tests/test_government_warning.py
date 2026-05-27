"""Government Warning engine: 16.21 verbatim + 16.22 format checks."""

from app.constants import VERBATIM_GOVERNMENT_WARNING
from app.extractors.base import WarningStyle
from app.rules.government_warning import analyze_warning


def _good_style() -> WarningStyle:
    return WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=2.2, contrast_ok=True, separate_and_apart=True,
    )


def test_exact_verbatim_warning_is_compliant():
    a = analyze_warning(
        detected_text=VERBATIM_GOVERNMENT_WARNING,
        present=True,
        style=_good_style(),
        container_ml=750.0,
    )
    assert a.present is True
    assert a.verbatimMatch is True
    assert a.casingBoldOk is True
    assert a.contrastOk is True
    assert a.separateAndApart is True
    # No deviations — type size (16.22) is intentionally not verified
    # (digital image has no DPI/scale reference). Documented limitation,
    # not a deviation.
    assert a.deviations == []


def test_all_caps_body_is_verbatim_compliant():
    """TTB allows the warning body in any case — only the 'GOVERNMENT WARNING'
    heading is case-restricted (16.22). An all-caps body printed verbatim must
    NOT be a wording violation."""
    all_caps = (
        "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
        "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. "
        "(2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR "
        "OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
    )
    a = analyze_warning(all_caps, present=True, style=_good_style(), container_ml=750.0)
    assert a.verbatimMatch is True
    assert not any(d.type == "wording" for d in a.deviations)


def test_ocr_noise_punctuation_spacing_does_not_break_verbatim():
    """Real OCR often inserts spaces around punctuation: 'WARNING :', '( 1 )'.
    These should normalize away in the wording comparison."""
    noisy = (
        "GOVERNMENT WARNING : ( 1 ) According to the Surgeon General , women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth defects . "
        "( 2 ) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery , and may cause health problems ."
    )
    a = analyze_warning(noisy, present=True, style=_good_style(), container_ml=750.0)
    assert a.verbatimMatch is True


def test_ocr_noise_does_not_break_verbatim_match():
    """Stray spaces and a line-break hyphenation must NOT trip verbatim."""
    noisy = (
        "GOVERNMENT  WARNING: (1) According to the Surgeon General, women should not "
        "drink alcoholic beverages during preg-\nnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    a = analyze_warning(noisy, present=True, style=_good_style(), container_ml=750.0)
    assert a.verbatimMatch is True
    assert a.deviations == []


def test_title_case_paraphrased_small_warning_has_three_deviations():
    """Scenario C: catches casing, wording, and fontSize."""
    detected = (
        "Government Warning: (1) According to the Surgeon General, women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Drinking alcoholic beverages impairs your ability to drive a car or operate "
        "machinery and may cause health problems."
    )
    style = WarningStyle(
        casing_all_caps=False, heading_bold=False, body_bold=False,
        approx_font_mm=0.8, contrast_ok=True, separate_and_apart=True,
    )
    # 12 FL OZ ≈ 355 mL → min 2 mm threshold
    a = analyze_warning(detected, present=True, style=style, container_ml=355.0)
    assert a.verbatimMatch is False
    assert a.casingBoldOk is False
    kinds = {d.type for d in a.deviations}
    assert "casing" in kinds
    assert "wording" in kinds
    # fontSize check intentionally removed — not deterministically
    # verifiable from a digital image. See DESIGN.md §10.


def test_near_verbatim_single_character_ocr_slip_is_compliant_with_advisory():
    """Real labels often have a single missing comma or "operte" for "operate"
    — these are OCR slips, not paraphrase. The engine should keep
    verbatimMatch=True (so the bucket isn't routed to needs-review) and emit
    a 'near_verbatim' advisory deviation so the agent verifies visually."""
    # Missing comma after "general"
    detected = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
        "operate machinery, and may cause health problems."
    )
    a = analyze_warning(detected, present=True, style=_good_style(), container_ml=750.0)
    assert a.verbatimMatch is True
    kinds = [d.type for d in a.deviations]
    assert "near_verbatim" in kinds
    assert "wording" not in kinds  # not a substantive wording violation


def test_paraphrase_still_caught_below_near_verbatim_threshold():
    """Substantive paraphrase ('Drinking' instead of 'Consumption' / dropped
    sentences) drops similarity below 95% and still produces verbatim=False
    with a 'wording' deviation — paraphrase detection preserved."""
    paraphrased = (
        "Government Warning: (1) According to the Surgeon General, women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Drinking alcoholic beverages impairs your ability to drive a car or operate "
        "machinery and may cause health problems."
    )
    a = analyze_warning(paraphrased, present=True, style=_good_style(), container_ml=750.0)
    assert a.verbatimMatch is False
    assert any(d.type == "wording" for d in a.deviations)


def test_missing_warning_flags_with_citation():
    a = analyze_warning(detected_text="", present=False, style=None, container_ml=750.0)
    assert a.present is False
    assert any(d.type == "missing" for d in a.deviations)
    assert "16.21" in a.deviations[0].message  # cites the regulation


def test_body_bold_is_flagged():
    style = WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=True,  # body should NOT be bold
        approx_font_mm=2.2, contrast_ok=True, separate_and_apart=True,
    )
    a = analyze_warning(VERBATIM_GOVERNMENT_WARNING, present=True, style=style, container_ml=750.0)
    assert a.casingBoldOk is False
    assert any(d.type == "casing" for d in a.deviations)


def test_low_contrast_is_flagged():
    style = WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=2.2, contrast_ok=False, separate_and_apart=True,
    )
    a = analyze_warning(VERBATIM_GOVERNMENT_WARNING, present=True, style=style, container_ml=750.0)
    assert a.contrastOk is False
    assert any(d.type == "contrast" for d in a.deviations)


def test_not_separate_and_apart_is_flagged():
    style = WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=2.2, contrast_ok=True, separate_and_apart=False,
    )
    a = analyze_warning(VERBATIM_GOVERNMENT_WARNING, present=True, style=style, container_ml=750.0)
    assert a.separateAndApart is False
    assert any(d.type == "separation" for d in a.deviations)


# ── Type-size check via bbox + DPI (new in PR adding 16.22 mm verification) ──

def _style_with_bbox(line_count: int = 5, bbox_h: int = 200) -> WarningStyle:
    """Build a WarningStyle with the bbox/line-count needed for type-size."""
    return WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        contrast_ok=True, separate_and_apart=True,
        bbox=(100, 1000, 800, bbox_h),
        body_line_count=line_count,
    )


def test_type_size_passes_when_bbox_and_dpi_yield_compliant_mm():
    """200 px / 5 lines / 200 DPI = 0.20 in/line = 5.08 mm/line — well over 2 mm."""
    style = _style_with_bbox(line_count=5, bbox_h=200)
    a = analyze_warning(
        VERBATIM_GOVERNMENT_WARNING, present=True, style=style,
        container_ml=750.0, image_dpi=(200, 200),
    )
    assert a.fontSizeOk is True
    assert not any(d.type == "fontSize" for d in a.deviations)


def test_type_size_fails_when_measured_below_minimum():
    """30 px / 5 lines / 200 DPI = 0.030 in/line = 0.76 mm/line — below 2 mm."""
    style = _style_with_bbox(line_count=5, bbox_h=30)
    a = analyze_warning(
        VERBATIM_GOVERNMENT_WARNING, present=True, style=style,
        container_ml=750.0, image_dpi=(200, 200),
    )
    assert a.fontSizeOk is False
    assert any(d.type == "fontSize" for d in a.deviations)


def test_type_size_omitted_when_dpi_missing():
    """No DPI → fontSizeOk is None (agent confirms manually). No deviation."""
    style = _style_with_bbox(line_count=5, bbox_h=200)
    a = analyze_warning(
        VERBATIM_GOVERNMENT_WARNING, present=True, style=style,
        container_ml=750.0, image_dpi=None,
    )
    assert a.fontSizeOk is None
    assert not any(d.type == "fontSize" for d in a.deviations)


def test_type_size_omitted_when_bbox_missing():
    """No bbox → fontSizeOk is None even with DPI."""
    style = WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        contrast_ok=True, separate_and_apart=True,
        bbox=None, body_line_count=5,
    )
    a = analyze_warning(
        VERBATIM_GOVERNMENT_WARNING, present=True, style=style,
        container_ml=750.0, image_dpi=(200, 200),
    )
    assert a.fontSizeOk is None


# ── Regression: casing fallback when transcription drops the preamble ───────
def test_casing_passes_when_transcription_drops_preamble_but_flag_is_true():
    """Real-world failure mode: Haiku sometimes returns the warning body in
    detected_text but OMITS the literal 'GOVERNMENT WARNING:' preamble, while
    correctly reporting casing_all_caps=True from its visual observation.

    The engine MUST trust the model's flag in that gap (it's a visual
    observation independent of transcription completeness), not flag a
    compliant label as non-compliant just because the preamble didn't
    appear in the transcribed text.

    See: github.com/vsiwach/ttb-label-verification issue surfaced in QA
    on the Pilsener sample (May 2026).
    """
    # Body only — no "GOVERNMENT WARNING:" preamble in the text
    body_only = (
        "(1) According to the Surgeon General, women should not drink alcoholic "
        "beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic beverages impairs your ability to drive a "
        "car or operate machinery, and may cause health problems."
    )
    a = analyze_warning(
        detected_text=body_only,
        present=True,
        style=_good_style(),  # casing_all_caps=True (model's visual flag)
        container_ml=750.0,
    )
    assert a.present is True
    # casing should PASS via the style.casing_all_caps fallback
    assert a.casingBoldOk is True, (
        "Casing must pass when the model's visual flag says caps=True, "
        "even if the preamble didn't make it into detected_text."
    )
    # No 'casing' deviation should be raised
    assert not any(d.type == "casing" for d in a.deviations)


def test_casing_fails_when_flag_is_false_and_preamble_missing():
    """The flip side: if BOTH the preamble is missing AND the model says caps=False,
    we must still flag it. No positive evidence either way → conservative flag."""
    body_only = "(1) According to the Surgeon General..."
    a = analyze_warning(
        detected_text=body_only,
        present=True,
        style=WarningStyle(
            casing_all_caps=False,  # model says NOT in caps
            heading_bold=False, body_bold=False,
            contrast_ok=True, separate_and_apart=True,
        ),
        container_ml=750.0,
    )
    assert a.casingBoldOk is False
    assert any(d.type == "casing" for d in a.deviations)


def test_casing_passes_when_preamble_is_literally_in_caps_in_text():
    """Direct-evidence path: if 'GOVERNMENT WARNING:' appears literally in the
    transcribed text, we use that (don't need the model's flag)."""
    text_with_preamble = (
        "GOVERNMENT WARNING: (1) According to the Surgeon General..."
    )
    a = analyze_warning(
        detected_text=text_with_preamble,
        present=True,
        # Even with a contradictory flag, the literal text wins (positive evidence)
        style=WarningStyle(
            casing_all_caps=False,  # model flag is wrong; text wins
            heading_bold=True, body_bold=False,
            contrast_ok=True, separate_and_apart=True,
        ),
        container_ml=750.0,
    )
    assert a.casingBoldOk is True
