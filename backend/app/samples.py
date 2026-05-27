"""Sample COLA applications + label images exposed via /api/samples.

The list is built dynamically from two on-disk sources, so adding/removing
labels never requires editing this file:

  1. **Synthetic** (9) — hand-crafted labels with planted violations,
     loaded from `test/synthetic/expected_results.json`. Used for the
     deterministic CI gate. NOT shown in the agent picker — agents want
     real artwork — but they remain addressable by id so the test pack
     and any direct links keep working.

  2. **Real** (67 clean rows) — TTB-approved labels from the COLA Cloud
     free sample (CC0 — colacloud.us), loaded from
     `test/eval/data/cola_sample.csv` + matching `.webp` images. The
     filter drops rows with garbled OCR-spillage in brand/class and
     drops the dataset's own synthetic mutation rows.

The verdict-pill on each sample is the **typical engine output** captured
by `test/eval/real_audit.json` (run via `make audit-reals`). If no audit
file exists, we fall back to the CSV's TTB-disposition `expected_outcome`.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .models import ApplicationData
from .ocr_bottler import extract_bottler


REPO_ROOT     = Path(__file__).resolve().parents[2]
SYNTHETIC_DIR = REPO_ROOT / "test" / "synthetic"
SYNTHETIC_JSON = SYNTHETIC_DIR / "expected_results.json"
REAL_CSV      = REPO_ROOT / "test" / "eval" / "data" / "cola_sample.csv"
REAL_DIR      = REPO_ROOT / "test" / "eval" / "data" / "images"
AUDIT_JSON    = REPO_ROOT / "test" / "eval" / "real_audit.json"
# TTB live tier — labels scraped directly from the TTB Public COLA Registry
# via test/eval/scrape_ttb_registry.py. Field 8 ("Name and Address of
# Applicant") IS populated here, unlike the COLA Cloud sample, and ~51% of
# rows carry DPI metadata in the JPEG header — enabling the deterministic
# 27 CFR 16.22 type-size check.
#
# The full scrape (~20K rows / ~2.5GB of images) lives under ttb_live/ but is
# too large to ship in the Vercel function bundle. A curated subset under
# ttb_live/curated/ (20 labels with DPI ≥ 100, balanced across spirits /
# wine / beer-malt) ships in the demo. Production deploys use the curated
# subset; full-dataset workflows (eval, scraping) point at the full set.
_CURATED_TTB_LIVE_CSV = REPO_ROOT / "test" / "eval" / "data" / "ttb_live" / "curated" / "ttb_live.csv"
_CURATED_TTB_LIVE_DIR = REPO_ROOT / "test" / "eval" / "data" / "ttb_live" / "curated" / "images"
_FULL_TTB_LIVE_CSV    = REPO_ROOT / "test" / "eval" / "data" / "ttb_live" / "ttb_live.csv"
_FULL_TTB_LIVE_DIR    = REPO_ROOT / "test" / "eval" / "data" / "ttb_live" / "images"

# Prefer the curated set when both CSV + image dir exist (production path).
# Fall back to the full scrape only when the curated subset is absent — keeps
# local dev / eval / scraping workflows backwards-compatible.
if _CURATED_TTB_LIVE_CSV.exists() and _CURATED_TTB_LIVE_DIR.exists():
    TTB_LIVE_CSV = _CURATED_TTB_LIVE_CSV
    TTB_LIVE_DIR = _CURATED_TTB_LIVE_DIR
else:
    TTB_LIVE_CSV = _FULL_TTB_LIVE_CSV
    TTB_LIVE_DIR = _FULL_TTB_LIVE_DIR

TTB_LIVE_AUDIT_JSON = REPO_ROOT / "test" / "eval" / "ttb_live_audit.json"

SampleKind = Literal["synthetic", "real", "ttb-live"]


@dataclass(frozen=True)
class Sample:
    id: str
    kind: SampleKind
    image_path: Path
    application_data: ApplicationData
    expected_outcome: str  # 'auto-pass' | 'needs-confirm' | 'needs-review'
    note: str = ""


# ── Synthetic samples ───────────────────────────────────────────────────────

def _load_synthetic() -> list[Sample]:
    if not SYNTHETIC_JSON.exists():
        return []
    payload = json.loads(SYNTHETIC_JSON.read_text())
    out: list[Sample] = []
    for case in payload.get("cases", []):
        img = SYNTHETIC_DIR / case["image"]
        if not img.exists():
            continue
        # Build a stable id from the image filename
        sid = "syn-" + re.sub(r"\.png$", "", case["image"]).replace("_", "-")
        ad_raw = case["applicationData"]
        try:
            app_data = ApplicationData.model_validate(ad_raw)
        except Exception:
            continue
        out.append(Sample(
            id=sid,
            kind="synthetic",
            image_path=img,
            application_data=app_data,
            expected_outcome=case["expected"]["group"],
            note=case.get("notes", ""),
        ))
    return out


# ── Real samples ────────────────────────────────────────────────────────────

def _clean_real_row(r: dict) -> bool:
    """Filter to rows whose application metadata is well-formed AND whose
    backing image actually exists on disk.

    Requires the four user-fillable form fields (brand, class, ABV, net)
    to be non-empty on the CSV side — incomplete rows would land in the
    picker with blanks in the ApplicationData panel, which the agent
    flagged as confusing. Bottler is handled in _row_to_application_data
    via OCR backfill (the CSV has it empty on every row).
    """
    bad = lambda s: not s or len(s) > 50 or any(c in s for c in "(/.")
    if bad(r["brand_name"]) or bad(r["class_type"]):
        return False
    if r.get("mutation"):
        return False
    if not (r.get("alcohol_content") or "").strip():
        return False
    if not (r.get("net_contents") or "").strip():
        return False
    return (REAL_DIR / r["image_filename"]).exists()


def _row_to_application_data(r: dict) -> ApplicationData | None:
    try:
        # The COLA Cloud CSV has bottler_name_address empty on every row,
        # so we synthesize it from the label's pre-baked OCR text. The
        # original author left it empty because OCR-derived bottlers
        # don't byte-match the engine's vision-language extraction —
        # that decision was revisited because the demo picker needs
        # every required form field populated. The trade-off: the
        # engine may flag some bottlers as likely-match (not exact),
        # which is acceptable for demo purposes and exercises the HITL
        # one-click-confirm path.
        bottler = (r.get("bottler_name_address") or "").strip()
        if not bottler:
            bottler = extract_bottler(r.get("image_ocr_text") or "")
        if not bottler:
            return None  # Drop rows we can't fill bottler for
        return ApplicationData(
            colaNumber=r["ttb_id"],
            brandName=r["brand_name"],
            productName=r.get("product_name") or None,
            classType=r["class_type"],
            alcoholContent=r.get("alcohol_content") or "",
            netContents=r.get("net_contents") or "",
            bottlerNameAddress=bottler,
            countryOfOrigin=(r.get("origin") or "").title() or None,
            beverageType=r["beverage_type"],
        )
    except Exception:
        return None


def _load_audit_pills() -> dict[str, str]:
    """Map ttb_id -> typical engine verdict from the latest audit run.
    Empty dict if no audit file exists."""
    if not AUDIT_JSON.exists():
        return {}
    try:
        data = json.loads(AUDIT_JSON.read_text())
        return {
            r["ttb_id"]: r["engine_verdict"]
            for r in data.get("results", [])
            if r.get("engine_verdict") and r["engine_verdict"] != "ERROR"
        }
    except Exception:
        return {}


def _load_real() -> list[Sample]:
    if not REAL_CSV.exists():
        return []
    audit = _load_audit_pills()
    with open(REAL_CSV) as f:
        rows = [r for r in csv.DictReader(f) if _clean_real_row(r)]
    out: list[Sample] = []
    for r in rows:
        ad = _row_to_application_data(r)
        if ad is None:
            continue
        # Prefer the audit's actual engine verdict over the TTB disposition
        # for the picker pill, since that's what the user will actually
        # see on the result page. Fall back to TTB disposition.
        pill = audit.get(r["ttb_id"]) or r.get("expected_outcome") or "auto-pass"
        out.append(Sample(
            id=f"real-{r['ttb_id']}",
            kind="real",
            image_path=REAL_DIR / r["image_filename"],
            application_data=ad,
            expected_outcome=pill,
            note=f"{r.get('domestic_or_imported', '')} {r['beverage_type']}".strip(),
        ))
    return out


# ── TTB-live tier (scraped directly from the Public COLA Registry) ──────────

_BEVERAGE_MAP = {
    "beer": "beer", "malt beverage": "malt", "malt beverages": "malt",
    "wine": "wine", "table wine": "wine", "sparkling wine": "wine",
    "distilled spirits": "spirits", "spirits": "spirits", "whisky": "spirits",
    "whiskey": "spirits", "vodka": "spirits", "gin": "spirits",
    "rum": "spirits", "tequila": "spirits", "brandy": "spirits",
    "liqueur": "spirits", "cordial": "spirits",
}


def _guess_beverage(row: dict) -> str:
    """Map the form's CLASS/TYPE DESCRIPTION to our 4-state beverage_type."""
    text = (row.get("class_type_description") or row.get("class_type_code") or "").lower()
    if any(t in text for t in ("malt", "beer", "ale", "lager", "stout", "porter", "ipa", "pilsner")):
        return "malt" if "malt" in text else "beer"
    if any(t in text for t in ("wine", "champagne", "port", "sherry", "vermouth", "sake")):
        return "wine"
    if any(t in text for t in ("whisky", "whiskey", "vodka", "gin", "rum", "tequila", "brandy",
                                "liqueur", "cordial", "spirits", "mezcal", "agave", "cognac",
                                "schnapps", "shochu")):
        return "spirits"
    # Default to spirits — most ambiguous entries on this dataset are spirits
    return "spirits"


