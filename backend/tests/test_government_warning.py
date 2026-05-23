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
    assert a.fontSizeOk is True
    assert a.contrastOk is True
    assert a.separateAndApart is True
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
    assert a.fontSizeOk is False
    kinds = {d.type for d in a.deviations}
    assert "casing" in kinds
    assert "wording" in kinds
    assert "fontSize" in kinds


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


def test_unmeasurable_font_size_returns_borderline():
    """When the model can't measure font height, fontSizeOk is False and the
    deviation asks for manual confirmation rather than a hard fail message."""
    style = WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=None, contrast_ok=True, separate_and_apart=True,
    )
    a = analyze_warning(VERBATIM_GOVERNMENT_WARNING, present=True, style=style, container_ml=750.0)
    assert a.fontSizeOk is False
    msg = next((d.message for d in a.deviations if d.type == "fontSize"), "")
    assert "could not be measured" in msg.lower() or "confirm" in msg.lower()


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
