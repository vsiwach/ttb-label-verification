"""Post-2020 27 CFR citations. Beer and malt are both Part 7."""

from ..models import BeverageType

# Mandatory labeling info, per beverage type.
_FIELD_CITES: dict[BeverageType, str] = {
    "spirits": "27 CFR 5.63",
    "wine":    "27 CFR 4.32",
    "beer":    "27 CFR 7.63",
    "malt":    "27 CFR 7.63",
}

WARNING_CITE_VERBATIM = "27 CFR 16.21"
WARNING_CITE_FORMAT = "27 CFR 16.22"


def citation_for_field(beverage_type: BeverageType, _field_name: str = "") -> str:
    """Return the umbrella mandatory-info citation for the beverage type.

    Part 5/4/7 sections sub-divide further, but the umbrella section is the
    correct, defensible citation for any mandatory field. We keep this single
    so a future regulatory change is a one-line edit.
    """
    return _FIELD_CITES[beverage_type]


def citation_for_warning(check_kind: str) -> str:
    """16.21 for verbatim wording; 16.22 for format checks."""
    return WARNING_CITE_VERBATIM if check_kind == "wording" else WARNING_CITE_FORMAT
