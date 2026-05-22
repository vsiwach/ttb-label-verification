"""End-to-end rules-engine tests for the three demo scenarios and the
beverage-type ABV rule."""

from app.extractors.base import ExtractedField, ExtractedLabel, WarningStyle
from app.constants import VERBATIM_GOVERNMENT_WARNING
from app.models import ApplicationData, group_for
from app.rules.engine import verify


def _good_style() -> WarningStyle:
    return WarningStyle(
        casing_all_caps=True, heading_bold=True, body_bold=False,
        approx_font_mm=2.2, contrast_ok=True, separate_and_apart=True,
    )


# ── Scenario A — all matches → auto-pass ─────────────────────────────────────
def test_scenario_A_all_match_autopass():
    app = ApplicationData(
        brandName="OLD TOM DISTILLERY",
        classType="Kentucky Straight Bourbon Whiskey",
        alcoholContent="45% Alc./Vol. (90 Proof)",
        netContents="750 mL",
        bottlerNameAddress="Old Tom Distillery, Frankfort, Kentucky",
        beverageType="spirits",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("OLD TOM DISTILLERY", 0.99),
            "Class & type":        ExtractedField("Kentucky Straight Bourbon Whiskey", 0.97),
            "Alcohol content":     ExtractedField("45% Alc./Vol. (90 Proof)", 0.96),
            "Net contents":        ExtractedField("750 mL", 0.99),
            # Note: extracted side abbreviates state -> 'likely', not 'flag'.
            # We use the exact form so this scenario is all-match.
            "Bottler name/address": ExtractedField("Old Tom Distillery, Frankfort, Kentucky", 0.95),
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING,
        warning_present=True,
        warning_style=_good_style(),
        image_quality_score=0.92, image_legible=True,
    )
    r = verify(extracted, app)
    statuses = [f.status for f in r.fields]
    assert statuses == ["match"] * 5
    assert r.governmentWarning.verbatimMatch is True
    assert r.governmentWarning.casingBoldOk is True
    assert group_for(r) == "auto-pass"
    # Citations attached to every field
    assert all(f.regulationCite == "27 CFR 5.63" for f in r.fields)


# ── Scenario B — STONE'S THROW likely brand + flag net contents → needs-review ──
def test_scenario_B_stones_throw_likely_and_flag():
    app = ApplicationData(
        brandName="STONE'S THROW",
        classType="California Red Table Wine",
        alcoholContent="13.5% Alc./Vol.",
        netContents="750 mL",
        bottlerNameAddress="Stone's Throw Cellars, Sonoma, California",
        beverageType="wine",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("Stone's Throw", 0.88),     # casing differs
            "Class & type":        ExtractedField("California Red Table Wine", 0.96),
            "Alcohol content":     ExtractedField("13.5% Alc./Vol.", 0.95),
            "Net contents":        ExtractedField("700 mL", 0.97),            # WRONG
            "Bottler name/address": ExtractedField("Stone's Throw Cellars, Sonoma, CA", 0.94),
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING,
        warning_present=True,
        warning_style=_good_style(),
        image_quality_score=0.86, image_legible=True,
    )
    r = verify(extracted, app)
    by_name = {f.fieldName: f for f in r.fields}
    assert by_name["Brand name"].status == "likely"
    assert by_name["Class & type"].status == "match"
    assert by_name["Net contents"].status == "flag"
    assert by_name["Bottler name/address"].status == "likely"  # state abbrev
    assert all(f.regulationCite == "27 CFR 4.32" for f in r.fields)
    assert group_for(r) == "needs-review"  # because of the flag


# ── Scenario C — beer, three Government Warning deviations → needs-review ────
def test_scenario_C_warning_violation():
    app = ApplicationData(
        brandName="NORTHWIND BREWING",
        classType="India Pale Ale",
        alcoholContent="6.8% Alc./Vol.",
        netContents="12 FL OZ",
        bottlerNameAddress="Northwind Brewing Co., Bend, Oregon",
        beverageType="beer",
    )
    bad_warning = (
        "Government Warning: (1) According to the Surgeon General, women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Drinking alcoholic beverages impairs your ability to drive a car or operate "
        "machinery and may cause health problems."
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("NORTHWIND BREWING", 0.98),
            "Class & type":        ExtractedField("India Pale Ale", 0.95),
            "Alcohol content":     ExtractedField("6.8% Alc./Vol.", 0.93),
            "Net contents":        ExtractedField("12 FL. OZ.", 0.91),
            "Bottler name/address": ExtractedField("Northwind Brewing Co., Bend, OR", 0.93),
        },
        warning_text=bad_warning,
        warning_present=True,
        warning_style=WarningStyle(
            casing_all_caps=False, heading_bold=False, body_bold=False,
            approx_font_mm=0.8, contrast_ok=True, separate_and_apart=True,
        ),
        image_quality_score=0.79, image_legible=True,
    )
    r = verify(extracted, app)
    assert r.governmentWarning.verbatimMatch is False
    assert r.governmentWarning.casingBoldOk is False
    assert r.governmentWarning.fontSizeOk is False
    kinds = {d.type for d in r.governmentWarning.deviations}
    assert {"casing", "wording", "fontSize"}.issubset(kinds)
    assert group_for(r) == "needs-review"


