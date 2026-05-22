"""Parse net-contents strings to milliliters and pick the minimum warning type size.

27 CFR 16.22:
  container <= 237 mL  -> warning text >= 1 mm
  237 mL < container <= 3 L  -> warning text >= 2 mm
  container > 3 L  -> warning text >= 3 mm
"""

from __future__ import annotations

import re
from typing import Optional


_UNIT_TO_ML = {
    "ml":      1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l":       1000.0,
    "liter":   1000.0,
    "liters":  1000.0,
    "litre":   1000.0,
    "litres":  1000.0,
    "fl oz":   29.5735,
    "floz":    29.5735,
    "fl. oz.": 29.5735,
    "fl. oz":  29.5735,
    "fl oz.":  29.5735,
    "ounce":   29.5735,
    "ounces":  29.5735,
    "oz":      29.5735,
    "pint":    473.176,
    "pints":   473.176,
    "pt":      473.176,
    "quart":   946.353,
    "quarts":  946.353,
    "qt":      946.353,
    "gallon":  3785.41,
    "gallons": 3785.41,
    "gal":     3785.41,
}


def parse_net_contents_to_ml(s: str) -> Optional[float]:
    """Return container size in mL, or None if not parseable.

    Matches the FIRST leading number+unit pair, so multi-form displays like
    "1 PINT (16 FL OZ)" or "12 L 40.5 FL OZ 2.53 PINT" yield the first value.
    """
    if not s:
        return None
    text = s.strip().lower()
    # Find the first leading number+unit. The unit is one or more letter tokens,
    # optionally separated by whitespace or dots ('fl oz', 'fl. oz.', 'fluid ounces').
    # We stop at parens, digits, or end-of-string.
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([a-z]+(?:[.\s]+[a-z]+)*)", text)
    if not m:
        return None
    qty = float(m.group(1))
    # Strip cosmetic punctuation INSIDE the unit ('fl. oz.' -> 'fl oz').
    unit = m.group(2).replace(".", "").replace(",", "").strip()
    unit = re.sub(r"\s+", " ", unit)
    factor = _UNIT_TO_ML.get(unit)
    if factor is None:
        factor = _UNIT_TO_ML.get(unit.replace(" ", ""))
    if factor is None:
        # Try the first unit token only (e.g. 'fluid ounces' -> 'fluid' won't match,
        # but 'fl' won't either — we keep this best-effort).
        first = unit.split()[0]
        factor = _UNIT_TO_ML.get(first)
    if factor is None:
        return None
    return qty * factor


def required_warning_mm(container_ml: Optional[float]) -> Optional[float]:
    """Minimum warning text height in mm for the container size, per 16.22."""
    if container_ml is None:
        return None
    if container_ml <= 237.0:
        return 1.0
    if container_ml <= 3000.0:
        return 2.0
    return 3.0
