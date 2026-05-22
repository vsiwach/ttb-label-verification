"""MockExtractor — returns observations matching the three demo scenarios.

The verdicts are NOT baked in here. We only emit raw observations (what the
model 'saw'); the rules engine will turn these into match / likely / flag.
"""

from __future__ import annotations

from ..constants import VERBATIM_GOVERNMENT_WARNING
from ..models import BeverageType
from .base import ExtractedField, ExtractedLabel, LabelExtractor, WarningStyle


# Hand-tuned per-scenario observations. The extractor key is the application's
# brand name; the rules engine compares these strings against the declared
# application values.
_SCENARIO_A = ExtractedLabel(
    fields={
        "Brand name":          ExtractedField(value="OLD TOM DISTILLERY",                          confidence=0.99),
        "Class & type":        ExtractedField(value="Kentucky Straight Bourbon Whiskey",           confidence=0.97),
        "Alcohol content":     ExtractedField(value="45% Alc./Vol. (90 Proof)",                    confidence=0.96),
        "Net contents":        ExtractedField(value="750 mL",                                      confidence=0.99),
        "Bottler name/address": ExtractedField(value="Old Tom Distillery, Frankfort, KY",          confidence=0.95),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING,
    warning_present=True,
    warning_style=WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=2.2, contrast_ok=True, separate_and_apart=True,
    ),
    image_quality_score=0.92,
    image_legible=True,
    image_quality_note="Sharp; even lighting.",
)

_SCENARIO_B = ExtractedLabel(
    fields={
        "Brand name":          ExtractedField(value="Stone's Throw",                                confidence=0.88),
        "Class & type":        ExtractedField(value="California Red Table Wine",                    confidence=0.96),
        "Alcohol content":     ExtractedField(value="13.5% Alc./Vol.",                              confidence=0.95),
        "Net contents":        ExtractedField(value="700 mL",                                       confidence=0.97),
        "Bottler name/address": ExtractedField(value="Stone's Throw Cellars, Sonoma, CA",           confidence=0.94),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING,
    warning_present=True,
    warning_style=WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=2.1, contrast_ok=True, separate_and_apart=True,
    ),
    image_quality_score=0.86,
    image_legible=True,
)

_SCENARIO_C_WARNING_TEXT = (
    "Government Warning: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Drinking alcoholic beverages impairs your ability to drive a car or operate "
    "machinery and may cause health problems."
)

_SCENARIO_C = ExtractedLabel(
    fields={
        "Brand name":          ExtractedField(value="NORTHWIND BREWING",                            confidence=0.98),
        "Class & type":        ExtractedField(value="India Pale Ale",                               confidence=0.95),
        # Beer/malt ABV is optional — extractor reports empty if not on the label.
        "Alcohol content":     ExtractedField(value="6.8% Alc./Vol.",                               confidence=0.93),
        "Net contents":        ExtractedField(value="12 FL. OZ.",                                   confidence=0.91),
        "Bottler name/address": ExtractedField(value="Northwind Brewing Co., Bend, OR",             confidence=0.93),
    },
    warning_text=_SCENARIO_C_WARNING_TEXT,
    warning_present=True,
    warning_style=WarningStyle(
        # 'Government Warning' is Title Case, not all caps → casing_all_caps=False
        casing_all_caps=False, heading_bold=False, body_bold=False,
        approx_font_mm=0.8,   # below the 12 FL OZ (≤237 mL) → 1 mm minimum
        contrast_ok=True, separate_and_apart=True,
    ),
    image_quality_score=0.79,
    image_legible=True,
    image_quality_note="Warning band area is lower-resolution than the rest of the label.",
)


def _pick(brand_name: str) -> ExtractedLabel:
    b = (brand_name or "").upper()
    if "STONE" in b:
        return _SCENARIO_B
    if "NORTHWIND" in b:
        return _SCENARIO_C
    return _SCENARIO_A


class MockExtractor(LabelExtractor):
    """Returns deterministic observations matching the three demo scenarios.

    The application's brand name selects which scenario is returned, so this
    extractor never needs a real image — image bytes are accepted and ignored.
    """

    # The endpoint passes the brand_name through a side channel; for the mock
    # we use beverage_type as a fallback hint, but in practice main.py looks up
    # the right scenario by brand name. Keeping the interface clean: we route
    # by an internal hint set when the extractor is constructed for a request.

    def __init__(self, brand_hint: str = "") -> None:
        self._brand_hint = brand_hint

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        return _pick(self._brand_hint)
