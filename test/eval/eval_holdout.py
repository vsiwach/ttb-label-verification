"""Head-to-head eval on the held-out TTB-live 2K: Haiku vs Qwen-v1 vs Qwen-v2.

Hits a running backend's POST /api/verify with each row from the holdout
list. The model under test is whichever extractor the backend was started
with (INFERENCE_MODE=cloud / modal / sft / claude_code / onprem). This
script doesn't know or care — it just measures.

Orchestration:
  Start backend in one terminal, run this script in another. Repeat with
  a different extractor configured. Each run writes a tagged report so
  multiple runs accumulate side-by-side.

  Terminal A:    INFERENCE_MODE=cloud make serve-api
  Terminal B:    python test/eval/eval_holdout.py --report-tag haiku
  (kill A)
  Terminal A:    INFERENCE_MODE=modal MODAL_ENDPOINT_URL=<v1-url> make serve-api
  Terminal B:    python test/eval/eval_holdout.py --report-tag qwen_v1
  (repeat for v2 once deployed)

Metrics per row:
  - per-field exact-match against TTB form (Brand name, Class & type,
    Bottler name/address, Country of origin if non-US)
  - bucket the engine landed in (auto-pass / needs-confirm / needs-review)
  - end-to-end latency (whole /api/verify call)

Outputs:
  test/eval/data/holdout_eval/<tag>_report.json    raw per-row + summary
  test/eval/data/holdout_eval/<tag>_report.md      human-readable summary

After all three runs land, run:
  python test/eval/compare_holdout_models.py

to produce the head-to-head COMPARISON.md.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
TTB_CSV = REPO / "test" / "eval" / "data" / "ttb_live" / "ttb_live.csv"
TTB_IMGS = REPO / "test" / "eval" / "data" / "ttb_live" / "images"
HOLDOUT_TXT = REPO / "test" / "eval" / "data" / "ttb_live_test" / "holdout_ttbids.txt"
OUT_DIR = REPO / "test" / "eval" / "data" / "holdout_eval"

BASE_URL = os.environ.get("API_BASE", "http://localhost:8000")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "4"))
TIMEOUT = 240.0

# Reuse the beverage-type mapper used by the existing audit harness
sys.path.insert(0, str(REPO / "backend"))
from app.samples import _guess_beverage  # noqa: E402


_US_STATES = {
    "DOMESTIC","ALABAMA","ALASKA","ARIZONA","ARKANSAS","CALIFORNIA","COLORADO",
    "CONNECTICUT","DELAWARE","FLORIDA","GEORGIA","HAWAII","IDAHO","ILLINOIS",
    "INDIANA","IOWA","KANSAS","KENTUCKY","LOUISIANA","MAINE","MARYLAND",
    "MASSACHUSETTS","MICHIGAN","MINNESOTA","MISSISSIPPI","MISSOURI","MONTANA",
    "NEBRASKA","NEVADA","NEW HAMPSHIRE","NEW JERSEY","NEW MEXICO","NEW YORK",
    "NORTH CAROLINA","NORTH DAKOTA","OHIO","OKLAHOMA","OREGON","PENNSYLVANIA",
    "PUERTO RICO","RHODE ISLAND","SOUTH CAROLINA","SOUTH DAKOTA","TENNESSEE",
    "TEXAS","UTAH","VERMONT","VIRGINIA","WASHINGTON","WEST VIRGINIA",
    "WISCONSIN","WYOMING",
}


def _norm(s: str) -> str:
    """Tolerant normalization for field comparison."""
    s = (s or "").strip().lower()
    s = re.sub(r"[.,]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def to_application_data(r: dict) -> dict:
    """Map a CSV row to ApplicationData JSON (same shape as audit_ttb_live.py)."""
    bev = _guess_beverage(r)
    origin = (r.get("origin_code") or "").upper()
    data: dict = {
        "colaNumber":         r["ttb_id"],
        "brandName":          r.get("brand_name") or "",
        "classType":          r.get("class_type_description") or r.get("class_type_code") or "",
        "alcoholContent":     "",
        "netContents":        "",
        "bottlerNameAddress": r.get("name_address_applicant") or "",
        "beverageType":       bev,
    }
    if r.get("fanciful_name"):
        data["productName"] = r["fanciful_name"]
    if origin and origin not in _US_STATES:
        data["countryOfOrigin"] = origin.title()
    return data


def bucket_for(result: dict) -> str:
    """Full engine bucket — includes the warning check."""
    statuses = [f["status"] for f in result["fields"]]
    gw = result["governmentWarning"]
    if any(s == "flag" for s in statuses) or not gw["present"] or not gw["verbatimMatch"]:
        return "needs-review"
    if any(s == "likely" for s in statuses):
        return "needs-confirm"
    return "auto-pass"


def bucket_fields_only(result: dict) -> str:
    """Field-only bucket — ignores the warning rule.

    v2 is trained on fields-only targets, so the engine will systematically
    see warning_present=False on its outputs. Including the warning rule in
    bucket-agreement comparisons would penalize v2 for behavior it wasn't
    trained on. This variant isolates "did the field extraction improve?"
    from "did the warning detection regress?" — both are reported.
    """
    statuses = [f["status"] for f in result["fields"]]
    if any(s == "flag" for s in statuses):
        return "needs-review"
    if any(s == "likely" for s in statuses):
        return "needs-confirm"
    return "auto-pass"


def field_matches(result: dict, row: dict) -> dict:
    """Per-field exact-match against TTB form text.

    Returns {field_name: {expected, extracted, match}} for the four
    form-derived fields. Skips fields TTB doesn't carry on Form 5100.31
    (Alcohol content, Net contents) — these aren't gradeable here.
    """
    expected_by_field = {
        "Brand name":           _norm(row.get("brand_name", "")),
        "Class & type":         _norm(row.get("class_type_description", "")),
        "Bottler name/address": _norm(row.get("name_address_applicant", "")),
    }
    origin = (row.get("origin_code") or "").upper()
    if origin and origin not in _US_STATES:
        expected_by_field["Country of origin"] = _norm(origin)

    by_field = {f["fieldName"]: f for f in result["fields"]}
    out = {}
    for name, exp in expected_by_field.items():
        if not exp:
            continue
        f = by_field.get(name)
        extracted = _norm((f or {}).get("labelValue", ""))
        # "match" = both sides equal OR engine reported status=match
        # (engine uses substring/fuzzy logic for some fields, which is
        # closer to human judgment than strict string equality)
        is_match = (extracted == exp) or (f and f.get("status") == "match")
        out[name] = {"expected": exp, "extracted": extracted, "match": bool(is_match)}
    return out


async def verify_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, row: dict) -> dict:
    app_data = to_application_data(row)
    img_path = TTB_IMGS / row["image_filename"]
    img_bytes = img_path.read_bytes()
    t0 = time.perf_counter()
    async with sem:
        try:
            r = await client.post(
                f"{BASE_URL}/api/verify",
                files={"image": (row["image_filename"], img_bytes, "image/jpeg")},
                data={"applicationData": json.dumps(app_data)},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            result = r.json()
        except Exception as e:
            return {
                "ttb_id":   row["ttb_id"],
                "brand":    row.get("brand_name", ""),
                "beverage": app_data["beverageType"],
                "bucket":   "ERROR",
                "error":    str(e),
                "elapsed_s": round(time.perf_counter() - t0, 1),
            }
    elapsed = time.perf_counter() - t0
    return {
        "ttb_id":            row["ttb_id"],
        "brand":             row.get("brand_name", ""),
        "beverage":          app_data["beverageType"],
        "origin":            row.get("origin_code", ""),
        "bucket":            bucket_for(result),
        "bucket_fields_only": bucket_fields_only(result),
        "expected_bucket":   "auto-pass",   # all holdout = TTB-approved
        "fields":            field_matches(result, row),
        "gw_present":        result["governmentWarning"]["present"],
        "gw_verbatim":       result["governmentWarning"]["verbatimMatch"],
        "elapsed_s":         round(elapsed, 2),
    }


def summarize(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0}
    buckets = {b: sum(1 for r in results if r["bucket"] == b)
               for b in ("auto-pass", "needs-confirm", "needs-review", "ERROR")}
    buckets_fo = {b: sum(1 for r in results if r.get("bucket_fields_only") == b)
                  for b in ("auto-pass", "needs-confirm", "needs-review")}
    # Per-field accuracy
    per_field_total: dict[str, int] = {}
    per_field_match: dict[str, int] = {}
    for r in results:
        for fname, fres in (r.get("fields") or {}).items():
            per_field_total[fname] = per_field_total.get(fname, 0) + 1
            if fres["match"]:
                per_field_match[fname] = per_field_match.get(fname, 0) + 1
    per_field_acc = {
        fname: round(per_field_match.get(fname, 0) / per_field_total[fname], 4)
        for fname in per_field_total
    }
    # Aggregate field accuracy (micro-average across all field instances)
    total_fields = sum(per_field_total.values())
    total_matches = sum(per_field_match.values())
    micro_field_acc = round(total_matches / total_fields, 4) if total_fields else 0

    elapsed = [r["elapsed_s"] for r in results if "elapsed_s" in r and r.get("bucket") != "ERROR"]
    elapsed.sort()
    latency_mean = round(sum(elapsed) / len(elapsed), 2) if elapsed else None
    latency_p95  = elapsed[int(0.95 * len(elapsed))] if elapsed else None

    return {
        "n":                              n,
        "buckets":                        buckets,
        "buckets_fields_only":            buckets_fo,
        "auto_pass_rate":                 round(buckets["auto-pass"] / n, 4),
        "bucket_agreement_vs_ttb":        round(buckets["auto-pass"] / n, 4),  # full engine, w/ warning rule
        "bucket_agreement_fields_only":   round(buckets_fo["auto-pass"] / n, 4),  # ignores warning rule
        "per_field_accuracy":             per_field_acc,
        "micro_field_accuracy":           micro_field_acc,
        "warning_present_rate":           round(sum(1 for r in results if r.get("gw_present")) / n, 4),
        "warning_verbatim_rate":          round(sum(1 for r in results if r.get("gw_verbatim")) / n, 4),
        "latency_mean":                   latency_mean,
        "latency_p95":                    latency_p95,
    }


async def main_async(tag: str) -> int:
    if not HOLDOUT_TXT.exists():
        print(f"missing {HOLDOUT_TXT}; run holdout_split.py first", file=sys.stderr)
        return 1
    if not TTB_CSV.exists():
        print(f"missing {TTB_CSV}", file=sys.stderr)
        return 1

    holdout = {l.strip() for l in HOLDOUT_TXT.read_text().splitlines() if l.strip()}
    print(f"[init] {len(holdout)} ttb_ids in holdout list")

    all_rows = list(csv.DictReader(open(TTB_CSV)))
    rows = [r for r in all_rows
            if r["ttb_id"] in holdout
            and r.get("image_filename")
            and (TTB_IMGS / r["image_filename"]).exists()]
    print(f"[init] {len(rows)} rows ready (image present)")

    async with httpx.AsyncClient() as client:
        try:
            h = await client.get(f"{BASE_URL}/health", timeout=5.0)
            print(f"[init] backend: {h.json()}")
        except Exception as e:
            print(f"[init] backend unreachable at {BASE_URL}: {e}", file=sys.stderr)
            return 1

    sem = asyncio.Semaphore(CONCURRENCY)
    results: list[dict] = []
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        pending = [asyncio.create_task(verify_one(client, sem, r)) for r in rows]
        done = 0
        for coro in asyncio.as_completed(pending):
            r = await coro
            results.append(r)
            done += 1
            print(f"  [{done:>4}/{len(rows)}] {r.get('brand','')[:25]:25} "
                  f"bucket={r.get('bucket','?'):14} ({r.get('elapsed_s', '?')}s)", flush=True)
    total = time.perf_counter() - t0
    print(f"\n[done] {len(results)} verified in {total:.0f}s")

    summary = summarize(results)
    summary["tag"] = tag
    summary["backend_url"] = BASE_URL
    summary["wall_time_s"] = round(total, 1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"{tag}_report.json"
    md_path   = OUT_DIR / f"{tag}_report.md"
    json_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2))

    md = [
        f"# Holdout eval — {tag}",
        f"",
        f"Backend: `{BASE_URL}`  |  N={summary['n']}  |  wall: {summary['wall_time_s']}s",
        f"",
        f"## Headline",
        f"",
        f"- **bucket agreement vs TTB (full engine, incl. warning)**: {summary['bucket_agreement_vs_ttb']:.1%}",
        f"- **bucket agreement vs TTB (fields-only, ignores warning)**: {summary['bucket_agreement_fields_only']:.1%}",
        f"- **micro field accuracy**: {summary['micro_field_accuracy']:.1%}",
        f"- latency: mean {summary['latency_mean']}s, p95 {summary['latency_p95']}s",
        f"",
        f"## Per-field accuracy",
        f"",
        f"| Field | Accuracy | N |",
        f"|---|---|---|",
    ]
    for fname, acc in sorted(summary["per_field_accuracy"].items()):
        n_field = sum(1 for r in results if fname in (r.get("fields") or {}))
        md.append(f"| {fname} | {acc:.1%} | {n_field} |")
    md.append("")
    md.append("## Bucket distribution")
    md.append("")
    md.append("| Bucket | Count |")
    md.append("|---|---|")
    for b, c in summary["buckets"].items():
        md.append(f"| {b} | {c} |")
    md_path.write_text("\n".join(md) + "\n")
    print(f"wrote {json_path.relative_to(REPO)}")
    print(f"wrote {md_path.relative_to(REPO)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--report-tag", required=True,
                   help="Tag identifying the extractor under test (e.g. haiku, qwen_v1, qwen_v2). "
                        "Used in output filenames; pick descriptive ones.")
    args = p.parse_args()
    return asyncio.run(main_async(args.report_tag))


if __name__ == "__main__":
    sys.exit(main())
