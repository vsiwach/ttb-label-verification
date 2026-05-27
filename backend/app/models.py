"""Pydantic models that mirror the TypeScript contract in src/api/types.ts.

JSON field names match the TS interface exactly (camelCase). Pydantic serializes
these by field name, so the wire format is identical to the frontend's mock.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .constants import WARNING_REGULATION

FieldStatus = Literal["match", "likely", "flag"]
BeverageType = Literal["spirits", "wine", "beer", "malt"]
BatchGroup = Literal["auto-pass", "needs-confirm", "needs-review"]


class VerificationField(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fieldName: str
    declaredValue: str
    extractedValue: str
    status: FieldStatus
    confidence: float
    evidenceCropUrl: Optional[str] = None
    regulationCite: Optional[str] = None
    note: Optional[str] = None


class WarningDeviation(BaseModel):
    type: str
    message: str


class GovernmentWarningAnalysis(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    present: bool
    verbatimMatch: bool
    casingBoldOk: bool
    contrastOk: bool
    separateAndApart: bool
    detectedText: str
    deviations: list[WarningDeviation] = Field(default_factory=list)
    regulation: Literal["27 CFR 16.21/16.22"] = WARNING_REGULATION  # type: ignore[assignment]
    # 27 CFR 16.22 minimum type size. Computed deterministically every
    # time: the extractor returns the warning bounding box, the image
    # pipeline reads DPI from EXIF when present, and the rules engine
    # falls back to a documented default DPI (TTB submission standard
    # of 300) when EXIF doesn't carry it. The deterministic answer
    # means the rules engine always produces a verdict instead of
    # silently skipping — see fontSizeMm + fontSizeDpiSource for the
    # measurement provenance.
    fontSizeOk: Optional[bool] = None
    # Measured mm per line of warning body text. Optional only when the
    # warning is missing entirely (no bbox to measure). The agent sees
    # the actual number so they can sanity-check against the printed
    # label without re-doing the math.
    fontSizeMm: Optional[float] = None
    # Provenance of the DPI used to convert pixels → mm:
    #   "exif"    : DPI read from the JPEG/PNG header (authoritative)
    #   "assumed" : EXIF missing; used a documented default. The agent
    #               sees this in the deviation message and can request
    #               a higher-resolution scan for compliance-grade work.
    fontSizeDpiSource: Optional[Literal["exif", "assumed"]] = None


class ImageQuality(BaseModel):
    score: float
    legible: bool
    note: Optional[str] = None


class TimingInfo(BaseModel):
    """Per-request timing breakdown, attached to every VerificationResult.

    inference_mode is the extractor that did the read (claude-code, cloud,
    modal, sft, mock); it lets the UI show whether the user is on the local
    dev path or the deployed Modal+Qwen production path.

    Times are wall-clock milliseconds. extractorMs is the bulk of the time
    (model inference + network); rulesMs is the deterministic rules-engine
    pass; totalMs covers the whole pipeline including image-quality
    measurement and crop generation.
    """
    inferenceMode: str
    extractorMs: int
    rulesMs: int
    totalMs: int
    # Which extractor combination actually served the request. Distinct
    # from inferenceMode (the configured mode): on the modal path this
    # is "modal+haiku" when Qwen returned in time, or "haiku-fallback"
    # when Modal was cold and Haiku covered all six fields alone. Lets
    # the UI surface "warming up — re-run for higher accuracy" without
    # the user having to inspect logs.
    extractorSource: Optional[str] = None


class VerificationResult(BaseModel):
    fields: list[VerificationField]
    governmentWarning: GovernmentWarningAnalysis
    imageQuality: ImageQuality
    timing: Optional[TimingInfo] = None


class ApplicationData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    brandName: str
    # The COLA form's Fanciful Name / Product Name (TTB Form 5100.31 Field 16).
    # Real labels often print this MORE PROMINENTLY than the registered brand
    # (e.g., brewery 'Half Acre' + product 'NEON FOOTHILLS' — the label has
    # 'NEON FOOTHILLS' as the largest text). When supplied, the engine accepts
    # a label-extracted brand match against EITHER brandName or productName.
    productName: Optional[str] = None
    classType: str
    alcoholContent: str
    netContents: str
    bottlerNameAddress: str
    countryOfOrigin: Optional[str] = None
    beverageType: BeverageType
    colaNumber: Optional[str] = None


class BatchItemResult(BaseModel):
    id: str
    fileName: str
    thumbnailUrl: str
    result: VerificationResult
    group: BatchGroup


def group_for(result: VerificationResult) -> BatchGroup:
    """Mirror of groupFor() in src/api/types.ts.

    needs-review  — any field flag, warning missing, or warning not verbatim
    needs-confirm — any field 'likely'
    auto-pass     — otherwise
    """
    has_flag = (
        any(f.status == "flag" for f in result.fields)
        or result.governmentWarning.present is False
        or result.governmentWarning.verbatimMatch is False
    )
    has_likely = any(f.status == "likely" for f in result.fields)
    if has_flag:
        return "needs-review"
    if has_likely:
        return "needs-confirm"
    return "auto-pass"
