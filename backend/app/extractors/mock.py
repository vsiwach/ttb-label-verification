"""MockExtractor — returns observations matching the synthetic demo labels.

The verdicts are NOT baked in here. We only emit raw observations (what the
model 'saw'); the rules engine turns these into match / likely / flag. The
synthetic eval (test/synthetic + run_eval.py --synthetic) is the deterministic
CI gate, so this mock covers every synthetic case there.
"""

from __future__ import annotations

from ..constants import VERBATIM_GOVERNMENT_WARNING
from ..models import BeverageType
from .base import ExtractedField, ExtractedLabel, LabelExtractor, WarningStyle


def _good_style(font_mm: float = 2.2) -> WarningStyle:
    return WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=font_mm, contrast_ok=True, separate_and_apart=True,
    )


# Scenario A — OLD TOM DISTILLERY (all match, compliant warning)
_SCENARIO_A = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("OLD TOM DISTILLERY", 0.99),
        "Class & type":         ExtractedField("Kentucky Straight Bourbon Whiskey", 0.97),
        "Alcohol content":      ExtractedField("45% Alc./Vol. (90 Proof)", 0.96),
        "Net contents":         ExtractedField("750 mL", 0.99),
        "Bottler name/address": ExtractedField("Old Tom Distillery, Frankfort, Kentucky", 0.95),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
    warning_style=_good_style(),
    image_quality_score=0.92, image_legible=True, image_quality_note="Sharp; even lighting.",
)

# Scenario B — STONE'S THROW (brand casing -> likely, net contents 700 -> flag)
_SCENARIO_B = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("Stone's Throw", 0.88),
        "Class & type":         ExtractedField("California Red Table Wine", 0.96),
        "Alcohol content":      ExtractedField("13.5% Alc./Vol.", 0.95),
        "Net contents":         ExtractedField("700 mL", 0.97),
        "Bottler name/address": ExtractedField("Stone's Throw Cellars, Sonoma, California", 0.94),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
    warning_style=_good_style(2.1),
    image_quality_score=0.86, image_legible=True,
)

# Scenario C — NORTHWIND BREWING (warning title-case + paraphrased + small font)
_SCENARIO_C_WARNING = (
    "Government Warning: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Drinking alcoholic beverages impairs your ability to drive a car or operate "
    "machinery and may cause health problems."
)
_SCENARIO_C = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("NORTHWIND BREWING", 0.98),
        "Class & type":         ExtractedField("India Pale Ale", 0.95),
        "Alcohol content":      ExtractedField("6.8% Alc./Vol.", 0.93),
        "Net contents":         ExtractedField("12 FL OZ", 0.91),
        "Bottler name/address": ExtractedField("Northwind Brewing Co., Bend, Oregon", 0.93),
    },
    warning_text=_SCENARIO_C_WARNING, warning_present=True,
    warning_style=WarningStyle(
        casing_all_caps=False, heading_bold=False, body_bold=False,
        approx_font_mm=0.8, contrast_ok=True, separate_and_apart=True,
    ),
    image_quality_score=0.79, image_legible=True,
    image_quality_note="Warning band area is lower-resolution than the rest of the label.",
)

# Scenario D — CEDAR & SAGE (missing Government Warning)
_SCENARIO_D = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("CEDAR & SAGE", 0.98),
        "Class & type":         ExtractedField("Distilled Gin", 0.96),
        "Alcohol content":      ExtractedField("40% Alc./Vol. (80 Proof)", 0.95),
        "Net contents":         ExtractedField("750 mL", 0.99),
        "Bottler name/address": ExtractedField("Cedar & Sage Spirits, Portland, Oregon", 0.94),
    },
    warning_text="", warning_present=False, warning_style=None,
    image_quality_score=0.88, image_legible=True,
)

# Scenario E — VALLEY CREST (wine, compliant; bottler 'CA' vs 'California' -> likely)
_SCENARIO_E = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("VALLEY CREST", 0.98),
        "Class & type":         ExtractedField("Sonoma County Chardonnay", 0.96),
        "Alcohol content":      ExtractedField("13.5% Alc./Vol.", 0.95),
        "Net contents":         ExtractedField("750 mL", 0.99),
        "Bottler name/address": ExtractedField("Valley Crest Winery, Sonoma, CA", 0.94),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
    warning_style=_good_style(),
    image_quality_score=0.9, image_legible=True,
)

