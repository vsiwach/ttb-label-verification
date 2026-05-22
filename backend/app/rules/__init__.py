"""The deterministic 27 CFR rules engine.

This module is the legal core. It is pure Python (no AI, no I/O) so it can be
unit-tested exhaustively and audited.
"""

from .citations import citation_for_field, citation_for_warning
from .engine import verify
from .field_match import classify_field, normalize_for_compare
from .government_warning import analyze_warning
from .net_contents import parse_net_contents_to_ml, required_warning_mm

__all__ = [
    "verify",
    "classify_field",
    "normalize_for_compare",
    "analyze_warning",
    "parse_net_contents_to_ml",
    "required_warning_mm",
    "citation_for_field",
    "citation_for_warning",
]
