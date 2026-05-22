"""3-state field matching with normalization.

normalize_for_compare() removes OCR noise (whitespace, smart quotes, accents)
and case differences — anything that is a styling difference, not a
substantive one. classify_field() compares declared vs extracted and returns
'match' | 'likely' | 'flag'.

Thresholds are constants so they can be tuned without touching call sites.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from ..models import FieldStatus

# 'likely' if normalized strings are equal OR similarity >= LIKELY_THRESHOLD
# Otherwise 'flag'. The Stone's Throw vs STONE'S THROW case is caught at the
# normalized-equal step (case-folded + apostrophe-normalized -> identical).
LIKELY_SIMILARITY_THRESHOLD = 0.85


# Map curly/typographic punctuation to ASCII so OCR variants don't penalize.
_SMART_QUOTES = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ",  # non-breaking space
}


def _strict_normalize(s: str) -> str:
    """Whitespace + Unicode + smart-quote normalization. PRESERVES case.

    Two strings are 'strictly equal' iff they differ only in OCR noise:
    typographic punctuation, NFC vs NFKD encoding, repeated/extra whitespace.
    """
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = "".join(_SMART_QUOTES.get(ch, ch) for ch in s)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_for_compare(s: str) -> str:
    """Loose normalization: strict + lowercase + trailing punctuation strip.

    Two strings that are 'loosely equal' are equivalent up to case and
    cosmetic punctuation — which is the threshold for a 'likely' match.
    """
    s = _strict_normalize(s).lower()
    s = s.strip(" .,;:")
    return s


def _similarity(a: str, b: str) -> float:
    """0..1 token-set ratio via SequenceMatcher on normalized strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()


@dataclass
class FieldVerdict:
    status: FieldStatus
    normalized_declared: str
    normalized_extracted: str
    similarity: float
    note: str | None = None


def classify_field(declared: str, extracted: str) -> FieldVerdict:
    """Return the 3-state verdict for one field.

    Rule:
      'match'  — normalized strings are exactly equal
      'likely' — substring containment OR similarity >= threshold (case /
                 punctuation / abbreviation differences)
      'flag'   — anything else (substantive difference)
    """
    if extracted is None or extracted == "":
        return FieldVerdict(
            status="flag",
            normalized_declared=normalize_for_compare(declared),
            normalized_extracted="",
            similarity=0.0,
            note="Field not detected on the label.",
        )
    # Strict-equal: differs only in OCR noise / smart quotes / whitespace.
    if _strict_normalize(declared) == _strict_normalize(extracted):
        nd = normalize_for_compare(declared)
        return FieldVerdict(status="match", normalized_declared=nd, normalized_extracted=nd, similarity=1.0)

    nd = normalize_for_compare(declared)
    ne = normalize_for_compare(extracted)
    if nd == ne:
        # Loose-equal but not strict-equal -> case or cosmetic punctuation differs.
        note = _likely_reason(declared, extracted, nd, ne)
        return FieldVerdict(status="likely", normalized_declared=nd, normalized_extracted=ne, similarity=1.0, note=note)

    sim = _similarity(nd, ne)

    # Substring containment catches the common 'Kentucky' vs 'KY' state-abbrev
    # case as a likely (one side contains the other after normalization).
    contains = nd in ne or ne in nd

    if contains or sim >= LIKELY_SIMILARITY_THRESHOLD:
        note = _likely_reason(declared, extracted, nd, ne)
        return FieldVerdict(status="likely", normalized_declared=nd, normalized_extracted=ne, similarity=sim, note=note)

    return FieldVerdict(
        status="flag",
        normalized_declared=nd,
        normalized_extracted=ne,
        similarity=sim,
        note=f'Substantive difference: declared "{declared}" vs extracted "{extracted}".',
    )


def _likely_reason(declared: str, extracted: str, nd: str, ne: str) -> str:
    """Human-readable explanation for a 'likely'."""
    if declared.strip().lower() == extracted.strip().lower():
        return "Casing differs from the application; otherwise identical."
    if nd == ne:
        return "Differs only in punctuation or accents."
    if nd in ne or ne in nd:
        return "One value is a shortened/abbreviated form of the other (e.g. state abbreviation)."
    return "Close match with minor differences in punctuation or spelling."
