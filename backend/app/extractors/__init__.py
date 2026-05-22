"""Pluggable inference adapters.

The model reads and reports; the rules engine decides. Adapters live behind
the LabelExtractor interface so we can swap mock <-> cloud <-> onprem with
zero changes to the rules engine or endpoints.
"""

from .base import (
    ExtractedField,
    ExtractedLabel,
    InferenceError,
    LabelExtractor,
    WarningStyle,
)
from .factory import get_extractor

__all__ = [
    "ExtractedField",
    "ExtractedLabel",
    "InferenceError",
    "LabelExtractor",
    "WarningStyle",
    "get_extractor",
]
