"""Mandatory ApplicationData fields per beverage type.

Mirrors src/api/ttbRules.ts.requiredFields(): brand, class/type, net contents,
bottler name/address are universal; alcohol content is required for
spirits/wine and for beer/malt only when added nonbeverage flavors are present;
country of origin is required for imports.

The label-side field name (used by the UI) differs from the
ApplicationData key; this module maps between them.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import ApplicationData, BeverageType


@dataclass(frozen=True)
class FieldSpec:
    application_key: str   # key on ApplicationData
    label_name: str        # human-readable name used on the wire (VerificationField.fieldName)


# Order matters — this is the order the frontend renders.
ALL_FIELDS: list[FieldSpec] = [
    FieldSpec("brandName",          "Brand name"),
    FieldSpec("classType",          "Class & type"),
    FieldSpec("alcoholContent",     "Alcohol content"),
    FieldSpec("netContents",        "Net contents"),
    FieldSpec("bottlerNameAddress", "Bottler name/address"),
    FieldSpec("countryOfOrigin",    "Country of origin"),
]


def required_field_specs(
    beverage_type: BeverageType,
    *,
    imported: bool = False,
    contains_added_flavors: bool = False,
) -> list[FieldSpec]:
    """Return the FieldSpec list for fields that MUST appear on the label."""
    out: list[FieldSpec] = []
    for spec in ALL_FIELDS:
        key = spec.application_key
        if key in ("brandName", "classType", "netContents", "bottlerNameAddress"):
            out.append(spec)
        elif key == "alcoholContent":
            if beverage_type in ("spirits", "wine"):
                out.append(spec)
            elif beverage_type in ("beer", "malt") and contains_added_flavors:
                out.append(spec)
        elif key == "countryOfOrigin":
            if imported:
                out.append(spec)
    return out


def applies_to(app: ApplicationData, contains_added_flavors: bool = False) -> list[FieldSpec]:
    """Convenience: derive the imported flag from countryOfOrigin presence."""
    imported = bool(app.countryOfOrigin)
    return required_field_specs(
        app.beverageType, imported=imported, contains_added_flavors=contains_added_flavors,
    )


def declared_value(app: ApplicationData, spec: FieldSpec) -> str:
    return getattr(app, spec.application_key) or ""