def _load_ttb_audit_pills() -> dict[str, str]:
    if not TTB_LIVE_AUDIT_JSON.exists():
        return {}
    try:
        data = json.loads(TTB_LIVE_AUDIT_JSON.read_text())
        return {
            r["ttb_id"]: r["engine_verdict"]
            for r in data.get("results", [])
            if r.get("engine_verdict") and r["engine_verdict"] != "ERROR"
        }
    except Exception:
        return {}


def _load_ttb_live() -> list[Sample]:
    if not TTB_LIVE_CSV.exists():
        return []
    audit = _load_ttb_audit_pills()
    with open(TTB_LIVE_CSV) as f:
        rows = list(csv.DictReader(f))
    out: list[Sample] = []
    for r in rows:
        # Skip rows without a label image (scrape didn't recover it)
        img_path = TTB_LIVE_DIR / (r.get("image_filename") or "")
        if not r.get("image_filename") or not img_path.exists():
            continue
        bev = _guess_beverage(r)
        try:
            ad = ApplicationData(
                colaNumber=r["ttb_id"],
                brandName=r.get("brand_name") or "",
                productName=r.get("fanciful_name") or None,
                classType=r.get("class_type_description") or r.get("class_type_code") or "",
                # TTB form doesn't carry ABV / net contents — they're on the
                # label only. Engine handles empty declared values as
                # "label content shown for agent review."
                alcoholContent="",
                netContents="",
                bottlerNameAddress=r.get("name_address_applicant") or "",
                # Origin code is a country name like "JAPAN" or
                # "CALIFORNIA". Treat non-US states as domestic (no COO).
                countryOfOrigin=(
                    (r.get("origin_code") or "").title()
                    if (r.get("origin_code") and r["origin_code"].upper() not in (
                        "", "DOMESTIC", "ALABAMA", "ALASKA", "ARIZONA",
                        "ARKANSAS", "CALIFORNIA", "COLORADO", "CONNECTICUT",
                        "DELAWARE", "FLORIDA", "GEORGIA", "HAWAII", "IDAHO",
                        "ILLINOIS", "INDIANA", "IOWA", "KANSAS", "KENTUCKY",
                        "LOUISIANA", "MAINE", "MARYLAND", "MASSACHUSETTS",
                        "MICHIGAN", "MINNESOTA", "MISSISSIPPI", "MISSOURI",
                        "MONTANA", "NEBRASKA", "NEVADA", "NEW HAMPSHIRE",
                        "NEW JERSEY", "NEW MEXICO", "NEW YORK",
                        "NORTH CAROLINA", "NORTH DAKOTA", "OHIO", "OKLAHOMA",
                        "OREGON", "PENNSYLVANIA", "PUERTO RICO",
                        "RHODE ISLAND", "SOUTH CAROLINA", "SOUTH DAKOTA",
                        "TENNESSEE", "TEXAS", "UTAH", "VERMONT", "VIRGINIA",
                        "WASHINGTON", "WEST VIRGINIA", "WISCONSIN", "WYOMING",
                    )) else None
                ),
                beverageType=bev,
            )
        except Exception:
            continue
        pill = audit.get(r["ttb_id"]) or "auto-pass"
        out.append(Sample(
            id=f"ttb-{r['ttb_id']}",
            kind="ttb-live",
            image_path=img_path,
            application_data=ad,
            expected_outcome=pill,
            note=(
                f"Scraped from TTB Public Registry on {r.get('scraped_at', '?')[:10]}. "
                f"Status: {r.get('status', '?')}."
            ),
        ))
    return out