# ── Mandatory-field rules per beverage type ──────────────────────────────────
def test_beer_without_abv_not_flagged():
    """27 CFR 7.63: ABV is OPTIONAL for malt beverages without added flavors."""
    app = ApplicationData(
        brandName="NORTHWIND BREWING", classType="India Pale Ale",
        alcoholContent="6.8% Alc./Vol.",  # in the application, even if absent on label
        netContents="12 FL OZ",
        bottlerNameAddress="Northwind Brewing Co., Bend, Oregon",
        beverageType="beer",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("NORTHWIND BREWING", 0.98),
            "Class & type":        ExtractedField("India Pale Ale", 0.95),
            "Net contents":        ExtractedField("12 FL OZ", 0.95),
            "Bottler name/address": ExtractedField("Northwind Brewing Co., Bend, Oregon", 0.95),
            # NO 'Alcohol content' — beer/malt may omit it.
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING,
        warning_present=True,
        warning_style=_good_style(),
    )
    r = verify(extracted, app, contains_added_flavors=False)
    names = [f.fieldName for f in r.fields]
    assert "Alcohol content" not in names  # not even checked for plain beer
    assert all(f.status in ("match", "likely") for f in r.fields)


def test_spirits_without_abv_extraction_is_likely_not_flag():
    """27 CFR 5.63 requires ABV on spirits labels, but our system reasons over
    a SINGLE label panel at a time and ABV may live on a different panel. So a
    missing extraction is surfaced as 'likely' (needs-confirm), not 'flag' —
    the agent confirms whether ABV is actually absent from the full label set."""
    app = ApplicationData(
        brandName="OLD TOM DISTILLERY", classType="Kentucky Straight Bourbon Whiskey",
        alcoholContent="45% Alc./Vol.", netContents="750 mL",
        bottlerNameAddress="Old Tom Distillery, Frankfort, Kentucky",
        beverageType="spirits",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("OLD TOM DISTILLERY", 0.99),
            "Class & type":        ExtractedField("Kentucky Straight Bourbon Whiskey", 0.97),
            "Net contents":        ExtractedField("750 mL", 0.99),
            "Bottler name/address": ExtractedField("Old Tom Distillery, Frankfort, Kentucky", 0.95),
            # ABV missing on this panel.
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
        warning_style=_good_style(),
    )
    r = verify(extracted, app)
    abv = next((f for f in r.fields if f.fieldName == "Alcohol content"), None)
    assert abv is not None
    assert abv.status == "likely"
    assert abv.regulationCite == "27 CFR 5.63"
    assert "may be on another panel" in (abv.note or "").lower()


def test_seltzer_class_type_auto_detects_added_flavors():
    """A hard seltzer's class type is enough to flip ABV to mandatory — the
    caller should not have to remember to pass contains_added_flavors=True."""
    app = ApplicationData(
        brandName="BRIGHT WAVE", classType="Black Cherry Hard Seltzer",
        alcoholContent="5% Alc./Vol.", netContents="12 FL OZ",
        bottlerNameAddress="Bright Wave Beverage Co., Austin, Texas",
        beverageType="malt",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("BRIGHT WAVE", 0.99),
            "Class & type":        ExtractedField("Black Cherry Hard Seltzer", 0.96),
            "Alcohol content":     ExtractedField("5% Alc./Vol.", 0.95),
            "Net contents":        ExtractedField("12 FL OZ", 0.99),
            "Bottler name/address": ExtractedField("Bright Wave Beverage Co., Austin, Texas", 0.94),
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
        warning_style=_good_style(),
    )
    # No explicit contains_added_flavors — should be inferred from class type.
    r = verify(extracted, app)
    abv = next((f for f in r.fields if f.fieldName == "Alcohol content"), None)
    assert abv is not None and abv.status == "match"


