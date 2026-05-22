#!/usr/bin/env python3
"""Build a stratified eval subset from the COLA Cloud free sample.

Reads cola.csv + cola_image.csv (test/eval/data/), picks a small set covering
the categories in TEST_PLAN.md §B, downloads each label's front + back images
from the COLA Cloud CDN (webp), and emits:
  - test/eval/data/cola_sample.csv  — flat per-image row consumed by run_eval.py
  - test/eval/data/images/<TTB_IMAGE_ID>.webp

Each approved row is tagged expected_outcome=auto-pass. A separate set of
'mutation' rows for the same image are added with `mutation` set to a known
violation type ('shrink_net_contents' / 'paraphrase_warning' / 'titlecase_warning'
/ 'missing_warning') and expected_outcome=needs-review. The harness applies
the mutation to the declared application data (or expected warning) so the
rules engine sees a violation without us having to re-render artwork.
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

# Stratification buckets (label -> CSV predicate). The first match wins.
def _bucket(row: dict) -> str | None:
    pt = (row.get("PRODUCT_TYPE") or "").lower()
    cn = (row.get("CLASS_NAME") or "").lower()
    cat = (row.get("LLM_CATEGORY") or "").lower()
    imp = (row.get("DOMESTIC_OR_IMPORTED") or "").lower()
    if "bourbon" in cn or "bourbon" in cat:
        return "spirits_bourbon"
    if "scotch" in cn or "scotch" in cat:
        return "spirits_scotch_import" if imp == "imported" else "spirits_scotch"
    if "tequila" in cn or "tequila" in cat or "mezcal" in cn:
        return "spirits_tequila_import" if imp == "imported" else "spirits_tequila"
    if "vodka" in cn or "vodka" in cat:
        return "spirits_vodka"
    if "gin" in cn or "gin" in cat:
        return "spirits_gin"
    if "rum" in cn or "rum" in cat:
        return "spirits_rum"
    if "whisky" in cn and pt == "distilled spirits":
        return "spirits_whisky_other"
    if "sparkling" in cn or "champagne" in cn or "sparkling" in cat:
        return "wine_sparkling"
    if "table white" in cn or "white wine" in cat or "chardonnay" in cat or "riesling" in cat:
        return "wine_white_import" if imp == "imported" else "wine_white"
    if "table red" in cn or "red wine" in cat or "cabernet" in cat or "pinot noir" in cat:
        return "wine_red_import" if imp == "imported" else "wine_red"
    if "dessert" in cn or "port" in cn or "sherry" in cn:
        return "wine_fortified"
    if "rose" in cn:
        return "wine_rose"
    if "ale" in cn or "ipa" in cat or "pale ale" in cat:
        return "beer_ipa_ale"
    if "stout" in cn:
        return "beer_stout"
    if "lager" in cat:
        return "beer_lager"
    if cn == "beer":
        return "beer_generic"
    if "malt beverages specialities" in cn or "seltzer" in cat or "flavored" in cn:
        return "malt_flavored"
    if "liqueur" in cn or "liqueur" in cat:
        return "spirits_liqueur"
    if pt == "wine":
        return "wine_other"
    if pt == "malt beverage":
        return "beer_other"
    if pt == "distilled spirits":
        return "spirits_other"
    return None


def _derive_beverage(pt: str, cn: str) -> str:
    pt = (pt or "").lower()
    cn = (cn or "").lower()
    if "malt beverages specialities" in cn or "seltzer" in cn or "flavored" in cn:
        return "malt"
    if pt == "distilled spirits":
        return "spirits"
    if pt == "wine":
        return "wine"
    if pt == "malt beverage":
        return "beer"
    return "wine"  # safe default for the dataset (mostly wine)


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
    """Build a 'NNN mL' or 'NN FL OZ' style string from OCR_VOLUME columns."""
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


def _bottler(row: dict) -> str:
    """The COLA Cloud free-sample dataset doesn't carry the bottler name+address
    line — that field exists on the COLA form but isn't exported. We leave it
    blank; the rules engine treats empty-declared on a required field as
    informational (extracted value is shown but no false-flag is raised),
    since TTB has already verified that field at form-acceptance time.
    """
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-bucket", type=int, default=2, help="approved samples per category")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mutations", type=int, default=8, help="how many mutation rows to add")
    ap.add_argument("--include-back", action="store_true", default=True,
                    help="when a back image exists, prefer it (warning lives there)")
    ap.add_argument("--max", type=int, default=80, help="hard cap on total approved rows")
    args = ap.parse_args()

    random.seed(args.seed)

    cola = list(csv.DictReader(open(COLA_CSV)))
    image_rows = list(csv.DictReader(open(IMAGE_CSV)))
    by_ttb_id: dict[str, list[dict]] = defaultdict(list)
    for ir in image_rows:
        by_ttb_id[ir["TTB_ID"]].append(ir)

    # Pick the image whose OCR'd text actually contains "GOVERNMENT WARNING".
    # That's the image the verifier needs — labels are multi-image and the
    # warning often only lives on one panel. If none of the available images
    # carries the warning text, return None and we skip that COLA.
    def best_image(ttb_id: str) -> dict | None:
        imgs = by_ttb_id.get(ttb_id, [])
        if not imgs:
            return None
        # Prefer images whose OCR_TEXT explicitly contains "GOVERNMENT WARNING".
        with_warning = [i for i in imgs if "GOVERNMENT WARNING" in (i.get("OCR_TEXT") or "").upper()]
        if with_warning:
            # If multiple, prefer back over front.
            back = next((i for i in with_warning if i["CONTAINER_POSITION"].lower() == "back"), None)
            return back or with_warning[0]
        return None  # skip — warning not on any image we have

    # Filter out keg-scale containers: when OCR_VOLUME_UNIT == 'gallons' and
    # the quantity is large, the COLA may have been approved for multiple keg
    # sizes and the label image often shows a DIFFERENT keg size than the
    # dataset captured. That's a real-world data inconsistency, not an
    # extraction or rules-engine signal.
    def _is_keg(r: dict) -> bool:
        unit = (r.get("OCR_VOLUME_UNIT") or "").strip().lower()
        try:
            v = float(r.get("OCR_VOLUME") or 0)
        except ValueError:
            v = 0
        return unit in ("gallons", "gallon") and v >= 5.0

    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in cola:
        if _is_keg(r):
            continue
        b = _bucket(r)
        if b:
            buckets[b].append(r)

    print(f"Buckets discovered: {len(buckets)}")
    for k in sorted(buckets):
        print(f"  {len(buckets[k]):4} {k}")

    picked: list[tuple[dict, dict]] = []  # (cola row, image row)
    for b, rows in sorted(buckets.items()):
        random.shuffle(rows)
        for r in rows[: args.per_bucket]:
            img = best_image(r["TTB_ID"])
            if img is None:
                continue
            picked.append((r, img))
            if len(picked) >= args.max:
                break
        if len(picked) >= args.max:
            break

    print(f"\nPicked {len(picked)} approved rows. Downloading images …")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for cola_row, img_row in picked:
        ttb_image_id = img_row["TTB_IMAGE_ID"]
        dest = IMAGES_DIR / f"{ttb_image_id}.webp"
        if _download(CDN.format(ttb_image_id), dest):
            ok += 1
    print(f"  {ok}/{len(picked)} downloaded")

    # Emit cola_sample.csv with logical columns the harness expects.
    written: list[dict] = []
    for cola_row, img_row in picked:
        ttb_image_id = img_row["TTB_IMAGE_ID"]
        dest = IMAGES_DIR / f"{ttb_image_id}.webp"
        if not dest.exists():
            continue
        row = {
            "ttb_id": cola_row["TTB_ID"],
            "ttb_image_id": ttb_image_id,
            "image_filename": dest.name,
            "container_position": img_row.get("CONTAINER_POSITION", ""),
            "image_ocr_text": img_row.get("OCR_TEXT", ""),
            "brand_name": cola_row.get("BRAND_NAME", ""),
            # product/fanciful name (often the prominent text on the label)
            "product_name": cola_row.get("PRODUCT_NAME", ""),
            "class_type": cola_row.get("CLASS_NAME", ""),
            "alcohol_content": _parse_abv(cola_row),
            "net_contents": _parse_net_contents(cola_row),
            "bottler_name_address": _bottler(cola_row),
            "origin": cola_row.get("ORIGIN_NAME", "") if (cola_row.get("DOMESTIC_OR_IMPORTED") or "").lower() == "imported" else "",
            "beverage_type": _derive_beverage(cola_row.get("PRODUCT_TYPE", ""), cola_row.get("CLASS_NAME", "")),
            "bucket": _bucket(cola_row),
            "domestic_or_imported": cola_row.get("DOMESTIC_OR_IMPORTED", ""),
            "expected_outcome": "auto-pass",
            "mutation": "",
        }
        written.append(row)

    # Mutation rows: clone existing rows and mutate the declared application
    # data so the engine catches a real violation against the unchanged label.
    # We only generate mutation kinds that work without re-rendering artwork —
    # paraphrase/titlecase/missing-warning would need image edits.
    mutation_kinds = [
        "shrink_net_contents", "shrink_net_contents", "shrink_net_contents",
        "brand_mismatch", "brand_mismatch", "brand_mismatch",
        "abv_mismatch", "abv_mismatch",
    ]
    if written:
        sample_for_mut = random.sample(written, k=min(args.mutations, len(written)))
        for src, kind in zip(sample_for_mut, mutation_kinds):
            mut = dict(src)
            mut["expected_outcome"] = "needs-review"
            mut["mutation"] = kind
            # Apply application-side mutations that the rules engine WILL catch.
            if kind == "shrink_net_contents":
                # Force a flag by declaring a different size from the label.
                if "750 mL" in mut["net_contents"]:
                    mut["net_contents"] = "700 mL"
                elif "12 FL OZ" in mut["net_contents"]:
                    mut["net_contents"] = "16 FL OZ"
                else:
                    mut["net_contents"] = "999 mL"
            elif kind == "brand_mismatch":
                mut["brand_name"] = mut["brand_name"] + " ABSOLUTELY-WRONG"
            elif kind == "abv_mismatch":
                # Pick a clearly different ABV.
                mut["alcohol_content"] = "99.9% Alc./Vol."
            written.append(mut)

    fieldnames = list(written[0].keys()) if written else []
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in written:
            w.writerow(row)
    print(f"\nWrote {len(written)} rows to {OUT_CSV}")
    print(f"  approved:        {sum(1 for r in written if r['expected_outcome'] == 'auto-pass')}")
    print(f"  needs-review:    {sum(1 for r in written if r['expected_outcome'] == 'needs-review')}")
    print(f"  bucket coverage: {len({r['bucket'] for r in written})} buckets")


if __name__ == "__main__":
    main()
