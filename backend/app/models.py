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
    fontSizeOk: bool
    contrastOk: bool
    separateAndApart: bool
    detectedText: str
    deviations: list[WarningDeviation] = Field(default_factory=list)
    regulation: Literal["27 CFR 16.21/16.22"] = WARNING_REGULATION  # type: ignore[assignment]


class ImageQuality(BaseModel):
    score: float
    legible: bool
    note: Optional[str] = None


class VerificationResult(BaseModel):
    fields: list[VerificationField]
    governmentWarning: GovernmentWarningAnalysis
    imageQuality: ImageQuality


class ApplicationData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    brandName: str
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
