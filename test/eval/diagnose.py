#!/usr/bin/env python3
"""Diagnostic helper used by the parallel test agents.

Each agent picks random samples from the COLA Cloud full pool (1,000 records)
filtered by their category, runs them through the live backend, and writes a
structured findings JSON. The orchestrator then synthesizes across agents.

Usage:
    python diagnose.py --pool cola_cloud --filter <expr> --limit N \
        --api http://localhost:8000/api --out <agent_name>.json

Filter is a Python expression evaluated against the row dict. Examples:
    --filter "row['PRODUCT_TYPE']=='wine' and row['DOMESTIC_OR_IMPORTED']=='imported'"
    --filter "'bourbon' in row['CLASS_NAME'].lower()"
    --filter "_has_gws_finding(row)"

Output JSON:
    {
      "agent": "<name>", "category": "<...>", "n": int,
      "results": [{
        "ttb_id": ..., "image": ..., "brand": ..., "class_type": ...,
        "expected": <inferred>, "verdict_group": ...,
        "warning": {"verbatim": bool, "casingBoldOk": bool, "fontSizeOk": bool,
                    "present": bool, "deviations": [str], "detected": str},
        "fields": [{"name", "status", "declared", "extracted", "note"}],
        "root_cause": "<categorized failure reason or 'ok'>",
        "latency_s": float
      }, ...],
      "summary": {"auto-pass": n, "needs-confirm": n, "needs-review": n,
                  "root_causes": {<cause>: count}}
    }
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import time
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
IMAGES_DIR = DATA_DIR / "images"
COLA_CSV = DATA_DIR / "cola.csv"
IMAGE_CSV = DATA_DIR / "cola_image.csv"
CDN = "https://dyuie4zgfxmt6.cloudfront.net/{}.webp"


# ── Helpers exposed in --filter expressions ─────────────────────────────────
_GWS_FINDING_RE = re.compile(r"(correct the spelling|approved despite error|change the statement so the spelling)", re.IGNORECASE)


def _has_gws_finding(row: dict) -> bool:
    return bool(_GWS_FINDING_RE.search(row.get("APPROVAL_QUALIFICATIONS") or ""))


def _is_keg(row: dict) -> bool:
    try:
        v = float(row.get("OCR_VOLUME") or 0)
    except ValueError:
        v = 0
    return (row.get("OCR_VOLUME_UNIT") or "").lower() in ("gallons", "gallon") and v >= 5.0


# ── Load source data once ──────────────────────────────────────────────────
def _load_pool():
    cola = list(csv.DictReader(open(COLA_CSV)))
    imgs = list(csv.DictReader(open(IMAGE_CSV)))
    img_by_ttb = {}
    for ir in imgs:
        img_by_ttb.setdefault(ir["TTB_ID"], []).append(ir)
    return cola, img_by_ttb


def _best_image_with_warning(ttb_id: str, img_by_ttb: dict) -> dict | None:
    images = img_by_ttb.get(ttb_id, [])
    with_warning = [i for i in images if "GOVERNMENT WARNING" in (i.get("OCR_TEXT") or "").upper()]
    if not with_warning:
        return None
    back = next((i for i in with_warning if i["CONTAINER_POSITION"].lower() == "back"), None)
    return back or with_warning[0]


def _front_image(ttb_id: str, img_by_ttb: dict) -> dict | None:
    images = img_by_ttb.get(ttb_id, [])
    return next((i for i in images if i["CONTAINER_POSITION"].lower() == "front"), None)


def _back_image(ttb_id: str, img_by_ttb: dict) -> dict | None:
    images = img_by_ttb.get(ttb_id, [])
    return next((i for i in images if i["CONTAINER_POSITION"].lower() == "back"), None)


def _download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ttb-eval/0.1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"  WARN download: {e}", flush=True)
        return False


# ── API call ────────────────────────────────────────────────────────────────
def _verify(api_base: str, image_path: Path, app_data: dict, timeout: int = 60) -> tuple[dict, float]:
    import requests
    with open(image_path, "rb") as f:
        files = {"image": (image_path.name, f, "image/webp")}
        data = {"applicationData": json.dumps(app_data)}
        t0 = time.time()
        r = requests.post(f"{api_base}/verify", files=files, data=data, timeout=timeout)
        dt = time.time() - t0
    r.raise_for_status()
    return r.json(), dt


# ── Bucket logic mirrors src/api/types.ts ──────────────────────────────────
def _group_for(result: dict) -> str:
    gw = result.get("governmentWarning", {})
    has_flag = (
        any(f.get("status") == "flag" for f in result.get("fields", []))
        or gw.get("present") is False
        or gw.get("verbatimMatch") is False
    )
    has_likely = any(f.get("status") == "likely" for f in result.get("fields", []))
    if has_flag:
        return "needs-review"
    if has_likely:
        return "needs-confirm"
    return "auto-pass"


# ── Root-cause categorization ───────────────────────────────────────────────
def _root_cause(row: dict, result: dict, group: str, expected: str) -> str:
    if group == expected:
        return "ok"
    gw = result.get("governmentWarning", {})
    fields = result.get("fields", [])
    flag_fields = [f for f in fields if f.get("status") == "flag"]
    likely_fields = [f for f in fields if f.get("status") == "likely"]

    # Warning-driven needs-review
    if expected == "auto-pass" and group == "needs-review":
        if not gw.get("present"):
            return "warning_missing"
        if not gw.get("verbatimMatch"):
            return "warning_verbatim_false"
        if not gw.get("casingBoldOk"):
            return "warning_casing_bold_false"
        if flag_fields:
            f = flag_fields[0]
            name = f.get("fieldName", "").lower()
            if "brand" in name:
                return "field_flag_brand"
            if "net" in name:
                return "field_flag_net_contents"
            if "class" in name:
                return "field_flag_class"
            if "alcohol" in name:
                return "field_flag_abv"
            if "country" in name or "origin" in name:
                return "field_flag_country"
            return "field_flag_other"
        return "review_unknown"

    if expected == "auto-pass" and group == "needs-confirm":
        # Got a likely — categorize
        if likely_fields:
            f = likely_fields[0]
            name = f.get("fieldName", "").lower()
            note = (f.get("note") or "").lower()
            if "low extractor confidence" in note:
                return "confirm_low_confidence"
            if "may be on another panel" in note:
                return "confirm_missing_extracted"
            if "brand" in name:
                return "confirm_brand_likely"
            if "alcohol" in name:
                return "confirm_abv_likely"
            if "country" in name:
                return "confirm_country_likely"
            return "confirm_other"
        return "confirm_unknown"

    if expected == "needs-review" and group != "needs-review":
        # We MISSED a real issue
        return "missed_should_flag"

    return "other"


# ── Main run loop for the agent ─────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, help="agent name for the report")
    ap.add_argument("--category", required=True, help="human-readable category description")
    ap.add_argument("--api", default="http://localhost:8000/api")
    ap.add_argument("--filter", default="True", help="Python expression on row dict")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--image-mode", choices=["warning", "front", "back"], default="warning",
                    help="which image to upload (default: image with warning)")
    ap.add_argument("--expected", choices=["auto-pass", "needs-review", "infer"], default="infer",
                    help="ground-truth bucket for these samples")
    args = ap.parse_args()

    random.seed(args.seed)
    cola, img_by_ttb = _load_pool()

    # Apply filter
    matching = []
    for row in cola:
        try:
            if eval(args.filter, {"_has_gws_finding": _has_gws_finding, "_is_keg": _is_keg, "re": re}, {"row": row}):
                matching.append(row)
        except Exception as e:
            print(f"filter error on {row.get('TTB_ID','?')}: {e}", flush=True)
    random.shuffle(matching)

    # Pick samples
    pick_image = {"warning": _best_image_with_warning, "front": _front_image, "back": _back_image}[args.image_mode]
    results = []
    summary = {"auto-pass": 0, "needs-confirm": 0, "needs-review": 0, "root_causes": {}}
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[{args.agent}] category={args.category} matching={len(matching)} target={args.limit}", flush=True)

    for row in matching:
        if len(results) >= args.limit:
            break
        img = pick_image(row["TTB_ID"], img_by_ttb)
        if img is None:
            continue
        ttb_image_id = img["TTB_IMAGE_ID"]
        dest = IMAGES_DIR / f"{ttb_image_id}.webp"
        if not _download(CDN.format(ttb_image_id), dest):
            continue
        bev = "spirits" if row["PRODUCT_TYPE"] == "distilled spirits" else (
              "wine" if row["PRODUCT_TYPE"] == "wine" else "beer")
        app = {
            "brandName": row["BRAND_NAME"], "classType": row["CLASS_NAME"],
            "alcoholContent": (f"{float(row['OCR_ABV']):g}% Alc./Vol." if row.get("OCR_ABV") else ""),
            "netContents": _net_str(row),
            "bottlerNameAddress": "",
            "beverageType": bev,
        }
        # Pass the COLA form's Product/Fanciful Name so the engine can match
        # against either brand or product (labels often show the SKU prominently).
        if row.get("PRODUCT_NAME"):
            app["productName"] = row["PRODUCT_NAME"]
        if (row.get("DOMESTIC_OR_IMPORTED") or "").lower() == "imported":
            app["countryOfOrigin"] = row.get("ORIGIN_NAME", "")
        try:
            result, dt = _verify(args.api, dest, app)
        except Exception as e:
            print(f"  verify FAIL {ttb_image_id}: {e}", flush=True)
            continue

        group = _group_for(result)
        expected = args.expected if args.expected != "infer" else \
                   ("needs-review" if _has_gws_finding(row) else "auto-pass")
        summary[group] = summary.get(group, 0) + 1
        cause = _root_cause(row, result, group, expected)
        summary["root_causes"][cause] = summary["root_causes"].get(cause, 0) + 1

        gw = result.get("governmentWarning", {})
        rec = {
            "ttb_id": row["TTB_ID"],
            "image": ttb_image_id,
            "container_position": img["CONTAINER_POSITION"],
            "brand": row["BRAND_NAME"],
            "product_name": row.get("PRODUCT_NAME", ""),
            "class_type": row["CLASS_NAME"],
            "expected": expected,
            "verdict_group": group,
            "root_cause": cause,
            "ttb_qualification": (row.get("APPROVAL_QUALIFICATIONS") or "")[:200],
            "warning": {
                "present": gw.get("present"),
                "verbatim": gw.get("verbatimMatch"),
                "casingBoldOk": gw.get("casingBoldOk"),
                "fontSizeOk": gw.get("fontSizeOk"),
                "deviations": [d.get("type") for d in gw.get("deviations", [])],
                "detected_text": gw.get("detectedText", "")[:400],
            },
            "fields": [
                {"name": f["fieldName"], "status": f["status"],
                 "declared": f.get("declaredValue"), "extracted": f.get("extractedValue"),
                 "note": (f.get("note") or "")[:160]}
                for f in result.get("fields", [])
            ],
            "latency_s": round(dt, 2),
        }
        results.append(rec)

    report = {
        "agent": args.agent, "category": args.category, "n": len(results),
        "summary": summary, "results": results,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"[{args.agent}] wrote {args.out} (n={len(results)})", flush=True)
    print(f"  summary: {json.dumps(summary)}")


def _net_str(row: dict) -> str:
    v = (row.get("OCR_VOLUME") or "").strip()
    u = (row.get("OCR_VOLUME_UNIT") or "").strip().lower()
    if not v:
        return ""
    try:
        f = float(v); v = str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        pass
    return f"{v} {('mL' if u in ('milliliters','milliliter','ml') else 'L' if u in ('liters','liter','l') else 'FL OZ' if 'oz' in u else u)}"


if __name__ == "__main__":
    main()
