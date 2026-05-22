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


def verify(
    extracted: ExtractedLabel,
    app: ApplicationData,
    *,
    contains_added_flavors: bool = False,
) -> VerificationResult:
    """Turn raw model observations into the public VerificationResult."""

    cite = citation_for_field(app.beverageType)
    specs = applies_to(app, contains_added_flavors=contains_added_flavors)

    fields: list[VerificationField] = []
    for spec in specs:
        declared = declared_value(app, spec)
        extracted_field = extracted.fields.get(spec.label_name)

        if extracted_field is None or not extracted_field.value:
            # Mandatory field not on the label -> flag with citation.
            fields.append(VerificationField(
                fieldName=spec.label_name,
                declaredValue=declared,
                extractedValue="",
                status="flag",
                confidence=extracted_field.confidence if extracted_field else 0.0,
                regulationCite=cite,
                note=f"Mandatory field missing from the label ({cite}).",
            ))
            continue

        verdict = classify_field(declared, extracted_field.value)
        fields.append(VerificationField(
            fieldName=spec.label_name,
            declaredValue=declared,
            extractedValue=extracted_field.value,
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
