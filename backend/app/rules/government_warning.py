"""The Government Warning engine (27 CFR 16.21 / 16.22).

Four classes of check:
  1. Verbatim text match (16.21) — normalize only OCR noise, never wording
  2. ALL-CAPS + bold on 'GOVERNMENT WARNING' (16.22)
  3. Type-size vs container (16.22): ≤237 mL → 1 mm; ≤3 L → 2 mm; >3 L → 3 mm
  4. Contrast + 'separate and apart' (16.22)
"""

from __future__ import annotations

import re

from ..constants import VERBATIM_GOVERNMENT_WARNING
from ..extractors.base import WarningStyle
from ..models import GovernmentWarningAnalysis, WarningDeviation
from .net_contents import parse_net_contents_to_ml, required_warning_mm


def _normalize_ocr_noise(s: str) -> str:
    """Normalize ONLY OCR noise.

    We collapse whitespace and reattach line-break hyphenation. We do NOT
    case-fold or rewrite words — paraphrase must remain detectable.
    """
    if not s:
        return ""
    # Reattach line-break hyphenation: "preg-\nnancy" -> "pregnancy"
    s = re.sub(r"-\s*\n\s*", "", s)
    # Collapse whitespace runs (including newlines) to single spaces.
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _verbatim_match(detected: str) -> bool:
    return _normalize_ocr_noise(detected) == _normalize_ocr_noise(VERBATIM_GOVERNMENT_WARNING)


def analyze_warning(
    detected_text: str,
    present: bool,
    style: WarningStyle | None,
    container_ml: float | None,
) -> GovernmentWarningAnalysis:
    """Apply the four 16.21/16.22 checks and build the analysis payload."""
    from .citations import citation_for_warning  # local import avoids cycle

    deviations: list[WarningDeviation] = []

    if not present or not detected_text:
        return GovernmentWarningAnalysis(
            present=False,
            verbatimMatch=False,
            casingBoldOk=False,
            fontSizeOk=False,
            contrastOk=False,
            separateAndApart=False,
            detectedText=detected_text or "",
            deviations=[
                WarningDeviation(
                    type="missing",
                    message=f"Required Government Warning is missing from the label ({citation_for_warning('wording')}).",
                ),
            ],
        )

    # 1. Verbatim text
    verbatim_ok = _verbatim_match(detected_text)
    if not verbatim_ok:
        deviations.append(WarningDeviation(
            type="wording",
            message=f"Statement wording does not match the required verbatim text ({citation_for_warning('wording')}).",
        ))

    # 2. Casing + bold
    casing_bold_ok = bool(style and style.casing_all_caps and style.heading_bold and not style.body_bold)
    if not casing_bold_ok:
        if style and not style.casing_all_caps:
            deviations.append(WarningDeviation(
                type="casing",
                message=f'"GOVERNMENT WARNING" must be all capitals and bold; detected non-all-caps heading ({citation_for_warning("format")}).',
            ))
        elif style and not style.heading_bold:
            deviations.append(WarningDeviation(
                type="casing",
                message=f'"GOVERNMENT WARNING" must be bold ({citation_for_warning("format")}).',
            ))
        elif style and style.body_bold:
            deviations.append(WarningDeviation(
                type="casing",
                message=f"Warning body text must not be bold; only the GOVERNMENT WARNING heading is bold ({citation_for_warning('format')}).",
            ))
        else:
            deviations.append(WarningDeviation(
                type="casing",
                message=f'"GOVERNMENT WARNING" must be all capitals and bold ({citation_for_warning("format")}).',
            ))

    # 3. Type size vs container
    min_mm = required_warning_mm(container_ml)
    if style is None or style.approx_font_mm is None or min_mm is None:
        # Borderline / unmeasurable — return False so the dashboard treats it
        # as a non-pass; the deviation message asks the agent to confirm.
        font_size_ok = False
        if min_mm is not None:
            deviations.append(WarningDeviation(
                type="fontSize",
                message=(
                    f"Warning type size could not be measured from this image; "
                    f"minimum is {min_mm:.0f} mm for this container "
                    f"({citation_for_warning('format')}). Please confirm manually."
                ),
            ))
    else:
        font_size_ok = style.approx_font_mm + 1e-9 >= min_mm
        if not font_size_ok:
            deviations.append(WarningDeviation(
                type="fontSize",
                message=(
                    f"Warning text appears below the minimum type size for this container "
                    f"(measured ~{style.approx_font_mm:.1f} mm vs required {min_mm:.0f} mm) "
                    f"({citation_for_warning('format')})."
                ),
            ))

    # 4. Contrast + separation
    contrast_ok = bool(style and style.contrast_ok)
    if style and style.contrast_ok is False:
        deviations.append(WarningDeviation(
            type="contrast",
            message=f"Warning text contrast against the background is insufficient ({citation_for_warning('format')}).",
        ))

    separate_ok = bool(style and style.separate_and_apart)
    if style and style.separate_and_apart is False:
        deviations.append(WarningDeviation(
            type="separation",
            message=f'Warning is not "separate and apart" from surrounding label copy ({citation_for_warning("format")}).',
        ))

    return GovernmentWarningAnalysis(
        present=True,
        verbatimMatch=verbatim_ok,
        casingBoldOk=casing_bold_ok,
        fontSizeOk=font_size_ok,
        contrastOk=contrast_ok,
        separateAndApart=separate_ok,
        detectedText=detected_text,
        deviations=deviations,
    )


# Re-export the container parser so the engine can reach it from one import.
__all__ = ["analyze_warning", "parse_net_contents_to_ml"]
