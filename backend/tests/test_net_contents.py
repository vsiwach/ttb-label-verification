"""Container parsing and the 27 CFR 16.22 type-size thresholds."""

import pytest

from app.rules.net_contents import parse_net_contents_to_ml, required_warning_mm


@pytest.mark.parametrize(
    "text,expected_ml",
    [
        ("750 mL", 750.0),
        ("750ml", 750.0),
        ("1 L", 1000.0),
        ("1.5 L", 1500.0),
        ("12 FL OZ", pytest.approx(354.882, rel=1e-3)),
        ("12 FL. OZ.", pytest.approx(354.882, rel=1e-3)),
        ("8 oz", pytest.approx(236.588, rel=1e-3)),
    ],
)
def test_parse_known_units(text, expected_ml):
    assert parse_net_contents_to_ml(text) == expected_ml


def test_parse_unknown_returns_none():
    assert parse_net_contents_to_ml("two seventy") is None
    assert parse_net_contents_to_ml("") is None


def test_required_mm_thresholds():
    """27 CFR 16.22: ≤237 mL → 1 mm; ≤3 L → 2 mm; >3 L → 3 mm."""
    assert required_warning_mm(50) == 1.0
    assert required_warning_mm(237.0) == 1.0
    assert required_warning_mm(237.01) == 2.0
    assert required_warning_mm(750.0) == 2.0
    assert required_warning_mm(3000.0) == 2.0
    assert required_warning_mm(3000.01) == 3.0
    assert required_warning_mm(5000.0) == 3.0


def test_required_mm_unknown():
    assert required_warning_mm(None) is None
