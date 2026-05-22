"""Field matching: match / likely / flag with explainable reasons."""

from app.rules.field_match import classify_field, normalize_for_compare


def test_exact_match():
    v = classify_field("OLD TOM DISTILLERY", "OLD TOM DISTILLERY")
    assert v.status == "match"
    assert v.similarity == 1.0


def test_casing_difference_is_likely_stones_throw():
    """The headline case from the PRD: STONE'S THROW vs Stone's Throw -> likely."""
    v = classify_field("STONE'S THROW", "Stone's Throw")
    assert v.status == "likely", f"got {v.status}, sim={v.similarity}"
    assert "casing" in (v.note or "").lower() or "punctuation" in (v.note or "").lower()


def test_smart_apostrophe_difference_is_likely():
    """Curly quote on extracted side should not penalize."""
    v = classify_field("STONE'S THROW", "STONE’S THROW")
    assert v.status == "match"  # normalized identical


def test_state_abbreviation_is_likely():
    v = classify_field("Old Tom Distillery, Frankfort, Kentucky",
                       "Old Tom Distillery, Frankfort, KY")
    assert v.status == "likely"


def test_net_contents_substantive_difference_is_flag():
    """750 mL vs 700 mL is a substantive difference -> flag."""
    v = classify_field("750 mL", "700 mL")
    assert v.status == "flag"


def test_missing_extracted_is_flag():
    v = classify_field("750 mL", "")
    assert v.status == "flag"
    assert "not detected" in (v.note or "").lower()


def test_punctuation_only_is_likely_or_match():
    """'12 FL OZ' vs '12 FL. OZ.' — punctuation-only delta -> match (normalized)."""
    v = classify_field("12 FL OZ", "12 FL. OZ.")
    assert v.status in ("match", "likely")


def test_short_brand_inside_long_unrelated_extracted_is_flag():
    """Containment is only 'likely' when the contained string is most of the
    longer string. A 5-char brand inside a 30-char unrelated extraction is a
    substantive content difference, not a near-match."""
    v = classify_field("Brand", "Brand WRONG-MATCH AND MORE STUFF")
    assert v.status == "flag", f"got {v.status}, sim={v.similarity}"


def test_state_abbreviation_still_likely_in_context():
    """Length-ratio tightening must not kill the state-abbrev case when there's
    enough surrounding address content for the similarity score to clear the
    threshold."""
    v = classify_field(
        "Old Tom Distillery, Frankfort, Kentucky",
        "Old Tom Distillery, Frankfort, KY",
    )
    assert v.status == "likely"


def test_normalize_idempotent():
    assert normalize_for_compare("  Hello  WORLD  ") == "hello world"
    assert normalize_for_compare(None) == ""  # type: ignore[arg-type]
