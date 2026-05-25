"""End-to-end integration tests via FastAPI's TestClient.

Runs in mock mode (no API keys needed). Exercises /health, /api/verify for
all three scenarios, /api/verify-batch with mixed groups, the /crops/{id}
route, and error handling for bad inputs.
"""

import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _png_bytes(w: int = 800, h: int = 600, color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=color).save(buf, format="PNG")
    return buf.getvalue()


# ── health ───────────────────────────────────────────────────────────────────
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["inferenceMode"] in ("mock", "cloud", "onprem")


# ── single-label verify (3 scenarios) ────────────────────────────────────────
_OLD_TOM = {
    "brandName": "OLD TOM DISTILLERY",
    "classType": "Kentucky Straight Bourbon Whiskey",
    "alcoholContent": "45% Alc./Vol. (90 Proof)",
    "netContents": "750 mL",
    "bottlerNameAddress": "Old Tom Distillery, Frankfort, Kentucky",
    "beverageType": "spirits",
}

_STONES = {
    "brandName": "STONE'S THROW",
    "classType": "California Red Table Wine",
    "alcoholContent": "13.5% Alc./Vol.",
    "netContents": "750 mL",
    "bottlerNameAddress": "Stone's Throw Cellars, Sonoma, California",
    "beverageType": "wine",
}

_NORTHWIND = {
    "brandName": "NORTHWIND BREWING",
    "classType": "India Pale Ale",
    "alcoholContent": "6.8% Alc./Vol.",
    "netContents": "12 FL OZ",
    "bottlerNameAddress": "Northwind Brewing Co., Bend, Oregon",
    "beverageType": "beer",
}


def _post_verify(client, application):
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    data = {"applicationData": json.dumps(application)}
    return client.post("/api/verify", files=files, data=data)


def test_verify_scenario_A_old_tom(client):
    r = _post_verify(client, _OLD_TOM)
    assert r.status_code == 200
    body = r.json()
    statuses = [f["status"] for f in body["fields"]]
    # OLD TOM is the all-match scenario (5 mandatory fields for spirits).
    assert statuses.count("match") == 5
    gw = body["governmentWarning"]
    assert gw["verbatimMatch"] is True
    assert gw["casingBoldOk"] is True
    # fontSizeOk is None for inputs without DPI metadata + bbox (this test
    # uses synthetic PNG bytes, no DPI). Computed deterministically when
    # both inputs are present (TTB-scraped JPEGs with DPI).
    assert gw.get("fontSizeOk") is None
    assert gw["deviations"] == []
    assert gw["regulation"] == "27 CFR 16.21/16.22"
    for f in body["fields"]:
        assert f["regulationCite"] == "27 CFR 5.63"


def test_verify_scenario_B_stones_throw(client):
    r = _post_verify(client, _STONES)
    assert r.status_code == 200
    body = r.json()
    by_name = {f["fieldName"]: f for f in body["fields"]}
    # Brand case-only differences are 'match' under the permissive brand rule.
    assert by_name["Brand name"]["status"] == "match"
    # 750 mL vs 700 mL = 6.7% → 'likely' under graduated net-contents tolerance.
    assert by_name["Net contents"]["status"] == "likely"
    assert all(f["regulationCite"] == "27 CFR 4.32" for f in body["fields"])


def test_verify_scenario_C_northwind_warning_violation(client):
    r = _post_verify(client, _NORTHWIND)
    assert r.status_code == 200
    body = r.json()
    gw = body["governmentWarning"]
    assert gw["verbatimMatch"] is False
    assert gw["casingBoldOk"] is False
    # fontSizeOk None on this synthetic image (no DPI, no bbox)
    assert gw.get("fontSizeOk") is None
    kinds = {d["type"] for d in gw["deviations"]}
    assert {"casing", "wording"}.issubset(kinds)
    # fontSize deviation only emitted when the check ACTUALLY runs and fails
    # (DPI + bbox present and below threshold). Not the case for this test.
    assert "fontSize" not in kinds


# ── batch ─────────────────────────────────────────────────────────────────────
def test_verify_batch_groups(client):
    files = [
        ("images", ("a.png", _png_bytes(), "image/png")),
        ("images", ("b.png", _png_bytes(), "image/png")),
        ("images", ("c.png", _png_bytes(), "image/png")),
    ]
    r = client.post("/api/verify-batch", files=files)
    assert r.status_code == 200
    arr = r.json()
    assert len(arr) == 3
    groups = {item["group"] for item in arr}
    # Scenario A is auto-pass; B (net 6.7% delta on a standard fill) is now
    # 'needs-confirm' under the graduated net-contents tolerance; C (warning
    # violation: paraphrased + non-all-caps heading) is 'needs-review'.
    assert groups == {"auto-pass", "needs-confirm", "needs-review"}
    for item in arr:
        assert "id" in item and "fileName" in item and "thumbnailUrl" in item


def test_verify_batch_with_shared_application(client):
    """When applicationData is supplied, every item uses it."""
    files = [
        ("images", ("a.png", _png_bytes(), "image/png")),
        ("images", ("b.png", _png_bytes(), "image/png")),
    ]
    data = {"applicationData": json.dumps(_OLD_TOM)}
    r = client.post("/api/verify-batch", files=files, data=data)
    assert r.status_code == 200
    arr = r.json()
    assert len(arr) == 2
    # All items resolved against OLD TOM -> same group.
    assert len({item["group"] for item in arr}) == 1


# ── errors ────────────────────────────────────────────────────────────────────
def test_verify_bad_application_json_is_400(client):
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    data = {"applicationData": "not json"}
    r = client.post("/api/verify", files=files, data=data)
    assert r.status_code == 400


def test_verify_missing_required_application_field_is_422(client):
    files = {"image": ("label.png", _png_bytes(), "image/png")}
    bad = dict(_OLD_TOM)
    del bad["beverageType"]
    data = {"applicationData": json.dumps(bad)}
    r = client.post("/api/verify", files=files, data=data)
    assert r.status_code == 422


def test_verify_batch_empty_is_400(client):
    r = client.post("/api/verify-batch", files=[])
    # FastAPI returns 422 when a required form field is absent.
    assert r.status_code in (400, 422)


# ── crops route ───────────────────────────────────────────────────────────────
def test_crops_route_404_when_unknown(client):
    r = client.get("/crops/does-not-exist")
    assert r.status_code == 404