def test_malt_with_added_flavors_requires_abv():
    app = ApplicationData(
        brandName="FLAVORTOWN MALT", classType="Flavored Malt Beverage",
        alcoholContent="5.0% Alc./Vol.", netContents="12 FL OZ",
        bottlerNameAddress="Flavortown LLC, Anywhere, USA",
        beverageType="malt",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("FLAVORTOWN MALT", 0.99),
            "Class & type":        ExtractedField("Flavored Malt Beverage", 0.95),
            "Net contents":        ExtractedField("12 FL OZ", 0.95),
            "Bottler name/address": ExtractedField("Flavortown LLC, Anywhere, USA", 0.95),
            # ABV missing on the label.
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
        warning_style=_good_style(),
    )
    r = verify(extracted, app, contains_added_flavors=True)
    abv = next((f for f in r.fields if f.fieldName == "Alcohol content"), None)
    # Same multi-image rationale as the spirits-no-ABV test: missing extraction
    # surfaces as 'likely' (needs-confirm), not 'flag'.
    assert abv is not None and abv.status == "likely"


def test_umbrella_class_code_matches_specific_label_designation():
    """COLA Registry class/type codes are taxonomy umbrellas ('beer', 'ale',
    'table red wine'). Labels print the specific designation. The engine should
    treat any specific designation under a known umbrella as a match."""
    app = ApplicationData(
        brandName="NORTHWIND BREWING", classType="beer",  # umbrella code
        alcoholContent="6.8% Alc./Vol.", netContents="12 FL OZ",
        bottlerNameAddress="Northwind Brewing Co., Bend, Oregon",
        beverageType="beer",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("NORTHWIND BREWING", 0.99),
            "Class & type":        ExtractedField("CZECH-STYLE PILSNER", 0.96),
            "Alcohol content":     ExtractedField("6.8% Alc./Vol.", 0.95),
            "Net contents":        ExtractedField("12 FL OZ", 0.99),
            "Bottler name/address": ExtractedField("Northwind Brewing Co., Bend, Oregon", 0.94),
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
        warning_style=_good_style(),
    )
    r = verify(extracted, app)
    cls = next(f for f in r.fields if f.fieldName == "Class & type")
    assert cls.status == "match"
    assert "umbrella" in (cls.note or "").lower()


def test_imported_country_of_origin_with_product_of_prefix_is_match():
    """Real labels print 'PRODUCT OF SCOTLAND'; the COLA form says 'Scotland'.
    The engine should strip the prefix and call it a match."""
    app = ApplicationData(
        brandName="GLEN ARDEN", classType="Blended Scotch Whisky",
        alcoholContent="40% Alc./Vol.", netContents="750 mL",
        bottlerNameAddress="Glen Arden Imports, New York, NY",
        countryOfOrigin="Scotland", beverageType="spirits",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("GLEN ARDEN", 0.99),
            "Class & type":        ExtractedField("Blended Scotch Whisky", 0.97),
            "Alcohol content":     ExtractedField("40% Alc./Vol.", 0.96),
            "Net contents":        ExtractedField("750 mL", 0.99),
            "Bottler name/address": ExtractedField("Glen Arden Imports, New York, NY", 0.95),
            "Country of origin":   ExtractedField("PRODUCT OF SCOTLAND", 0.97),
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
        warning_style=_good_style(),
    )
    r = verify(extracted, app)
    coo = next((f for f in r.fields if f.fieldName == "Country of origin"), None)
    assert coo is not None and coo.status == "match"
    assert group_for(r) == "auto-pass"


def test_imported_product_requires_country_of_origin():
    app = ApplicationData(
        brandName="CHATEAU FOO", classType="French Red Wine",
        alcoholContent="13% Alc./Vol.", netContents="750 mL",
        bottlerNameAddress="Chateau Foo, Bordeaux", countryOfOrigin="France",
        beverageType="wine",
    )
    extracted = ExtractedLabel(
        fields={
            "Brand name":          ExtractedField("CHATEAU FOO", 0.99),
            "Class & type":        ExtractedField("French Red Wine", 0.97),
            "Alcohol content":     ExtractedField("13% Alc./Vol.", 0.96),
            "Net contents":        ExtractedField("750 mL", 0.99),
            "Bottler name/address": ExtractedField("Chateau Foo, Bordeaux", 0.95),
            # 'Country of origin' missing from the label.
        },
        warning_text=VERBATIM_GOVERNMENT_WARNING, warning_present=True,
        warning_style=_good_style(),
    )
    r = verify(extracted, app)
    coo = next((f for f in r.fields if f.fieldName == "Country of origin"), None)
    assert coo is not None and coo.status == "likely"  # missing extraction -> likely
