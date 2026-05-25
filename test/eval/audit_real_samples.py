"""Audit every clean real label from cola_sample.csv against the live backend.

Reads the CSV, filters to rows whose brand/class are well-formed and image
file exists, then hits POST /api/verify per row with bounded concurrency.
Writes:
  - test/eval/real_audit.json   (per-row machine-readable)
  - test/eval/REAL_AUDIT.md     (human-readable summary table)

Usage:
  make serve                    # backend must be running on :8000
  backend/.venv/bin/python test/eval/audit_real_samples.py
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
CSV  = REPO / "test" / "eval" / "data" / "cola_sample.csv"
IMG  = REPO / "test" / "eval" / "data" / "images"
OUT_JSON = REPO / "test" / "eval" / "real_audit.json"
OUT_MD   = REPO / "test" / "eval" / "REAL_AUDIT.md"

BASE_URL = os.environ.get("API_BASE", "http://localhost:8000")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "4"))
TIMEOUT = 240.0


def clean_row(r: dict) -> bool:
    bad = lambda s: not s or len(s) > 50 or any(c in s for c in "(/.")
    if bad(r["brand_name"]) or bad(r["class_type"]):
        return False
    if r.get("mutation"):
        return False
    return (IMG / r["image_filename"]).exists()


sys.path.insert(0, str(REPO / "backend"))
from app.ocr_bottler import extract_bottler  # noqa: E402


def to_application_data(r: dict) -> dict:
    """Map a CSV row to the ApplicationData JSON the backend accepts.

    Bottler stays empty when the CSV row has it empty. We tried
    synthesizing it from OCR text but that worsened the engine
    agreement rate (different OCRs of the same label diverge). The
    honest behavior is empty → engine returns match with the label
    content shown for agent review.
    """
    bev = r["beverage_type"]
    bottler = r.get("bottler_name_address") or ""
    data = {
        "colaNumber": r["ttb_id"],
        "brandName": r["brand_name"],
        "classType": r["class_type"],
        "alcoholContent": r.get("alcohol_content") or "",
        "netContents": r.get("net_contents") or "",
        "bottlerNameAddress": bottler,
        "beverageType": bev,
    }
    if r.get("product_name"):
        data["productName"] = r["product_name"]
    if r.get("origin"):
        data["countryOfOrigin"] = r["origin"].title()
    return data


def bucket_for(result: dict) -> str:
    """Mirror group_for() in backend/app/models.py."""
    statuses = [f["status"] for f in result["fields"]]
    gw = result["governmentWarning"]
    has_flag = (
        any(s == "flag" for s in statuses)
        or not gw["present"]
        or not gw["verbatimMatch"]
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
                files={"image": (row["image_filename"], img_bytes, "image/webp")},
                data={"applicationData": json.dumps(app_data)},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            result = r.json()
        except Exception as e:
            return {
                "ttb_id": row["ttb_id"],
                "brand": row["brand_name"],
                "beverage": row["beverage_type"],
                "import": row["domestic_or_imported"],
                "expected": row["expected_outcome"],
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
        "beverage": row["beverage_type"],
        "import": row["domestic_or_imported"],
        "expected": row["expected_outcome"],
        "engine_verdict": bucket_for(result),
        "field_counts": counts,
        "gw_present": gw["present"],
        "gw_verbatim": gw["verbatimMatch"],
        "gw_casing": gw["casingBoldOk"],
        "image_filename": row["image_filename"],
        "elapsed_s": round(elapsed, 1),
    }


async def main() -> int:
    with open(CSV) as f:
        rows = list(csv.DictReader(f))
    clean = [r for r in rows if clean_row(r)]

    # Resume support: if a previous audit JSON exists, skip rows whose
    # ttb_id is already in it (so we can run incrementally if interrupted).
    already_done: dict[str, dict] = {}
    if OUT_JSON.exists():
        try:
            prev = json.loads(OUT_JSON.read_text())
            for r in prev.get("results", []):
                if r.get("engine_verdict") != "ERROR":
                    already_done[r["ttb_id"]] = r
        except Exception:
            pass

    to_run = [r for r in clean if r["ttb_id"] not in already_done]
    print(f"CSV total: {len(rows)}, clean: {len(clean)}, already done: {len(already_done)}, to run: {len(to_run)}", flush=True)

    # Health check
    async with httpx.AsyncClient() as client:
        try:
            h = await client.get(f"{BASE_URL}/health", timeout=5.0)
            print(f"backend health: {h.json()}", flush=True)
        except Exception as e:
            print(f"backend unreachable at {BASE_URL}: {e}", file=sys.stderr)
            return 1

    sem = asyncio.Semaphore(CONCURRENCY)
    results: list[dict] = list(already_done.values())
    started = time.perf_counter()

    def _checkpoint() -> None:
        """Write partial results to disk so an interruption doesn't lose them."""
        OUT_JSON.write_text(json.dumps({"summary": {}, "results": results}, indent=2))

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        pending = [asyncio.create_task(verify_one(client, sem, r)) for r in to_run]
        done = 0
        for coro in asyncio.as_completed(pending):
            r = await coro
            results.append(r)
            done += 1
            print(
                f"  [{done:>3}/{len(to_run)}] {r['brand'][:25]:25} "
                f"expected={r['expected']:13} engine={r.get('engine_verdict', '?'):14} "
                f"({r['elapsed_s']}s)",
                flush=True,
            )
            # Checkpoint every 5 to survive interruptions
            if done % 5 == 0:
                _checkpoint()

    total_s = time.perf_counter() - started
    print(f"\nDone in {total_s:.0f}s ({total_s/60:.1f} min)", flush=True)

    # ── Summarize ────────────────────────────────────────────────────────────
    results.sort(key=lambda x: (x["beverage"], x["brand"]))
    summary = {
        "total": len(results),
        "by_expected": {},
        "by_engine": {},
        "agreement_matrix": {},
        "errors": [r for r in results if r["engine_verdict"] == "ERROR"],
    }
    for r in results:
        summary["by_expected"][r["expected"]] = summary["by_expected"].get(r["expected"], 0) + 1
        summary["by_engine"][r["engine_verdict"]] = summary["by_engine"].get(r["engine_verdict"], 0) + 1
        key = (r["expected"], r["engine_verdict"])
        summary["agreement_matrix"][f"{key[0]}|{key[1]}"] = (
            summary["agreement_matrix"].get(f"{key[0]}|{key[1]}", 0) + 1
        )

    OUT_JSON.write_text(json.dumps({"summary": summary, "results": results}, indent=2))

    # Markdown
    md = []
    md.append("# Real-data audit — every clean COLA Cloud sample\n")
    md.append(f"Generated against {BASE_URL} (claude-code mode). "
              f"{summary['total']} samples processed in {total_s/60:.1f} min.\n")
    md.append("## Summary\n")
    md.append("**By expected (TTB ground truth):**\n")
    for k, v in sorted(summary["by_expected"].items()):
        md.append(f"- `{k}`: {v}")
    md.append("\n**By engine verdict:**\n")
    for k, v in sorted(summary["by_engine"].items()):
        md.append(f"- `{k}`: {v}")
    md.append("\n**Agreement matrix (expected → engine):**\n")
    md.append("| Expected | Engine | Count |")
    md.append("|---|---|---|")
    for k, v in sorted(summary["agreement_matrix"].items()):
        e, en = k.split("|")
        md.append(f"| {e} | {en} | {v} |")
    md.append("\n## Per-row results\n")
    md.append("| Brand | Beverage | Import | Expected | Engine | M/L/F | GW | Latency |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        c = r.get("field_counts", {})
        gw = f"p={int(r.get('gw_present', False))}/v={int(r.get('gw_verbatim', False))}/c={int(r.get('gw_casing', False))}"
        m_l_f = f"{c.get('match', 0)}/{c.get('likely', 0)}/{c.get('flag', 0)}" if c else "-"
        agreement = "✓" if r["expected"] == r["engine_verdict"] else "~"
        md.append(
            f"| {r['brand'][:30]} | {r['beverage']} | {r['import']} | {r['expected']} | "
            f"**{r['engine_verdict']}** {agreement} | {m_l_f} | {gw} | {r['elapsed_s']}s |"
        )
    OUT_MD.write_text("\n".join(md) + "\n")
    print(f"\nWrote {OUT_JSON.relative_to(REPO)} and {OUT_MD.relative_to(REPO)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
