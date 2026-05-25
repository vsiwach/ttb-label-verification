"""Extract a plausible bottler name+address from a label's OCR text.

The COLA Cloud free sample CSV has `bottler_name_address` empty on ~95% of
rows. Real TTB applications carry it, but we don't have access to the full
filing data. This module synthesizes a reasonable bottler value by parsing
the label's existing OCR text (which DOES contain "BOTTLED BY...",
"IMPORTED BY...", etc. since that's printed on the label).

Used by samples.py to populate the picker / verify pipeline with non-empty
declared bottlers, so the engine can actually do a meaningful comparison.

LIMITATION: This is SYNTHESIZED application data derived from the label
itself, not the actual TTB filing. Documented in DESIGN.md §10 / README.
For production, the bottler comes from the real COLA application.
"""

from __future__ import annotations

import re

# Patterns ordered from most-specific to least-specific. Each captures the
# bottler line up to a common boundary marker (next semantic block on the
# label: GOVERNMENT WARNING, CONTAINS, ALC/VOL, net contents, etc.).
_BOUNDARY = (
    r"(?:\s+(?:GOVERNMENT|WARNING|CONTAINS|INGREDIENTS|ALCOHOL|ALC\.?\s*BY|"
    r"ALC\.?\s*/?\s*VOL|NET\s+(?:CONTENTS|WT)|PRODUCT\s+OF|DRINK\s+RESPONSIBLY|"
    r"AGED|PROOF|\d+\s*%|\d+\s*ML|\d+\s*FL\s*OZ|\d+\s*PINT|"
    r"DISTILLED|BREWED|FERMENTED|CRAFTED|PRODUCED\s+(?:IN|AT)|"
    r"VINTAGED|HARVEST|ESTATE|REG\.?\s*PA|UPC|CA\s+CRV|TA\s+\d+C|"
    # Government Warning text fragments that occasionally splice into
    # bottler lines via bad OCR ordering.
    r"a\s+car|operate\s+machinery|machinery\s*,|may\s+cause|"
    r"health\s+problems|risk\s+of\s+birth|drink\s+alcoholic|"
    r"during\s+pregnancy|surgeon\s+general|drive\s+a\s+car|"
    r"impairs\s+your|your\s+ability|"
    r"\d{8,}|www\.|http)|\.$|\.\s+\w)"
)

PATTERNS = [
    rf"PRODUCED\s+AND\s+BOTTLED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"DISTILLED\s+AND\s+BOTTLED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"DISTILLED,?\s+BLENDED,?\s+AND\s+BOTTLED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"BREWED\s+AND\s+BOTTLED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"BREWED\s+AND\s+CANNED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"AGED\s+AND\s+BOTTLED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"BOTTLED\s+AT\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"BOTTLED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"IMPORTED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"PRODUCED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"DISTILLED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"BREWED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
    rf"CANNED\s+BY\s*[:\.]?\s*([^.]+?){_BOUNDARY}",
]

# Trailing junk: deposit codes, lot numbers, single-letter remnants.
_TAIL_JUNK = re.compile(
    r"\s+(?:CA\s+CRV|TA\s+\d+C|REG\.?\s*PA|"
    r"\d{4,}|[A-Z]{1,2}\s*-?\s*[A-Z]{1,2}\s*\d+C|"
    r"www\.\S+|https?://\S+|MOMENTUM\s+\w+)\s*$",
    re.IGNORECASE,
)


def extract_bottler(ocr_text: str) -> str:
    """Return a plausible bottler-line string parsed from `ocr_text`,
    or "" if no recognizable bottler signal is found.

    The output is intended to match what the COLA application would have
    declared, not a perfect transcription of the label. It's used to
    pre-populate `bottlerNameAddress` when the CSV row has it empty.
    """
    if not ocr_text:
        return ""
    for pat in PATTERNS:
        m = re.search(pat, ocr_text, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        bottler = m.group(1).strip().rstrip(",").strip()
        # Normalize whitespace + drop trailing junk
        bottler = re.sub(r"\s+", " ", bottler)
        bottler = _TAIL_JUNK.sub("", bottler).strip().rstrip(",").strip()
        # Drop leading punctuation/colon
        bottler = re.sub(r"^[:\s\.]+", "", bottler)
        # Length sanity
        if 5 < len(bottler) < 120:
            return bottler
    return ""
