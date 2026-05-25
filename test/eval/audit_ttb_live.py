"""Run the engine agreement audit on the TTB-live tier.

Same as audit_real_samples.py but reads from ttb_live.csv (scraped via
scrape_ttb_registry.py) instead of the COLA Cloud sample. Writes:
  - test/eval/ttb_live_audit.json
  - test/eval/TTB_LIVE_AUDIT.md
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
CSV  = REPO / "test" / "eval" / "data" / "ttb_live" / "ttb_live.csv"
IMG  = REPO / "test" / "eval" / "data" / "ttb_live" / "images"
OUT_JSON = REPO / "test" / "eval" / "ttb_live_audit.json"
OUT_MD   = REPO / "test" / "eval" / "TTB_LIVE_AUDIT.md"

BASE_URL = os.environ.get("API_BASE", "http://localhost:8000")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "4"))
TIMEOUT = 240.0

# Reuse the beverage-type mapping from samples.py
sys.path.insert(0, str(REPO / "backend"))
from app.samples import _guess_beverage  # noqa: E402


def to_application_data(r: dict) -> dict:
    """Map a scraped TTB-live row to ApplicationData JSON."""
    origin_us_states = {
        "DOMESTIC", "ALABAMA", "ALASKA", "ARIZONA", "ARKANSAS", "CALIFORNIA",
        "COLORADO", "CONNECTICUT", "DELAWARE", "FLORIDA", "GEORGIA", "HAWAII",
        "IDAHO", "ILLINOIS", "INDIANA", "IOWA", "KANSAS", "KENTUCKY",
        "LOUISIANA", "MAINE", "MARYLAND", "MASSACHUSETTS", "MICHIGAN",
        "MINNESOTA", "MISSISSIPPI", "MISSOURI", "MONTANA", "NEBRASKA",
        "NEVADA", "NEW HAMPSHIRE", "NEW JERSEY", "NEW MEXICO", "NEW YORK",
        "NORTH CAROLINA", "NORTH DAKOTA", "OHIO", "OKLAHOMA", "OREGON",
        "PENNSYLVANIA", "PUERTO RICO", "RHODE ISLAND", "SOUTH CAROLINA",
        "SOUTH DAKOTA", "TENNESSEE", "TEXAS", "UTAH", "VERMONT", "VIRGINIA",
        "WASHINGTON", "WEST VIRGINIA", "WISCONSIN", "WYOMING",
    }
    bev = _guess_beverage(r)
    origin = (r.get("origin_code") or "").upper()
    data = {
        "colaNumber": r["ttb_id"],
        "brandName": r.get("brand_name") or "",
        "classType": r.get("class_type_description") or r.get("class_type_code") or "",
        "alcoholContent": "",  # TTB form doesn't carry; on label only
        "netContents": "",
        "bottlerNameAddress": r.get("name_address_applicant") or "",
        "beverageType": bev,
    }
    if r.get("fanciful_name"):
        data["productName"] = r["fanciful_name"]
    if origin and origin not in origin_us_states:
        data["countryOfOrigin"] = origin.title()
    return data


def bucket_for(result: dict) -> str:
    statuses = [f["status"] for f in result["fields"]]
    gw = result["governmentWarning"]
    has_flag = (
        any(s == "flag" for s in statuses)
        or not gw["present"] or not gw["verbatimMatch"]
    )
    has_likely = any(s == "likely" for s in statuses)
    if has_flag:
        return "needs-review"
    if has_likely:
        return "needs-confirm"
    return "auto-pass"


async def verify_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, row: dict) -> dict:
    app_data = to_application_data(row)
    img_path = IMG / row["image_filename"]
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
                "ttb_id": row["ttb_id"],
                "brand": row["brand_name"],
                "engine_verdict": "ERROR",
                "error": str(e),
                "elapsed_s": round(time.perf_counter() - t0, 1),
            }
    elapsed = time.perf_counter() - t0
    statuses = [f["status"] for f in result["fields"]]
    counts = {k: statuses.count(k) for k in ("match", "likely", "flag")}
    gw = result["governmentWarning"]
    return {
        "ttb_id": row["ttb_id"],
        "brand": row["brand_name"],
        "beverage": app_data["beverageType"],
        "origin": row.get("origin_code", ""),
        "status": row.get("status", ""),
        # TTB ground truth: all approved labels in this set are "auto-pass"
        # by definition (TTB issued the certificate). EXPIRED / SURRENDERED
        # mean the certificate is no longer valid but the label was
        # approved at issuance.
        "expected": "auto-pass",
        "engine_verdict": bucket_for(result),
        "field_counts": counts,
        "gw_present": gw["present"],
        "gw_verbatim": gw["verbatimMatch"],
        "gw_casing": gw["casingBoldOk"],
        "image_filename": row["image_filename"],
        "image_dpi": row.get("image_dpi", ""),
        "elapsed_s": round(elapsed, 1),
    }


async def main() -> int:
    if not CSV.exists():
        print(f"No scraped data at {CSV}. Run 'make scrape-ttb' first.", file=sys.stderr)
        return 1
    with open(CSV) as f:
        rows = [r for r in csv.DictReader(f) if r.get("image_filename")]
    print(f"{len(rows)} TTB-live rows; backend at {BASE_URL}", flush=True)

    async with httpx.AsyncClient() as client:
        try:
            h = await client.get(f"{BASE_URL}/health", timeout=5.0)
            print(f"backend: {h.json()}", flush=True)
        except Exception as e:
            print(f"backend unreachable: {e}", file=sys.stderr)
            return 1

    sem = asyncio.Semaphore(CONCURRENCY)
    results: list[dict] = []
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        pending = [asyncio.create_task(verify_one(client, sem, r)) for r in rows]
        done = 0
        for coro in asyncio.as_completed(pending):
            r = await coro
            results.append(r)
            done += 1
            print(
                f"  [{done:>3}/{len(rows)}] {r['brand'][:25]:25} "
                f"engine={r.get('engine_verdict', '?'):14} ({r['elapsed_s']}s)",
                flush=True,
            )
    total = time.perf_counter() - started
    print(f"\nDone in {total:.0f}s", flush=True)

    # ── Summarize ─────────────────────────────────────────────────────────
    results.sort(key=lambda x: x.get("brand", ""))
    by_engine: dict[str, int] = {}
    for r in results:
        by_engine[r["engine_verdict"]] = by_engine.get(r["engine_verdict"], 0) + 1
    auto_pass_rate = by_engine.get("auto-pass", 0) / len(results) if results else 0
    review_rate = by_engine.get("needs-review", 0) / len(results) if results else 0

    summary = {
        "total": len(results),
        "auto_pass_rate": auto_pass_rate,
        "review_rate": review_rate,
        "by_engine": by_engine,
    }
    OUT_JSON.write_text(json.dumps({"summary": summary, "results": results}, indent=2))

    md = ["# TTB-live audit — engine on real Form 5100.31 data\n"]
    md.append(f"Generated against {BASE_URL}. {len(results)} samples in {total:.0f}s.\n")
    md.append("## Headline\n")
    md.append(f"- **auto-pass rate**: {auto_pass_rate:.0%} ({by_engine.get('auto-pass', 0)} of {len(results)})")
    md.append(f"- **needs-review rate**: {review_rate:.0%} ({by_engine.get('needs-review', 0)} of {len(results)})")
    md.append(f"- needs-confirm: {by_engine.get('needs-confirm', 0)}")
    md.append(f"- errors: {by_engine.get('ERROR', 0)}\n")
    md.append("All TTB-approved labels are by definition \"auto-pass\" ground truth — "
              "this is the **engine's false-flag rate on real filed application data**.\n")
    md.append("\n## Per-row results\n")
    md.append("| Brand | Beverage | Origin | Engine | M/L/F | GW | DPI | Latency |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        c = r.get("field_counts", {})
        gw = f"p={int(r.get('gw_present', False))}/v={int(r.get('gw_verbatim', False))}/c={int(r.get('gw_casing', False))}"
        mlf = f"{c.get('match', 0)}/{c.get('likely', 0)}/{c.get('flag', 0)}" if c else "-"
        md.append(
            f"| {r['brand'][:30]} | {r.get('beverage', '?')} | {r.get('origin', '?')} | "
            f"**{r['engine_verdict']}** | {mlf} | {gw} | {r.get('image_dpi', '-')} | {r['elapsed_s']}s |"
        )
    OUT_MD.write_text("\n".join(md) + "\n")
    print(f"\nWrote {OUT_MD.relative_to(REPO)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