# ── Module-level caches (rebuilt on import; cheap CSV/JSON reads) ───────────

_SYNTHETIC: list[Sample] = _load_synthetic()
_REAL:      list[Sample] = _load_real()
_TTB_LIVE:  list[Sample] = _load_ttb_live()
ALL_SAMPLES: list[Sample] = _SYNTHETIC + _REAL + _TTB_LIVE


# Picker = curated COLA Cloud demo set. Two motivations for trimming:
#   - The user's task is to demo the engine end-to-end on TTB-approved
#     labels, with both happy paths (auto-pass) and a few failures
#     (needs-review) so the HITL surface is visible.
#   - TTB-live samples have empty ABV/Net contents on the form side, so
#     they always land in needs-confirm — they're more useful in the
#     full gallery view than in the demo dropdown.
# The full universe (synthetic + every COLA Cloud row + every TTB-live
# row with an image) is still exposed via list_all_samples() for the
# /samples gallery page; the picker on /upload stays small and curated.
_PICKER_FAIL_CAP = 5  # how many needs-review labels to surface


def list_samples() -> list[Sample]:
    """Return the curated COLA Cloud subset shown in the /upload picker.

    Composition (depends on test/eval/real_audit.json's engine verdicts):
      - every COLA Cloud row the audit marked auto-pass
      - up to _PICKER_FAIL_CAP rows the audit marked needs-review (so
        the demo includes visible failure cases)
    Ordering: auto-pass first, then the fails, so the dropdown opens
    with the happy path.

    Synthetic + TTB-live samples are intentionally excluded from the
    picker; they're still accessible via list_all_samples() and by id.
    """
    real_with_image = [s for s in _REAL if s.image_path.exists()]
    auto_pass = [s for s in real_with_image if s.expected_outcome == "auto-pass"]
    fails     = [s for s in real_with_image if s.expected_outcome == "needs-review"][:_PICKER_FAIL_CAP]
    return auto_pass + fails


def list_all_samples() -> list[Sample]:
    """Return every sample with a label image on disk — the full universe
    feeding the /samples gallery page.

    Tiers in display order:
      - real     : COLA Cloud free-sample labels (form data fully populated)
      - ttb-live : scraped from the TTB Public Registry (form data minus
                   ABV/Net which the agent edits on the verify form)
      - synthetic: hand-crafted controlled cases (kept last; CI fixtures)
    """
    real      = [s for s in _REAL      if s.image_path.exists()]
    ttb_live  = [s for s in _TTB_LIVE  if s.image_path.exists()]
    synthetic = [s for s in _SYNTHETIC if s.image_path.exists()]
    return real + ttb_live + synthetic


def get_sample_by_id(sample_id: str) -> Sample | None:
    """Resolve a sample by id — covers BOTH real and synthetic so the
    test pack and any cached agent links keep working even after
    synthetic was dropped from the picker."""
    for s in ALL_SAMPLES:
        if s.id == sample_id:
            return s
    return None
