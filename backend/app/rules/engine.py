"""verify(extracted, applicationData) -> VerificationResult.

This is what /api/verify calls after the extractor returns. It is pure and
synchronous — every match/likely/flag decision and every Government Warning
verdict happens here, with a regulation citation attached.
"""

from __future__ import annotations

from ..extractors.base import ExtractedLabel
from ..models import (
    ApplicationData,
    ImageQuality,
    VerificationField,
    VerificationResult,
)
from .citations import citation_for_field
from .field_match import classify_field
from .government_warning import analyze_warning
from .mandatory_fields import applies_to, declared_value
from .net_contents import parse_net_contents_to_ml


import re as _re

# COLA registry's class/type codes are taxonomy buckets ('beer', 'ale', 'table
# red wine'); the LABEL prints specific designations ('Czech-Style Pilsner',
# 'New Zealand Style Pilsner', 'Sonoma County Chardonnay'). TTB approves the
# COLA against the broader bucket so a label-side specific designation under
# a known umbrella is a match, not a flag.
_UMBRELLA_CLASSES = {
    "beer", "ale", "wine", "table red wine", "table white wine",
    "table flavored wine", "malt beverages specialities",
    "malt beverages specialities - flavored", "sparkling wine/champagne",
    "dessert /port/sherry/(cooking) wine", "rose wine",
    "honey based table wine", "other specialties & proprietaries",
}


def _is_umbrella_class(declared: str) -> bool:
    return declared.strip().lower() in _UMBRELLA_CLASSES


def _abv_percent(s: str) -> float | None:
    """Pull the first percentage out of an alcohol-content string."""
    if not s:
        return None
    m = _re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", s)
    return float(m.group(1)) if m else None


def _normalize_country_of_origin(extracted: str) -> str:
    """Strip the common 'Product of X' / 'Imported from X' / 'Made in X' prefixes
    that real labels print but COLA application forms do not.
    """
    if not extracted:
        return extracted
    low = extracted.strip().lower()
    for prefix in ("product of ", "produce of ", "imported from ", "made in ",
                   "bottled in ", "distilled in "):
        if low.startswith(prefix):
            return extracted.strip()[len(prefix):]
    return extracted


# Class/type tokens that indicate a malt beverage contains added nonbeverage
# flavors and therefore (per 27 CFR 7.63) requires an ABV statement.
_FLAVORED_MALT_TOKENS = (
    "seltzer", "hard seltzer", "flavored malt", "flavored beer",
    "fruit beer", "spiked", "ready to drink", "rtd",
)


def _looks_like_flavored_malt(app: ApplicationData) -> bool:
    ct = (app.classType or "").lower()
    return any(t in ct for t in _FLAVORED_MALT_TOKENS)


