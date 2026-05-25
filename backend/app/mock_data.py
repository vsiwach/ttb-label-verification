"""Saved sample COLA applications used by the batch endpoint when no
shared applicationData is supplied. These pair with the 9 synthetic label
images in test/synthetic/ by filename — so dragging all 9 into /batch
matches each label with its real COLA application.

These are sample fixtures for the prototype, NOT a production queue. In a
production deployment, application data is loaded from the TTB filing
system (COLAs Online); see DESIGN.md §10 future-state notes.
"""

from __future__ import annotations

from .models import ApplicationData


SAVED_APPLICATIONS: list[ApplicationData] = [
    ApplicationData(
        colaNumber="25-001234",
        brandName="OLD TOM DISTILLERY",
        classType="Kentucky Straight Bourbon Whiskey",
        alcoholContent="45% Alc./Vol. (90 Proof)",
        netContents="750 mL",
        bottlerNameAddress="Old Tom Distillery, Frankfort, Kentucky",
        beverageType="spirits",
    ),
    ApplicationData(
        colaNumber="25-002301",
        brandName="STONE'S THROW",
        classType="California Red Table Wine",
        alcoholContent="13.5% Alc./Vol.",
        netContents="750 mL",
        bottlerNameAddress="Stone's Throw Cellars, Sonoma, California",
        beverageType="wine",
    ),
    ApplicationData(
        colaNumber="25-003988",
        brandName="NORTHWIND BREWING",
        classType="India Pale Ale",
        alcoholContent="6.8% Alc./Vol.",
        netContents="12 FL OZ",
        bottlerNameAddress="Northwind Brewing Co., Bend, Oregon",
        beverageType="beer",
    ),
    ApplicationData(
        colaNumber="25-004102",
        brandName="CEDAR & SAGE",
        classType="Distilled Gin",
        alcoholContent="40% Alc./Vol. (80 Proof)",
        netContents="750 mL",
        bottlerNameAddress="Cedar & Sage Spirits, Portland, Oregon",
        beverageType="spirits",
    ),
    ApplicationData(
        colaNumber="25-005517",
        brandName="VALLEY CREST",
        classType="Sonoma County Chardonnay",
        alcoholContent="13.5% Alc./Vol.",
        netContents="750 mL",
        bottlerNameAddress="Valley Crest Winery, Sonoma, California",
        beverageType="wine",
    ),
    ApplicationData(
        colaNumber="25-006023",
        brandName="IRON ANCHOR",
        classType="Premium Lager Beer",
        alcoholContent="",
        netContents="12 FL OZ",
        bottlerNameAddress="Iron Anchor Brewing Co., Milwaukee, Wisconsin",
        beverageType="beer",
    ),
    ApplicationData(
        colaNumber="25-007840",
        brandName="BRIGHT WAVE",
        classType="Black Cherry Hard Seltzer",
        alcoholContent="5% Alc./Vol.",
        netContents="12 FL OZ",
        bottlerNameAddress="Bright Wave Beverage Co., Austin, Texas",
        beverageType="malt",
    ),
    ApplicationData(
        colaNumber="25-008311",
        brandName="GLEN ARDEN",
        classType="Blended Scotch Whisky",
        alcoholContent="40% Alc./Vol. (80 Proof)",
        netContents="750 mL",
        bottlerNameAddress="Glen Arden Imports, New York, NY",
        countryOfOrigin="Scotland",
        beverageType="spirits",
    ),
    ApplicationData(
        colaNumber="25-009766",
        brandName="SUMMIT RIDGE",
        classType="Straight Rye Whiskey",
        alcoholContent="47% Alc./Vol. (94 Proof)",
        netContents="750 mL",
        bottlerNameAddress="Summit Spirits, Denver, Colorado",
        beverageType="spirits",
    ),
]


# Map fixture filename substrings to the matching application above.
# The batch endpoint uses this to pair each uploaded label with its COLA
# when no shared applicationData is provided.
_FILENAME_TO_BRAND: list[tuple[str, str]] = [
    ("old_tom",      "OLD TOM DISTILLERY"),
    ("stones_throw", "STONE'S THROW"),
    ("stone",        "STONE'S THROW"),
    ("northwind",    "NORTHWIND BREWING"),
    ("cedar_sage",   "CEDAR & SAGE"),
    ("cedar",        "CEDAR & SAGE"),
    ("valley_crest", "VALLEY CREST"),
    ("iron_anchor",  "IRON ANCHOR"),
    ("bright_wave",  "BRIGHT WAVE"),
    ("glen_arden",   "GLEN ARDEN"),
    ("summit",       "SUMMIT RIDGE"),
]


def application_for_filename(filename: str, fallback_index: int = 0) -> ApplicationData:
    """Pick the saved application that matches an uploaded label by filename.

    Used by the batch endpoint to pair each image with its COLA when the
    client didn't supply a shared applicationData. Falls back to a stable
    round-robin if no substring matches (so the agent still sees results).
    """
    if not filename:
        return SAVED_APPLICATIONS[fallback_index % len(SAVED_APPLICATIONS)]
    low = filename.lower()
    for needle, brand in _FILENAME_TO_BRAND:
        if needle in low:
            for app in SAVED_APPLICATIONS:
                if app.brandName == brand:
                    return app
    return SAVED_APPLICATIONS[fallback_index % len(SAVED_APPLICATIONS)]