# Scenario F — IRON ANCHOR (beer, no ABV on label, plain compliant)
_SCENARIO_F = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("IRON ANCHOR", 0.99),
        "Class & type":         ExtractedField("Premium Lager Beer", 0.96),
        # NO 'Alcohol content' field — 27 CFR 7.63 makes ABV optional for plain beer.
        "Net contents":         ExtractedField("12 FL OZ", 0.99),
        "Bottler name/address": ExtractedField("Iron Anchor Brewing Co., Milwaukee, Wisconsin", 0.95),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
    warning_style=_good_style(),
    image_quality_score=0.9, image_legible=True,
)

# Scenario G — BRIGHT WAVE (hard seltzer / flavored malt with ABV — mandatory)
_SCENARIO_G = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("BRIGHT WAVE", 0.98),
        "Class & type":         ExtractedField("Black Cherry Hard Seltzer", 0.96),
        "Alcohol content":      ExtractedField("5% Alc./Vol.", 0.95),
        "Net contents":         ExtractedField("12 FL OZ", 0.99),
        "Bottler name/address": ExtractedField("Bright Wave Beverage Co., Austin, Texas", 0.94),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
    warning_style=_good_style(),
    image_quality_score=0.9, image_legible=True,
)

# Scenario H — GLEN ARDEN (imported scotch, country of origin = Scotland)
_SCENARIO_H = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("GLEN ARDEN", 0.98),
        "Class & type":         ExtractedField("Blended Scotch Whisky", 0.96),
        "Alcohol content":      ExtractedField("40% Alc./Vol. (80 Proof)", 0.95),
        "Net contents":         ExtractedField("750 mL", 0.99),
        "Bottler name/address": ExtractedField("Glen Arden Imports, New York, NY", 0.94),
        "Country of origin":    ExtractedField("PRODUCT OF SCOTLAND", 0.97),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
    warning_style=_good_style(),
    image_quality_score=0.9, image_legible=True,
)

# Scenario I — SUMMIT PEAK (declared SUMMIT RIDGE, label reads SUMMIT PEAK -> brand flag)
_SCENARIO_I = ExtractedLabel(
    fields={
        "Brand name":           ExtractedField("SUMMIT PEAK", 0.98),
        "Class & type":         ExtractedField("Straight Rye Whiskey", 0.96),
        "Alcohol content":      ExtractedField("47% Alc./Vol. (94 Proof)", 0.95),
        "Net contents":         ExtractedField("750 mL", 0.99),
        "Bottler name/address": ExtractedField("Summit Spirits, Denver, Colorado", 0.94),
    },
    warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
    warning_style=_good_style(),
    image_quality_score=0.9, image_legible=True,
)


def _pick(brand_name: str) -> ExtractedLabel:
    b = (brand_name or "").upper()
    if "STONE" in b:        return _SCENARIO_B
    if "NORTHWIND" in b:    return _SCENARIO_C
    if "CEDAR" in b:        return _SCENARIO_D
    if "VALLEY CREST" in b: return _SCENARIO_E
    if "IRON ANCHOR" in b:  return _SCENARIO_F
    if "BRIGHT WAVE" in b:  return _SCENARIO_G
    if "GLEN ARDEN" in b:   return _SCENARIO_H
    if "SUMMIT" in b:       return _SCENARIO_I
    return _SCENARIO_A


class MockExtractor(LabelExtractor):
    """Returns deterministic observations matching the synthetic demo labels.

    The application's brand name selects which scenario is returned. The mock
    accepts (and ignores) image bytes so curl smoke-testing works with any file.
    """

    def __init__(self, brand_hint: str = "") -> None:
        self._brand_hint = brand_hint

    async def extract(self, image_bytes: bytes, beverage_type: BeverageType) -> ExtractedLabel:
        return _pick(self._brand_hint)
