"""The Government Warning engine (27 CFR 16.21 / 16.22).

Three classes of check:
  1. Verbatim text match (16.21) — normalize only OCR noise, never wording
  2. ALL-CAPS heading on 'GOVERNMENT WARNING' (16.22)
  3. Contrast + 'separate and apart' (16.22)

The fourth 16.22 requirement — minimum type size (1/2/3 mm by container
size) — is NOT verified here. A digital image has no DPI/scale reference,
so mm cannot be measured from pixels. TTB inspectors verify this on
physical samples. The UI surfaces this as a documented limitation in the
panel footer.
"""

from __future__ import annotations

import re

from ..constants import VERBATIM_GOVERNMENT_WARNING
from ..extractors.base import WarningStyle
from ..models import GovernmentWarningAnalysis, WarningDeviation
from .net_contents import parse_net_contents_to_ml, required_warning_mm


def _normalize_ocr_noise(s: str) -> str:
    """Normalize ONLY OCR noise.

    We collapse whitespace, reattach line-break hyphenation, and tighten the
    spacing around punctuation that the OCR pass often introduces ('WARNING :'
    -> 'WARNING:', '( 1 )' -> '(1)'). We do NOT rewrite words — paraphrase
    must remain detectable.

    Casing is NOT normalized here. The case fold lives in _verbatim_match
    because TTB allows the BODY of the warning in any case (16.21 fixes the
    wording, 16.22 fixes only the 'GOVERNMENT WARNING' heading style); we
    handle the heading separately via casing_all_caps + heading_bold.
    """
    if not s:
        return ""
    # Reattach line-break hyphenation: "preg-\nnancy" -> "pregnancy"
    s = re.sub(r"-\s*\n\s*", "", s)
    # Collapse whitespace runs (including newlines) to single spaces.
    s = re.sub(r"\s+", " ", s).strip()
    # Tighten OCR-introduced spaces around common punctuation.
    s = re.sub(r"\s+([:,.;])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


_HEADING_ALL_CAPS_RE = re.compile(r"^\s*GOVERNMENT\s+WARNING\s*:", re.MULTILINE)


def _heading_is_all_caps(detected: str) -> bool:
    """Deterministically check whether the 'GOVERNMENT WARNING:' heading on
    the label is rendered in all-caps. The extractor's self-reported
    boolean is unreliable (the model sometimes answers about the body or
    flips on minor styling), so we check the raw OCR text ourselves.

    A label with all-caps heading will have 'GOVERNMENT WARNING:' (or
    similar with whitespace tolerance) appear verbatim in the detected
    text. Title case ('Government Warning:') or lowercase fails the
    regex by definition because we're case-sensitive.
    """
    return bool(detected and _HEADING_ALL_CAPS_RE.search(detected))


def _verbatim_match(detected: str) -> bool:
    """Wording-only comparison after OCR-noise normalization.

    Case-insensitive: an ALL-CAPS body printed verbatim is compliant. The
    separate casing_all_caps / heading_bold checks enforce 27 CFR 16.22 on
    the 'GOVERNMENT WARNING' heading.
    """
    return _normalize_ocr_noise(detected).casefold() == _normalize_ocr_noise(VERBATIM_GOVERNMENT_WARNING).casefold()


# When the detected text is *almost* identical to the canonical warning at this
# character-level similarity, we treat the difference as OCR noise rather than
# a substantive paraphrase. Real labels we see fail here with:
#   - single missing comma ("surgeon general," -> "surgeon general")
#   - "operate" misread as "operte"
#   - missing period before "(2)"
# These are model-transcription slips, not paraphrase. The agent verifies
# visually; the engine records 'verbatimMatch=True' with a 'near_verbatim'
# advisory deviation so the bucket isn't auto-promoted to needs-review.
NEAR_VERBATIM_SIMILARITY = 0.95


def _near_verbatim(detected: str) -> tuple[bool, float]:
    """Return (is_near, similarity_ratio) after OCR-noise normalization +
    case-fold. is_near is True iff the ratio >= NEAR_VERBATIM_SIMILARITY but
    the strings aren't exactly equal."""
    from difflib import SequenceMatcher
    a = _normalize_ocr_noise(detected).casefold()
    b = _normalize_ocr_noise(VERBATIM_GOVERNMENT_WARNING).casefold()
    if not a or a == b:
        return (False, 1.0 if a == b else 0.0)
    ratio = SequenceMatcher(a=a, b=b).ratio()
    return (ratio >= NEAR_VERBATIM_SIMILARITY, ratio)


def _compute_type_size_mm(
    style: WarningStyle | None,
    image_dpi: tuple[int, int] | None,
) -> float | None:
    """Convert the warning bbox + DPI to mm-per-line of body text.

    Returns None if any input is missing. The math:
        mm = (bbox_height / line_count) / dpi_y * 25.4

    We use line_count = body_line_count + 1 (the +1 accounts for the
    'GOVERNMENT WARNING:' heading, which the bbox also covers). This
    biases the estimate slightly low (heading is usually larger than
    body), which is the conservative direction for the check.
    """
    if style is None or image_dpi is None:
        return None
    if style.bbox is None or style.body_line_count is None:
        return None
    _, _, _, h = style.bbox
    line_count = style.body_line_count + 1  # +1 for heading
    if h <= 0 or line_count <= 0:
        return None
    dpi_y = image_dpi[1]
    if dpi_y <= 0:
        return None
    return round((h / line_count) / dpi_y * 25.4, 2)


def analyze_warning(
    detected_text: str,
    present: bool,
    style: WarningStyle | None,
    container_ml: float | None,
    image_dpi: tuple[int, int] | None = None,
) -> GovernmentWarningAnalysis:
    """Apply the four 16.21/16.22 checks and build the analysis payload."""
    from .citations import citation_for_warning  # local import avoids cycle

    deviations: list[WarningDeviation] = []

    if not present or not detected_text:
        return GovernmentWarningAnalysis(
            present=False,
            verbatimMatch=False,
            casingBoldOk=False,
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

    # 1. Verbatim text. If not an exact match, check whether the detected text
    # is *near* verbatim (>= 95% similarity) — typical for OCR slips like a
    # single missing comma or "operte" for "operate". We treat those as
    # verbatim=True with an informational 'near_verbatim' advisory deviation,
    # so the bucket isn't routed to needs-review for a transcription slip.
    # True paraphrase / substantive wording changes still drop below 0.95 and
    # produce verbatim=False with a 'wording' deviation.
    verbatim_ok = _verbatim_match(detected_text)
    if not verbatim_ok:
        is_near, ratio = _near_verbatim(detected_text)
        if is_near:
            verbatim_ok = True  # bucket allows auto-pass on near-verbatim
            deviations.append(WarningDeviation(
                type="near_verbatim",
                message=(
                    f"Warning text closely matches the canonical statement ({ratio:.0%}) "
                    f"but differs in minor characters likely due to OCR noise; please "
                    f"verify visually ({citation_for_warning('wording')})."
                ),
            ))
        else:
            deviations.append(WarningDeviation(
                type="wording",
                message=f"Statement wording does not match the required verbatim text ({citation_for_warning('wording')}).",
            ))

    # 2. Casing + bold. Bold weight cannot be reliably detected from a single
    # image at typical warning-text sizes, so the gate is the more reliable
    # signals: heading must be ALL CAPS, and body must NOT be bold (when the
    # model can tell). heading_bold is recorded but doesn't gate the verdict.
    #
    # Heading-all-caps decision logic (positive-evidence preferred):
    #   1. If the preamble "GOVERNMENT WARNING:" appears literally in the
    #      transcribed text → direct evidence, pass.
    #   2. Else if the extractor's self-reported `casing_all_caps` is True
    #      → the model is making a *visual* observation of the heading style,
    #      which is independent of whether it transcribed the preamble into
    #      `detected_text`. Some Haiku responses include only the warning body
    #      (omitting "GOVERNMENT WARNING:") in detected_text while correctly
    #      reporting the visual caps observation; trusting the flag in that
    #      gap avoids false-positive flags on clearly compliant labels.
    #   3. Else → no positive evidence, treat as non-compliant.
    derived_all_caps = _heading_is_all_caps(detected_text)
    if derived_all_caps:
        casing_all_caps = True
    elif style and style.casing_all_caps:
        casing_all_caps = True
    else:
        casing_all_caps = False
    body_bold = bool(style and style.body_bold)
    casing_bold_ok = casing_all_caps and not body_bold
    if not casing_bold_ok:
        if not casing_all_caps:
            deviations.append(WarningDeviation(
                type="casing",
                message=f'"GOVERNMENT WARNING" must be all capitals and bold; detected non-all-caps heading ({citation_for_warning("format")}).',
            ))
        elif body_bold:
            deviations.append(WarningDeviation(
                type="casing",
                message=f"Warning body text must not be bold; only the GOVERNMENT WARNING heading is bold ({citation_for_warning('format')}).",
            ))
        else:
            deviations.append(WarningDeviation(
                type="casing",
                message=f'"GOVERNMENT WARNING" must be all capitals and bold ({citation_for_warning("format")}).',
            ))

    # 3. Type size (27 CFR 16.22). Computed deterministically when the
    # extractor returned a warning bbox AND the image has DPI metadata
    # (TTB-scraped labels do, phone photos don't). Otherwise omitted
    # entirely — the agent confirms manually for unmeasurable inputs.
    measured_mm = _compute_type_size_mm(style, image_dpi)
    min_mm = required_warning_mm(container_ml)
    if min_mm is None and measured_mm is not None:
        # Container size unknown (net contents not declared on the COLA
        # application — TTB Form 5100.31 doesn't carry it). Default to
        # the 2 mm threshold which covers the ≤3 L consumer-bottle range
        # (~95% of submissions). The deviation message flags this is the
        # default threshold; the agent confirms for unusual sizes.
        min_mm = 2.0
    font_size_ok: bool | None = None
    if measured_mm is not None and min_mm is not None:
        # Allow a 10% tolerance — the bbox is a model estimate, ±5-10%
        # error is realistic. Substantially-below = real flag.
        font_size_ok = measured_mm >= (min_mm * 0.9)
        if not font_size_ok:
            deviations.append(WarningDeviation(
                type="fontSize",
                message=(
                    f"Warning text measures ~{measured_mm:.2f} mm per line; "
                    f"27 CFR 16.22 requires {min_mm:.0f} mm minimum for this "
                    f"container size. Below threshold by "
                    f"{(min_mm - measured_mm) / min_mm:.0%}."
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
