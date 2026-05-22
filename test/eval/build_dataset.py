#!/usr/bin/env python3
"""Build a stress-test eval set from the COLA Cloud free sample.

The dataset has 1,000 approved COLAs with rich metadata — including
APPROVAL_QUALIFICATIONS, which is TTB's plain-text record of issues they
caught during review. We mine three slices:

  1. CLEAN APPROVED (per category, stratified)        -> expected auto-pass / needs-confirm
  2. TTB-NOTED GWS ISSUES (real labels TTB flagged)   -> expected needs-review
  3. MUTATION CASES (declared data flipped on clean   -> expected needs-review
     approved labels to force specific violations)

Together they let the harness measure:
  - false-positive rate on really-approved labels
  - real-issue detection rate (does our engine find what TTB found?)
  - rejection rate on engineered violations

The TTB data.gov "Public COLA Registry Search and Download" page is an
interactive UI — no bulk CSV. The COLA Cloud free sample is the only
direct-fetch source for the prototype; it covers ~1,000 recent records
across all categories with multi-image metadata and OCR'd text.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
IMAGES_DIR = DATA_DIR / "images"
COLA_CSV = DATA_DIR / "cola.csv"
IMAGE_CSV = DATA_DIR / "cola_image.csv"
OUT_CSV = DATA_DIR / "cola_sample.csv"

CDN = "https://dyuie4zgfxmt6.cloudfront.net/{}.webp"

# Patterns in APPROVAL_QUALIFICATIONS that indicate REAL TTB-noted issues
# (not the boilerplate that's on every record).
_GWS_FINDING_RE = re.compile(
    r"(correct the spelling|approved despite error|change the statement so the spelling)",
    re.IGNORECASE,
)
_CLASS_CHANGE_RE = re.compile(
    r"changed the application by designating",
    re.IGNORECASE,
)


def _has_real_gws_finding(row: dict) -> bool:
    q = row.get("APPROVAL_QUALIFICATIONS") or ""
    return bool(_GWS_FINDING_RE.search(q))


def _has_class_change_finding(row: dict) -> bool:
    q = row.get("APPROVAL_QUALIFICATIONS") or ""
    return bool(_CLASS_CHANGE_RE.search(q))


def _bucket(row: dict) -> str | None:
    pt = (row.get("PRODUCT_TYPE") or "").lower()
    cn = (row.get("CLASS_NAME") or "").lower()
    cat = (row.get("LLM_CATEGORY") or "").lower()
    imp = (row.get("DOMESTIC_OR_IMPORTED") or "").lower()
    if "bourbon" in cn or "bourbon" in cat:           return "spirits_bourbon"
    if "scotch" in cn or "scotch" in cat:
        return "spirits_scotch_import" if imp == "imported" else "spirits_scotch"
    if "tequila" in cn or "tequila" in cat or "mezcal" in cn:
        return "spirits_tequila_import" if imp == "imported" else "spirits_tequila"
    if "vodka" in cn or "vodka" in cat:               return "spirits_vodka"
    if "gin" in cn or "gin" in cat:                    return "spirits_gin"
    if "rum" in cn or "rum" in cat:                    return "spirits_rum"
    if "whisky" in cn and pt == "distilled spirits":   return "spirits_whisky_other"
    if "sparkling" in cn or "champagne" in cn or "sparkling" in cat: return "wine_sparkling"
    if "table white" in cn or "white wine" in cat or "chardonnay" in cat or "riesling" in cat:
        return "wine_white_import" if imp == "imported" else "wine_white"
    if "table red" in cn or "red wine" in cat or "cabernet" in cat or "pinot noir" in cat:
        return "wine_red_import" if imp == "imported" else "wine_red"
    if "dessert" in cn or "port" in cn or "sherry" in cn: return "wine_fortified"
    if "rose" in cn:                                   return "wine_rose"
    if "ale" in cn or "ipa" in cat or "pale ale" in cat: return "beer_ipa_ale"
    if "stout" in cn:                                  return "beer_stout"
    if "lager" in cat:                                 return "beer_lager"
    if cn == "beer":                                   return "beer_generic"
    if "malt beverages specialities" in cn or "seltzer" in cat or "flavored" in cn:
        return "malt_flavored"
    if "liqueur" in cn or "liqueur" in cat:            return "spirits_liqueur"
    if pt == "wine":                                   return "wine_other"
    if pt == "malt beverage":                          return "beer_other"
    if pt == "distilled spirits":                      return "spirits_other"
    return None


def _derive_beverage(pt: str, cn: str) -> str:
    pt, cn = (pt or "").lower(), (cn or "").lower()
    if "malt beverages specialities" in cn or "seltzer" in cn or "flavored" in cn:
        return "malt"
    if pt == "distilled spirits": return "spirits"
    if pt == "wine":              return "wine"
    if pt == "malt beverage":     return "beer"
    return "wine"


def _download(url: str, dest: Path, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ttb-eval/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            dest.write_bytes(data)
            return True
        except Exception as e:
            if attempt == retries - 1:
                print(f"  WARN: download failed for {url}: {e}")
                return False
            time.sleep(0.5 * (attempt + 1))
    return False


def _parse_net_contents(row: dict) -> str:
    v = (row.get("OCR_VOLUME") or "").strip()
    u = (row.get("OCR_VOLUME_UNIT") or "").strip().lower()
    if not v:
        return ""
    try:
        f = float(v)
        v_str = str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        v_str = v
    unit_map = {
        "milliliters": "mL", "milliliter": "mL", "ml": "mL",
        "liters": "L", "liter": "L", "l": "L",
        "fluid ounces": "FL OZ", "fluid ounce": "FL OZ", "fl oz": "FL OZ", "fl. oz.": "FL OZ",
        "ounces": "FL OZ", "ounce": "FL OZ", "oz": "FL OZ",
    }
    return f"{v_str} {unit_map.get(u, u or 'mL')}"


def _parse_abv(row: dict) -> str:
    v = (row.get("OCR_ABV") or "").strip()
    if not v:
        return ""
    try:
        f = float(v)
        return f"{f:g}% Alc./Vol."
    except ValueError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-bucket", type=int, default=4, help="approved samples per category")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mutations", type=int, default=10, help="mutation rows to add")
    ap.add_argument("--max-clean", type=int, default=60, help="hard cap on clean approved rows")
    ap.add_argument("--max-ttb-findings", type=int, default=20, help="cap on TTB-noted GWS rows")
    ap.add_argument("--no-kegs", action="store_true", default=True,
                    help="exclude keg COLAs (multi-size approvals confuse extraction)")
    args = ap.parse_args()

    random.seed(args.seed)

    cola = list(csv.DictReader(open(COLA_CSV)))
    image_rows = list(csv.DictReader(open(IMAGE_CSV)))
    by_ttb_id: dict[str, list[dict]] = defaultdict(list)
    for ir in image_rows:
        by_ttb_id[ir["TTB_ID"]].append(ir)

    def _is_keg(r: dict) -> bool:
        unit = (r.get("OCR_VOLUME_UNIT") or "").strip().lower()
        try:
            v = float(r.get("OCR_VOLUME") or 0)
        except ValueError:
            v = 0
        return unit in ("gallons", "gallon") and v >= 5.0

    def best_image_with_warning(ttb_id: str) -> dict | None:
        imgs = by_ttb_id.get(ttb_id, [])
        if not imgs:
            return None
        with_warning = [i for i in imgs if "GOVERNMENT WARNING" in (i.get("OCR_TEXT") or "").upper()]
        if with_warning:
            back = next((i for i in with_warning if i["CONTAINER_POSITION"].lower() == "back"), None)
            return back or with_warning[0]
        return None

    def row_for_picked(cola_row: dict, img_row: dict, *, expected: str, mutation: str = "", source_tag: str = "clean") -> dict:
        ttb_image_id = img_row["TTB_IMAGE_ID"]
        return {
            "ttb_id": cola_row["TTB_ID"],
            "ttb_image_id": ttb_image_id,
            "image_filename": IMAGES_DIR.joinpath(f"{ttb_image_id}.webp").name,
            "container_position": img_row.get("CONTAINER_POSITION", ""),
            "image_ocr_text": img_row.get("OCR_TEXT", ""),
            "brand_name": cola_row.get("BRAND_NAME", ""),
            "product_name": cola_row.get("PRODUCT_NAME", ""),
            "class_type": cola_row.get("CLASS_NAME", ""),
            "alcohol_content": _parse_abv(cola_row),
            "net_contents": _parse_net_contents(cola_row),
            "bottler_name_address": "",
            "origin": cola_row.get("ORIGIN_NAME", "") if (cola_row.get("DOMESTIC_OR_IMPORTED") or "").lower() == "imported" else "",
            "beverage_type": _derive_beverage(cola_row.get("PRODUCT_TYPE", ""), cola_row.get("CLASS_NAME", "")),
            "bucket": _bucket(cola_row),
            "domestic_or_imported": cola_row.get("DOMESTIC_OR_IMPORTED", ""),
            "expected_outcome": expected,
            "mutation": mutation,
            "source": source_tag,
            "ttb_qualifications": (cola_row.get("APPROVAL_QUALIFICATIONS") or "")[:240],
        }

    # ── Slice 1: TTB-noted GWS findings (real "should-flag" labels) ─────────────
    ttb_findings = [r for r in cola if _has_real_gws_finding(r) and not (args.no_kegs and _is_keg(r))]
    random.shuffle(ttb_findings)
    print(f"Slice 1 — TTB-noted GWS findings available: {len(ttb_findings)}")

    # ── Slice 2: clean approved, stratified by category ─────────────────────────
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in cola:
        if _has_real_gws_finding(r):  # exclude TTB-noted ones from "clean"
            continue
        if args.no_kegs and _is_keg(r):
            continue
        b = _bucket(r)
        if b:
            buckets[b].append(r)
    print(f"Slice 2 — clean approved buckets: {len(buckets)}")

    picked: list[tuple[dict, dict, str, str, str]] = []  # (cola, img, expected, mutation, source)

    # Pick TTB-noted GWS findings first
    n_ttb = 0
    for r in ttb_findings:
        if n_ttb >= args.max_ttb_findings:
            break
        img = best_image_with_warning(r["TTB_ID"])
        if img is None:
            continue
        picked.append((r, img, "needs-review", "", "ttb_gws_finding"))
        n_ttb += 1

    # Pick clean approved with strata
    n_clean = 0
    for b, rows in sorted(buckets.items()):
        random.shuffle(rows)
        per = 0
        for r in rows:
            if per >= args.per_bucket or n_clean >= args.max_clean:
                break
            img = best_image_with_warning(r["TTB_ID"])
            if img is None:
                continue
            picked.append((r, img, "auto-pass", "", "clean_approved"))
            per += 1
            n_clean += 1
        if n_clean >= args.max_clean:
            break

    print(f"\nPicked {len(picked)} total ({n_ttb} TTB-noted + {n_clean} clean). Downloading images …")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for cola_row, img_row, *_ in picked:
        dest = IMAGES_DIR / f"{img_row['TTB_IMAGE_ID']}.webp"
        if _download(CDN.format(img_row["TTB_IMAGE_ID"]), dest):
            ok += 1
    print(f"  {ok}/{len(picked)} downloaded")

    written: list[dict] = []
    for cola_row, img_row, expected, mutation, source_tag in picked:
        dest = IMAGES_DIR / f"{img_row['TTB_IMAGE_ID']}.webp"
        if not dest.exists():
            continue
        written.append(row_for_picked(cola_row, img_row, expected=expected, mutation=mutation, source_tag=source_tag))

    # ── Slice 3: mutation rows — engineered violations on clean approved labels.
    # We apply each mutation kind to a row whose beverage type / extraction makes
    # the violation actually reachable by the engine (no point mutating ABV on
    # plain beer where ABV is optional per 27 CFR 7.63).
    def _eligible(kind: str, row: dict) -> bool:
        bt = row.get("beverage_type", "")
        ct = (row.get("class_type") or "").lower()
        if kind in ("abv_mismatch_high", "abv_mismatch_low"):
            # ABV is mandatory for spirits/wine and for flavored malt beverages.
            if bt in ("spirits", "wine"): return True
            if bt in ("beer", "malt") and any(t in ct for t in ("seltzer","flavored","fruit","spiked","rtd")):
                return True
            return False
        if kind == "country_origin_mismatch":
            return bool(row.get("origin"))  # only imports have COO
        return True

    plan = [
        "shrink_net_contents", "swap_net_contents_unit",
        "brand_mismatch", "brand_mismatch",
        "abv_mismatch_high", "abv_mismatch_low",
        "country_origin_mismatch",
        "class_type_mismatch",
        "shrink_net_contents",
        "abv_mismatch_high",
    ]
    clean = [w for w in written if w["source"] == "clean_approved"]
    used = set()
    for kind in plan:
        candidates = [w for w in clean if _eligible(kind, w) and id(w) not in used]
        if not candidates:
            continue
        src = random.choice(candidates)
        used.add(id(src))
        mut = dict(src)
        mut["expected_outcome"] = "needs-review"
        mut["mutation"] = kind
        mut["source"] = "mutation"
        mut["ttb_qualifications"] = ""
        if kind == "shrink_net_contents":
            if "750 mL" in (mut["net_contents"] or ""):
                mut["net_contents"] = "500 mL"  # bigger gap, well beyond 5% tolerance
            elif "12 FL OZ" in (mut["net_contents"] or ""):
                mut["net_contents"] = "24 FL OZ"
            elif "L" in (mut["net_contents"] or ""):
                mut["net_contents"] = "0.5 L"
            else:
                mut["net_contents"] = "999 mL"
        elif kind == "swap_net_contents_unit":
            mut["net_contents"] = "100 mL"
        elif kind == "brand_mismatch":
            # Use a completely different brand (no overlap with original) so the
            # engine's containment rule cannot pass it as 'likely'.
            mut["brand_name"] = "NONEXISTENT MISMATCH BRAND XYZ"
        elif kind == "abv_mismatch_high":
            mut["alcohol_content"] = "99.9% Alc./Vol."
        elif kind == "abv_mismatch_low":
            mut["alcohol_content"] = "0.4% Alc./Vol."
        elif kind == "country_origin_mismatch":
            mut["origin"] = "Mars"
        elif kind == "class_type_mismatch":
            mut["class_type"] = "infused honey-flavored cocktail wine spirit"
        written.append(mut)

    fieldnames = list(written[0].keys()) if written else []
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in written:
            w.writerow(row)

    print(f"\nWrote {len(written)} rows to {OUT_CSV}")
    by_source = defaultdict(int)
    for r in written:
        by_source[r["source"]] += 1
    for k, v in sorted(by_source.items()):
        print(f"  {v:3} {k}")
    print(f"  bucket coverage: {len({r['bucket'] for r in written})} buckets")


if __name__ == "__main__":
    main()
