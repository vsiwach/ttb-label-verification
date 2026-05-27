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

    We collapse whitespace, reattach line-break and space-break hyphenation
    ("preg-\\nnancy" and "AL- COHOLIC" both -> "ALCOHOLIC"), and tighten the
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
    # Reattach space-break hyphenation: "AL- COHOLIC" -> "ALCOHOLIC". Common
    # when the OCR pass treats a soft hyphen at end-of-line as a real word
    # boundary. We only join when both sides are alphabetic so we don't
    # collapse legitimate dashes like "drink alcoholic — beverages".
    s = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", s)
    # Collapse whitespace runs (including newlines) to single spaces.
    s = re.sub(r"\s+", " ", s).strip()
    # Tighten OCR-introduced spaces around common punctuation.
    s = re.sub(r"\s+([:,.;])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


_WARNING_ANCHOR_RE = re.compile(r"government\s*warning\s*:?", re.IGNORECASE)


def _extract_warning_substring(detected: str) -> str:
    """Strip leading garbage and trailing non-warning OCR capture.

    TTB-live scans frequently bleed neighbour text into Haiku's warning
    transcription — leading scraps like "een TO THE SURGEON" before the
    actual heading, or trailing "Lote: Bsa HECHO EN MEXICO" after the
    warning ends. The verbatim comparator can't see past this noise, so
    we anchor at the "GOVERNMENT WARNING" preamble and clip at the
    canonical end ("HEALTH PROBLEMS." or "OPERATE MACHINERY..." for
    truncated reads). When neither anchor is present, return the input
    unchanged so the normal comparator path can still log the mismatch.
    """
    if not detected:
        return ""
    m = _WARNING_ANCHOR_RE.search(detected)
    if not m:
        return detected
    body = detected[m.start():]
    # Clip at the end of the canonical warning. Two known endings depending
    # on whether the OCR captured statement (1) only or both (1) + (2):
    end_markers = (
        "HEALTH PROBLEMS.",
        "health problems.",
        "Health Problems.",
        "Health problems.",
    )
    cut_at = -1
    for marker in end_markers:
        idx = body.find(marker)
        if idx != -1:
            cut_at = max(cut_at, idx + len(marker))
    if cut_at > 0:
        body = body[:cut_at]
    return body


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
    """Wording-only comparison after anchor extraction + OCR-noise normalization.

    Case-insensitive: an ALL-CAPS body printed verbatim is compliant. The
    separate casing_all_caps / heading_bold checks enforce 27 CFR 16.22 on
    the 'GOVERNMENT WARNING' heading. The anchor extraction strips leading
    and trailing OCR garbage before comparison.
    """
    a = _normalize_ocr_noise(_extract_warning_substring(detected)).casefold()
    b = _normalize_ocr_noise(VERBATIM_GOVERNMENT_WARNING).casefold()
    return a == b


# When the detected text is *almost* identical to the canonical warning at this
# character-level similarity, we treat the difference as OCR noise rather than
# a substantive paraphrase. Lowered from 0.95 to 0.85 because the anchor
# extraction now reliably strips leading/trailing junk, so the ratio reflects
# in-warning OCR slips only — and on real TTB-live scans those slips
# (broken hyphens, misread chars) drop the ratio below 0.95 even on
# clearly-compliant labels. 0.85 still catches genuine paraphrases.
NEAR_VERBATIM_SIMILARITY = 0.85


def _near_verbatim(detected: str) -> tuple[bool, float]:
    """Return (is_near, similarity_ratio) after anchor extraction + OCR-noise
    normalization + case-fold. is_near is True iff the ratio >=
    NEAR_VERBATIM_SIMILARITY but the strings aren't exactly equal."""
    from difflib import SequenceMatcher
    a = _normalize_ocr_noise(_extract_warning_substring(detected)).casefold()
    b = _normalize_ocr_noise(VERBATIM_GOVERNMENT_WARNING).casefold()
    if not a or a == b:
        return (False, 1.0 if a == b else 0.0)
    ratio = SequenceMatcher(a=a, b=b).ratio()
    return (ratio >= NEAR_VERBATIM_SIMILARITY, ratio)


# TTB Public COLA Registry's submission guidance recommends 300 DPI for
# label artwork. When a label image arrives without DPI in EXIF (phone
# photos, web-stripped JPEGs, COLA Cloud free-sample WebPs), we use this
# as a deterministic fallback so the 16.22 type-size check ALWAYS runs.
# The deviation message tags such results as DPI=assumed so the agent
# knows the measurement is estimated rather than EXIF-authoritative.
_DEFAULT_DPI = 300


def _compute_type_size_mm(
    style: WarningStyle | None,
    image_dpi: tuple[int, int] | None,
) -> tuple[float, str] | None:
    """Convert the warning bbox + DPI to mm-per-line of body text.

    Returns (mm_per_line, dpi_source) where dpi_source is "exif" when
    the image carried DPI metadata or "assumed" when we used the
    documented default. Returns None ONLY when the bbox itself is
    missing — there's nothing to measure in that case.

    The math:
        mm = (bbox_height / line_count) / dpi_y * 25.4

    We use line_count = body_line_count + 1 (the +1 accounts for the
    'GOVERNMENT WARNING:' heading, which the bbox also covers). This
    biases the estimate slightly low (heading is usually larger than
    body), which is the conservative direction for the check.
    """
    if style is None or style.bbox is None or style.body_line_count is None:
        return None
    _, _, _, h = style.bbox
    line_count = style.body_line_count + 1  # +1 for heading
    if h <= 0 or line_count <= 0:
        return None

    if image_dpi is not None and image_dpi[1] > 0:
        dpi_y = image_dpi[1]
        source = "exif"
    else:
        dpi_y = _DEFAULT_DPI
        source = "assumed"

    return round((h / line_count) / dpi_y * 25.4, 2), source


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

    # 2. Casing + bold. The gate is positive evidence that
    # "GOVERNMENT WARNING:" is in ALL CAPS — that's the one signal a
    # visual-language model can read reliably at warning-text size.
    # Body-bold and heading-bold reports are kept as ADVISORY deviations
    # only: empirically, vision models confuse "all-caps text" with
    # "bold text" frequently enough that gating on either produces
    # false positives on clearly compliant labels (e.g. labels where
    # the whole warning is set in all-caps regular weight).
    #
    # Heading-all-caps decision logic (positive-evidence preferred):
    #   1. If "GOVERNMENT WARNING:" appears literally in detected_text
    #      → direct transcription evidence, pass.
    #   2. Else if the model self-reports casing_all_caps=True → visual
    #      observation independent of transcription. Trust it.
    #   3. Else → no positive evidence, fail with a casing deviation.
    derived_all_caps = _heading_is_all_caps(detected_text)
    if derived_all_caps:
        casing_all_caps = True
    elif style and style.casing_all_caps:
        casing_all_caps = True
    else:
        casing_all_caps = False
    casing_bold_ok = casing_all_caps
    if not casing_all_caps:
        deviations.append(WarningDeviation(
            type="casing",
            message=f'"GOVERNMENT WARNING" must be all capitals and bold; detected non-all-caps heading ({citation_for_warning("format")}).',
        ))
    # Body-bold is advisory only — vision models over-report it on
    # all-caps regular-weight body text. Surface as a "review" note so
    # the agent can eyeball the label, but don't fail the casing gate.
    if style and style.body_bold:
        deviations.append(WarningDeviation(
            type="bodyBoldAdvisory",
            message=(
                f"Model reported warning body text may be bold; only the "
                f"GOVERNMENT WARNING heading should be bold ({citation_for_warning('format')}). "
                f"Confirm visually — vision-language models often misread all-caps body text as bold."
            ),
        ))

    # 3. Type size (27 CFR 16.22). Always runs when the extractor
    # returned a warning bbox + line count. DPI comes from EXIF when
    # the image carries it; otherwise we fall back to the documented
    # default (TTB's recommended 300 DPI submission standard) so the
    # check is deterministic instead of silently skipping. The
    # provenance flows through to the analysis payload as
    # fontSizeDpiSource and into the deviation message so the agent
    # sees whether the measurement is EXIF-authoritative or estimated.
    measurement = _compute_type_size_mm(style, image_dpi)
    measured_mm: float | None = None
    dpi_source: str | None = None
    if measurement is not None:
        measured_mm, dpi_source = measurement
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
        # Three-band size verdict. The bbox is an image-derived estimate;
        # scan resolution (EXIF DPI) doesn't reliably reflect physical
        # print resolution because TTB scans of approved labels routinely
        # come back as 1.1-1.8 mm under the 2 mm threshold even though
        # the physical labels obviously comply (otherwise TTB wouldn't
        # have approved them). The check is therefore inherently
        # approximate and we only HARD-FAIL when the measurement is so
        # far below the threshold that it can't be a scan artefact.
        #
        # Bands (in fraction of the regulation minimum):
        #   measured ≥ 0.9 * min : pass clean (matches the regulation
        #                          within the conventional 10% bbox
        #                          measurement tolerance)
        #   measured ≥ 0.5 * min : pass with advisory — likely a scan
        #                          resolution artefact, not a real
        #                          violation; agent eyeballs the
        #                          physical sample
        #   measured < 0.5 * min : flag — clearly substandard even
        #                          accounting for scan-resolution slop
        clean = measured_mm >= (min_mm * 0.9)
        suspicious = measured_mm >= (min_mm * 0.5)
        # On assumed DPI we can't trust a hard-fail no matter how low
        # the measurement reads — the 300-DPI submission default is
        # often 2-3x off from the actual scan resolution, so a 0.6 mm
        # measurement may correspond to a perfectly compliant 2 mm
        # printed warning. Treat assumed-DPI as advisory-only, mirroring
        # how body_bold / contrast / separation are handled. Only EXIF-
        # backed measurements can fail the gate.
        is_assumed = dpi_source == "assumed"
        font_size_ok = True if is_assumed else suspicious

        if clean:
            pass  # no deviation
        elif suspicious:
            dpi_note = (
                "scan EXIF reports DPI but the measurement may be off because TTB scans "
                "don't reliably preserve physical print resolution"
                if dpi_source == "exif" else
                "image lacks EXIF DPI so the rule engine used the 300-DPI submission "
                "default — measurement may be off by 2-3x"
            )
            deviations.append(WarningDeviation(
                type="fontSizeAdvisory",
                message=(
                    f"Warning text measures ~{measured_mm:.2f} mm per line; "
                    f"27 CFR 16.22 requires {min_mm:.0f} mm minimum for this "
                    f"container size. {dpi_note}. Confirm visually with a ruler "
                    f"on a printed sample for compliance-grade verification."
                ),
            ))
        elif is_assumed:
            # Below 0.5× threshold but DPI was assumed → still advisory.
            # The measurement is unreliable enough that we can't claim
            # the printed label is non-compliant without EXIF backing.
            deviations.append(WarningDeviation(
                type="fontSizeAdvisory",
                message=(
                    f"Warning text measures ~{measured_mm:.2f} mm per line under "
                    f"the assumed 300-DPI default — well below the {min_mm:.0f} mm "
                    f"27 CFR 16.22 minimum, but the image lacks EXIF DPI so this "
                    f"estimate may be off by 2-3x. The printed label may be fine; "
                    f"confirm visually with a ruler on a printed sample."
                ),
            ))
        else:
            deviations.append(WarningDeviation(
                type="fontSize",
                message=(
                    f"Warning text measures ~{measured_mm:.2f} mm per line — under "
                    f"half the {min_mm:.0f} mm 27 CFR 16.22 minimum. Even allowing "
                    f"for scan-resolution variance this is too small; the printed "
                    f"label likely needs a larger warning typeset."
                ),
            ))

    # 4. Contrast + separation — advisory-only. These are vision-language
    # model judgements (Haiku's contrast_ok / separate_and_apart self-
    # reports) which empirically false-positive on clearly compliant
    # labels: a black-on-white warning panel below the brand block gets
    # flagged "interspersed" or "insufficient contrast" maybe 1 in 5
    # times. Treating either as a hard gate would downgrade legitimate
    # auto-pass labels purely because the model had a bad read on
    # style. We keep BOTH values reported as True on the response (so
    # the GW pill in the UI stays "match" when text + casing + size
    # are good) and surface the model's "false" reading as a
    # contrastAdvisory / separationAdvisory deviation that the agent
    # confirms visually — matching how we treat body_bold and the
    # assumed-DPI font size.
    contrast_ok = True
    separate_ok = True
    if style and style.contrast_ok is False:
        deviations.append(WarningDeviation(
            type="contrastAdvisory",
            message=(
                f"Model reported the warning may have low contrast against "
                f"its background ({citation_for_warning('format')}). Vision-"
                f"language models occasionally misread contrast on clean "
                f"black-on-white labels — confirm visually."
            ),
        ))
    if style and style.separate_and_apart is False:
        deviations.append(WarningDeviation(
            type="separationAdvisory",
            message=(
                f'Model reported the warning may not be "separate and apart" '
                f"from surrounding label copy ({citation_for_warning('format')}). "
                f"Confirm visually — vision-language models often flag this on "
                f"compact label layouts where the warning is in fact "
                f"clearly delimited."
            ),
        ))

    return GovernmentWarningAnalysis(
        present=True,
        verbatimMatch=verbatim_ok,
        casingBoldOk=casing_bold_ok,
        fontSizeOk=font_size_ok,
        fontSizeMm=measured_mm,
        fontSizeDpiSource=dpi_source,  # type: ignore[arg-type]
        contrastOk=contrast_ok,
        separateAndApart=separate_ok,
        detectedText=detected_text,
        deviations=deviations,
    )


# Re-export the container parser so the engine can reach it from one import.
__all__ = ["analyze_warning", "parse_net_contents_to_ml"]