def verify(
    extracted: ExtractedLabel,
    app: ApplicationData,
    *,
    contains_added_flavors: bool | None = None,
) -> VerificationResult:
    """Turn raw model observations into the public VerificationResult.

    contains_added_flavors: explicit override; if None, auto-detect from the
    application's class type so the rules engine catches flavored-malt /
    seltzer products without callers having to flag them.
    """

    if contains_added_flavors is None:
        contains_added_flavors = _looks_like_flavored_malt(app)
    cite = citation_for_field(app.beverageType)
    specs = applies_to(app, contains_added_flavors=contains_added_flavors)

    fields: list[VerificationField] = []
    for spec in specs:
        declared = declared_value(app, spec)
        extracted_field = extracted.fields.get(spec.label_name)

        if extracted_field is None or not extracted_field.value:
            # Field not visible on this image. Real COLAs are multi-image —
            # ABV / net contents / bottler are often on a different panel from
            # the Government Warning. We mark this as 'likely' (route to
            # needs-confirm) with a clear note rather than a hard flag.
            fields.append(VerificationField(
                fieldName=spec.label_name,
                declaredValue=declared,
                extractedValue="",
                status="likely",
                confidence=extracted_field.confidence if extracted_field else 0.0,
                regulationCite=cite,
                note=f"Could not verify on this label image; may be on another panel ({cite}).",
            ))
            continue

        if not declared:
            # Application omitted this field (e.g. COLA form lacks bottler line on
            # some exports). The label content is shown for the agent; treat as
            # match for bucketing purposes — the form-level check happens elsewhere.
            fields.append(VerificationField(
                fieldName=spec.label_name,
                declaredValue="",
                extractedValue=extracted_field.value,
                status="match",
                confidence=extracted_field.confidence,
                regulationCite=cite,
                note="Application did not declare this field; label content shown for review.",
            ))
            continue

        # Per-field normalization for real-world realities the COLA form doesn't capture:
        extracted_value = extracted_field.value
        if spec.label_name == "Country of origin":
            # Strip 'Product of X' prefix; case is not meaningful (16.21 doesn't require it).
            extracted_value = _normalize_country_of_origin(extracted_value)
            verdict = classify_field(declared.title(), extracted_value.title())
        elif spec.label_name == "Class & type" and _is_umbrella_class(declared):
            # Form declared a taxonomy umbrella ('beer'); label printed a specific
            # designation. Any non-empty designation is consistent.
            from .field_match import FieldVerdict
            verdict = FieldVerdict(
                status="match",
                normalized_declared=declared.lower(),
                normalized_extracted=extracted_value.lower(),
                similarity=1.0,
                note="Form declared an umbrella class; label's specific designation is consistent.",
            )
        elif spec.label_name == "Alcohol content":
            # Compare numeric percent (within 0.1) — formats vary ("% Alc./Vol.",
            # "% ABV", "% by volume", "Proof") but the percentage is what matters.
            pd, pe = _abv_percent(declared), _abv_percent(extracted_value)
            if pd is not None and pe is not None and abs(pd - pe) <= 0.1:
                from .field_match import FieldVerdict
                verdict = FieldVerdict(
                    status="match",
                    normalized_declared=f"{pd}%", normalized_extracted=f"{pe}%",
                    similarity=1.0,
                )
            else:
                verdict = classify_field(declared, extracted_value)
        elif spec.label_name == "Net contents":
            # Real labels often print multi-unit displays ('12L 40.5 fl oz 2.53 pint');
            # COLA carries a single unit. Compare semantically when both parse.
            ml_d = parse_net_contents_to_ml(declared)
            ml_e = parse_net_contents_to_ml(extracted_value)
            if ml_d is not None and ml_e is not None and ml_d > 0:
                if abs(ml_d - ml_e) / max(ml_d, ml_e) <= 0.05:
                    # Numeric volumes within 5% — treat as match regardless of unit display.
                    from .field_match import FieldVerdict
                    verdict = FieldVerdict(
                        status="match",
                        normalized_declared=f"{ml_d:.0f} mL",
                        normalized_extracted=f"{ml_e:.0f} mL",
                        similarity=1.0,
                    )
                else:
                    verdict = classify_field(declared, extracted_value)
            else:
                verdict = classify_field(declared, extracted_value)
        else:
            verdict = classify_field(declared, extracted_value)
        fields.append(VerificationField(
            fieldName=spec.label_name,
            declaredValue=declared,
            extractedValue=extracted_field.value,  # show what was printed
            status=verdict.status,
            confidence=extracted_field.confidence,
            regulationCite=cite,
            note=verdict.note,
        ))

    # Government Warning analysis (16.21 / 16.22)
    container_ml = parse_net_contents_to_ml(app.netContents)
    gw = analyze_warning(
        detected_text=extracted.warning_text,
        present=extracted.warning_present,
        style=extracted.warning_style,
        container_ml=container_ml,
    )

    image_quality = ImageQuality(
        score=extracted.image_quality_score,
        legible=extracted.image_legible,
        note=extracted.image_quality_note,
    )

    return VerificationResult(fields=fields, governmentWarning=gw, imageQuality=image_quality)
