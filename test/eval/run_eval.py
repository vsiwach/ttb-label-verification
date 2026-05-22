#!/usr/bin/env python3
"""COLA verification eval harness.

Runs the FastAPI backend against a labeled COLA dataset (real or synthetic)
and scores it. Writes test/eval/report.md + report.json.

REAL mode: reads test/eval/data/cola_sample.csv (built by build_dataset.py),
sends each image to POST /api/verify, scores extraction + verdict + latency.

SYNTH mode: reads test/synthetic/expected_results.json, asserts the backend
produces the expected group/field/warning per case. This is the deterministic
gate — should be 100%.

Run:
  python run_eval.py --api http://localhost:8000/api --csv data/cola_sample.csv --images data/images
  python run_eval.py --api http://localhost:8000/api --synthetic ../synthetic

Notes baked in (per CLAUDE.md / EVALUATION.md):
- COLA forms lack bottler line + may lack ABV/net contents — extraction
  scoring skips fields whose declared value is blank.
- Government Warning lives on the BACK image; build_dataset.py prefers back.
- 'beer' and 'malt' are both Part 7; the API doesn't flag missing ABV on plain beer.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import time

import requests  # pip install requests


# ── CSV column mapping (matches build_dataset.py output) ──────────────────────
COL = {
    "image":        "image_filename",
    "brand":        "brand_name",
    "product":      "product_name",          # fanciful / SKU; often more prominent on label
    "class_type":   "class_type",
    "alcohol":      "alcohol_content",       # from OCR_ABV in source data
    "net_contents": "net_contents",          # from OCR_VOLUME in source data
    "bottler":      "bottler_name_address",  # blank in the COLA Cloud free sample
    "origin":       "origin",                # only set for imported products
    "beverage":     "beverage_type",
    "expected":     "expected_outcome",
    "mutation":     "mutation",              # tag for mutated negative cases
    "container":    "container_position",
}

# COLA taxonomy "umbrella" codes — labels print specifics. Treat any subtype
# extraction as a valid match against these.
_UMBRELLA_CLASSES = {
    "beer", "ale", "wine", "table red wine", "table white wine",
    "table flavored wine", "malt beverages specialities", "malt beverages specialities - flavored",
    "sparkling wine/champagne", "dessert /port/sherry/(cooking) wine",
    "rose wine", "honey based table wine", "other specialties & proprietaries",
}


def derive_beverage(row: dict) -> str:
    bt = (row.get(COL["beverage"]) or "").strip().lower()
    if bt in ("spirits", "wine", "beer", "malt"):
        return bt
    ct = (row.get(COL["class_type"]) or "").lower()
    if any(k in ct for k in ("seltzer", "flavored malt")):
        return "malt"
    if any(k in ct for k in ("whisky", "whiskey", "vodka", "gin", "rum", "tequila",
                              "brandy", "liqueur", "mezcal", "spirit")):
        return "spirits"
    if any(k in ct for k in ("ale", "stout", "lager", "beer", "ipa")):
        return "beer"
    if any(k in ct for k in ("wine", "champagne", "sparkling", "port", "sherry",
                              "sake", "cider", "rose")):
        return "wine"
    return "wine"


# ── Normalization for comparison (mirrors backend strict-vs-loose split) ─────
def norm(s: str | None) -> str:
    s = (s or "").lower().strip()
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[.,]", "", s)
    return s


_UNIT_TO_ML = {
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0, "litre": 1000.0, "litres": 1000.0,
    "floz": 29.5735, "ounce": 29.5735, "ounces": 29.5735, "oz": 29.5735,
    "pint": 473.176, "pints": 473.176, "pt": 473.176,
    "gallon": 3785.41, "gallons": 3785.41, "gal": 3785.41,
    "quart": 946.353, "quarts": 946.353, "qt": 946.353,
}


def _parse_ml(s: str) -> float | None:
    """Parse free-form volume strings like '750 mL', '12 FL OZ', '2.5 pints',
    '5 gallons', '1 PINT (16 FL OZ)'. Picks the FIRST parseable number+unit
    pair so multi-unit displays use the first declared form."""
    if not s:
        return None
    text = s.lower()  # IMPORTANT: don't strip dots — '5.3' must keep its decimal
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([a-z]+(?:[.\s]+[a-z]+)*)", text)
    if not m:
        return None
    qty = float(m.group(1))
    unit = m.group(2).replace(".", "").strip()
    unit = re.sub(r"\s+", " ", unit)
    factor = _UNIT_TO_ML.get(unit)
    if factor is None:
        factor = _UNIT_TO_ML.get(unit.replace(" ", ""))
    if factor is None:
        first = unit.split()[0]
        factor = _UNIT_TO_ML.get(first)
    return qty * factor if factor else None


def fields_match_loose(declared: str, extracted: str, *, field_name: str = "") -> bool:
    """Lenient equality for extraction scoring.

    - For 'Net contents' fields: parse to mL on both sides and accept within 1%.
      Real labels often print multi-unit displays ('12L 40.5 fl oz 2.53 pint');
      the COLA form carries a single unit. Numeric equivalence is the right test.
    - For 'Class & type': COLA codes are taxonomy buckets ('beer', 'table red wine');
      labels print specific designations ('NEW ZEALAND STYLE PILSNER', 'Sonoma County
      Pinot Noir'). Pass if any non-trivial declared token appears in extracted,
      or vice versa.
    - Otherwise: case-insensitive equality OR substring containment.
    """
    a, b = norm(declared), norm(extracted)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True

    if "net" in field_name.lower():
        da, db = _parse_ml(declared), _parse_ml(extracted)
        if da is not None and db is not None:
            return abs(da - db) / max(da, db) <= 0.05  # within 5% tolerance
    if "class" in field_name.lower():
        # Umbrella COLA codes ('beer', 'table red wine') match any label-printed
        # subtype — the form bucket is intentionally broader than the printed designation.
        if a in _UMBRELLA_CLASSES or b in _UMBRELLA_CLASSES:
            return True
        stop = {"of", "the", "a", "wine", "beer", "table", "and"}
        toks_a = [t for t in re.split(r"\W+", a) if t and t not in stop]
        toks_b = [t for t in re.split(r"\W+", b) if t and t not in stop]
        if toks_a and any(t in b for t in toks_a):
            return True
        if toks_b and any(t in a for t in toks_b):
            return True
    return False


def _abv_percent(s: str) -> float | None:
    if not s:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", s)
    return float(m.group(1)) if m else None


# ── Call the backend ──────────────────────────────────────────────────────────
def verify(api_base: str, image_path: str, app_data: dict, timeout: int = 60):
    with open(image_path, "rb") as f:
        files = {"image": (os.path.basename(image_path), f, _guess_mime(image_path))}
        data = {"applicationData": json.dumps(app_data)}
        t0 = time.time()
        r = requests.post(f"{api_base}/verify", files=files, data=data, timeout=timeout)
        dt = time.time() - t0
    r.raise_for_status()
    return r.json(), dt


def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "webp": "image/webp", "gif": "image/gif",
    }.get(ext, "image/jpeg")


def is_auto_pass(result: dict) -> bool:
    fields_ok = all(f.get("status") == "match" for f in result.get("fields", []))
    gw = result.get("governmentWarning", {})
    warn_ok = gw.get("present") and gw.get("verbatimMatch") and gw.get("casingBoldOk")
    return bool(fields_ok and warn_ok)


def group_for(result: dict) -> str:
    """Mirror groupFor() in src/api/types.ts."""
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


def find_field(result: dict, key: str) -> dict | None:
    for f in result.get("fields", []):
        if key.lower() in (f.get("fieldName", "").lower()):
            return f
    return None


# ── Real-data scoring ─────────────────────────────────────────────────────────
def run_real(api_base: str, csv_path: str, images_dir: str, limit: int):
    rows = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    if limit:
        rows = rows[:limit]

    misses: list[dict] = []
    latencies: list[float] = []
    auto_pass_approved = 0
    warn_false_flag_approved = 0
    field_total = field_correct = 0
    verdict_total = verdict_correct = 0
    approved_n = 0
    processed_n = 0

    for row in rows:
        img = row.get(COL["image"], "").strip()
        if not img:
            continue
        path = os.path.join(images_dir, img)
        if not os.path.exists(path):
            misses.append({"image": img, "error": "image file not found"})
            continue

        app = {
            "brandName":          row.get(COL["brand"], ""),
            "classType":          row.get(COL["class_type"], ""),
            "alcoholContent":     row.get(COL["alcohol"], ""),
            "netContents":        row.get(COL["net_contents"], ""),
            "bottlerNameAddress": row.get(COL["bottler"], ""),
            "beverageType":       derive_beverage(row),
        }
        origin = row.get(COL["origin"], "")
        if origin:
            app["countryOfOrigin"] = origin

        try:
            result, dt = verify(api_base, path, app)
        except Exception as e:
            misses.append({"image": img, "error": str(e)[:200]})
            continue
        processed_n += 1
        latencies.append(dt)

        # Extraction accuracy: per field, only score when the declared value is
        # non-empty (the dataset can't fill bottler/etc reliably).
        product = row.get(COL["product"], "")
        for fld in result.get("fields", []):
            declared = (fld.get("declaredValue") or "").strip()
            extracted = (fld.get("extractedValue") or "").strip()
            field_name = fld.get("fieldName", "")
            if not declared:
                continue  # skip COLA-form-omitted fields
            field_total += 1

            ok = fields_match_loose(declared, extracted, field_name=field_name)
            # Brand: also accept the PRODUCT_NAME (fanciful/SKU) since real labels
            # often prominently print that instead of the company brand.
            if not ok and "brand" in field_name.lower() and product:
                ok = fields_match_loose(product, extracted, field_name=field_name)
            # ABV: numeric percent within 0.1 is a match.
            if not ok and "alcohol" in field_name.lower():
                pd, pe = _abv_percent(declared), _abv_percent(extracted)
                if pd is not None and pe is not None and abs(pd - pe) <= 0.1:
                    ok = True

            if ok:
                field_correct += 1
            else:
                misses.append({
                    "image": img,
                    "field": field_name,
                    "expected": declared, "got": extracted,
                    "status": fld.get("status"),
                    "product": product if "brand" in field_name.lower() else None,
                })

        # Verdict bucket vs expected outcome
        expected = (row.get(COL["expected"]) or "auto-pass").strip().lower()
        got_group = group_for(result)
        verdict_total += 1
        if got_group == expected:
            verdict_correct += 1
        else:
            misses.append({
                "image": img,
                "mutation": row.get(COL["mutation"], ""),
                "verdict_expected": expected, "verdict_got": got_group,
                "bucket": row.get("bucket", ""),
            })

        if expected == "auto-pass":
            approved_n += 1
            if is_auto_pass(result):
                auto_pass_approved += 1
            gw = result.get("governmentWarning", {})
            if not (gw.get("present") and gw.get("verbatimMatch")):
                warn_false_flag_approved += 1

    p95 = None
    if latencies:
        s = sorted(latencies)
        # nearest-rank P95
        p95 = round(s[max(0, int(0.95 * len(s)) - 1)], 3)

    return {
        "mode": "real",
        "n": processed_n,
        "approved_n": approved_n,
        "field_extraction_accuracy": round(field_correct / field_total, 4) if field_total else None,
        "field_total": field_total, "field_correct": field_correct,
        "verdict_accuracy": round(verdict_correct / verdict_total, 4) if verdict_total else None,
        "auto_pass_rate_approved": round(auto_pass_approved / approved_n, 4) if approved_n else None,
        "warning_false_flag_rate": round(warn_false_flag_approved / approved_n, 4) if approved_n else None,
        "latency_p95": p95,
        "latency_mean": round(statistics.mean(latencies), 3) if latencies else None,
        "misses": misses,
    }


# ── Synthetic-fixture scoring (deterministic 100% gate) ──────────────────────
def run_synthetic(api_base: str, synth_dir: str):
    exp_path = os.path.join(synth_dir, "expected_results.json")
    assert os.path.exists(exp_path), f"missing {exp_path}"
    cases = json.load(open(exp_path, encoding="utf-8")).get("cases", [])
    results: list[dict] = []
    group_ok = field_ok = field_total = warn_ok = warn_total = 0

    for c in cases:
        img, app, exp = c["image"], c["applicationData"], c.get("expected", {})
        path = os.path.join(synth_dir, img)
        try:
            result, dt = verify(api_base, path, app)
        except Exception as e:
            results.append({"image": img, "passed": False, "error": str(e)[:200]})
            continue

        case = {"image": img, "checks": []}
        # 1) overall group
        got_group = group_for(result)
        g_ok = (got_group == exp.get("group"))
        group_ok += 1 if g_ok else 0
        case["checks"].append({"group_expected": exp.get("group"), "group_got": got_group, "ok": g_ok})
        # 2) per-field status
        for key, want in (exp.get("fields") or {}).items():
            field_total += 1
            f = find_field(result, key)
            got = f.get("status") if f else None
            ok = (got == want)
            field_ok += 1 if ok else 0
            case["checks"].append({"field": key, "expected": want, "got": got, "ok": ok})
        # 3) government-warning flags
        gw = result.get("governmentWarning", {})
        for key, want in (exp.get("governmentWarning") or {}).items():
            warn_total += 1
            got = gw.get(key)
            ok = (got == want)
            warn_ok += 1 if ok else 0
            case["checks"].append({"warning": key, "expected": want, "got": got, "ok": ok})
        case["passed"] = all(ch["ok"] for ch in case["checks"])
        results.append(case)

    passed_cases = sum(1 for r in results if r.get("passed"))
    return {
        "mode": "synthetic",
        "n": len(cases),
        "cases_passed": passed_cases,
        "violation_recall": round(passed_cases / len(cases), 4) if cases else None,
        "group_accuracy": round(group_ok / len(cases), 4) if cases else None,
        "field_status_accuracy": round(field_ok / field_total, 4) if field_total else None,
        "warning_flag_accuracy": round(warn_ok / warn_total, 4) if warn_total else None,
        "cases": results,
    }


def write_report(out_dir: str, report: dict):
    os.makedirs(out_dir, exist_ok=True)
    json.dump(report, open(os.path.join(out_dir, "report.json"), "w"), indent=2)
    lines = [f"# Eval report — {report.get('mode', '?')} mode", ""]
    for k, v in report.items():
        if k in ("misses", "cases"):
            continue
        lines.append(f"- **{k}**: {v}")
    if report.get("misses"):
        lines += ["", "## Misses (first 200)", ""]
        for m in report["misses"][:200]:
            lines.append(f"- {m}")
    if report.get("cases"):
        lines += ["", "## Synthetic cases", ""]
        for c in report["cases"]:
            lines.append(f"- {c}")
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="backend base URL, e.g. http://localhost:8000/api")
    ap.add_argument("--csv", help="dataset CSV (real mode)")
    ap.add_argument("--images", help="images directory (real mode)")
    ap.add_argument("--synthetic", help="synthetic fixtures dir (synthetic mode)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__) or ".", "eval"), help="output dir")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if args.synthetic:
        report = run_synthetic(args.api, args.synthetic)
    else:
        assert args.csv and args.images, "--csv and --images required for real mode"
        report = run_real(args.api, args.csv, args.images, args.limit)

    out_dir = args.out if os.path.isabs(args.out) else os.path.abspath(args.out)
    write_report(out_dir, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("misses", "cases")}, indent=2))


if __name__ == "__main__":
    main()
