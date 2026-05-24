#!/usr/bin/env python3
"""End-to-end SFT-vs-Claude scoring — replay edition.

Generic over any model whose Colab eval notebook produces a {model}_outputs.jsonl-
style fixture (per-image raw_output + parsed_output). Currently used for:
  - Qwen2.5-VL-7B LoRA   (notebooks/eval_qwen_drive.ipynb)
  - InternVL3-2B LoRA    (notebooks/eval_internvl3_drive.ipynb)
  - Donut v2 full FT     (notebooks/eval_donut_drive.ipynb)


Runs the same rules engine + same metrics + same ground truth as
test/eval/run_eval.py, but feeds the extractor with pre-recorded Qwen
outputs from a JSONL fixture (produced by any of the eval notebooks listed above).

This sidesteps having to host the 7B Qwen model locally for inference.
We do the heavy GPU inference once on Colab, save the outputs, then
score them through the local rules engine — getting the same
test/eval/report.json shape as Claude so the comparison is byte-for-byte.

Usage:
  python test/eval/replay_qwen.py \\
      --jsonl   ~/Downloads/qwen_outputs.jsonl \\
      --csv     test/eval/data/cola_sample.csv \\
      --out     test/eval/qwen_report.json

Compare to test/eval/report.json (Claude's report on the same images):
  python test/eval/replay_qwen.py --compare test/eval/report.json
"""

from __future__ import annotations

import argparse
import csv as _csv
import json
import os
import statistics
import sys
from pathlib import Path

# Make backend importable
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.extractors.sft import _try_parse_json, _to_extracted_label
from app.models import ApplicationData
from app.rules.engine import verify as engine_verify

# Reuse scoring helpers from run_eval so the metric definitions are IDENTICAL.
sys.path.insert(0, str(REPO_ROOT / "test" / "eval"))
from run_eval import (  # type: ignore  # noqa: E402
    COL,
    derive_beverage,
    fields_match_loose,
    _abv_percent,
    group_for,
    is_auto_pass,
)


def _verification_to_dict(result) -> dict:
    """Match the shape /api/verify returns so the scoring helpers
    (group_for, is_auto_pass) work unchanged."""
    return result.model_dump(by_alias=True, mode="json")


def _load_qwen_outputs(jsonl_path: Path) -> dict[str, dict]:
    """JSONL rows look like:
        {"image_filename": "25240001000020_0.webp",
         "ttb_image_id":   "25240001000020_0",
         "raw_output":     "{...full Qwen JSON text...}",
         "parsed_output":  {...parsed dict, or null...}}
    Returns: filename → parsed dict (None if Qwen output was unparseable).
    """
    out: dict[str, dict | None] = {}
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = rec.get("image_filename") or (rec.get("ttb_image_id", "") + ".webp")
            parsed = rec.get("parsed_output")
            if parsed is None:
                # Fall back to re-parsing raw_output server-side using the same
                # best-effort parser the live extractor uses.
                parsed = _try_parse_json(rec.get("raw_output", ""))
            out[key] = parsed
    return out


LABEL = "sft"   # overwritten by main() from --label


def replay(jsonl_path: Path, csv_path: Path) -> dict:
    qwen_outputs = _load_qwen_outputs(jsonl_path)
    print(f"Loaded {len(qwen_outputs)} Qwen outputs from {jsonl_path}")

    rows = list(_csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    print(f"Loaded {len(rows)} ground-truth rows from {csv_path}")

    misses: list[dict] = []
    latencies: list[float] = []
    # Pull latencies from the raw JSONL records so the report has mean/p95
    # for the SFT model (the values were captured during Colab extraction).
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            rec = json.loads(line)
            if "latency_sec" in rec and rec["latency_sec"] is not None:
                latencies.append(float(rec["latency_sec"]))
    auto_pass_approved = 0
    warn_false_flag_approved = 0
    field_total = field_correct = 0
    verdict_total = verdict_correct = 0
    approved_n = 0
    processed_n = 0
    missing_extraction = 0
    unparseable = 0

    for row in rows:
        img = row.get(COL["image"], "").strip()
        if not img:
            continue

        parsed = qwen_outputs.get(img)
        if parsed is None:
            # Either Qwen didn't produce output for this image, or its
            # output was unparseable. Distinguish in misses.
            if img not in qwen_outputs:
                missing_extraction += 1
                misses.append({"image": img, "error": "no Qwen extraction in JSONL"})
            else:
                unparseable += 1
                misses.append({"image": img, "error": "Qwen output unparseable as JSON"})
            continue

        # Build the ApplicationData the rules engine expects
        app = ApplicationData(
            brandName=row.get(COL["brand"], ""),
            productName=row.get(COL["product"]) or None,
            classType=row.get(COL["class_type"], ""),
            alcoholContent=row.get(COL["alcohol"], ""),
            netContents=row.get(COL["net_contents"], ""),
            bottlerNameAddress=row.get(COL["bottler"], ""),
            countryOfOrigin=row.get(COL["origin"]) or None,
            beverageType=derive_beverage(row),
        )

        # Build the ExtractedLabel the engine expects
        extracted = _to_extracted_label(parsed)

        # Run the rules engine
        result_obj = engine_verify(extracted=extracted, app=app)
        result = _verification_to_dict(result_obj)
        processed_n += 1

        # Per-field scoring — IDENTICAL to run_eval.py logic
        product = row.get(COL["product"], "")
        for fld in result.get("fields", []):
            declared = (fld.get("declaredValue") or "").strip()
            extracted_val = (fld.get("extractedValue") or "").strip()
            field_name = fld.get("fieldName", "")
            if not declared:
                continue  # COLA form omitted — skip
            field_total += 1

            ok = fields_match_loose(declared, extracted_val, field_name=field_name)
            if not ok and "brand" in field_name.lower() and product:
                ok = fields_match_loose(product, extracted_val, field_name=field_name)
            if not ok and "alcohol" in field_name.lower():
                pd, pe = _abv_percent(declared), _abv_percent(extracted_val)
                if pd is not None and pe is not None and abs(pd - pe) <= 0.1:
                    ok = True

            if ok:
                field_correct += 1
            else:
                misses.append({
                    "image": img,
                    "field": field_name,
                    "expected": declared, "got": extracted_val,
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

    return {
        "mode": f"{LABEL}_replay",
        "n": processed_n,
        "approved_n": approved_n,
        "field_extraction_accuracy": round(field_correct / field_total, 4) if field_total else None,
        "field_total": field_total, "field_correct": field_correct,
        "verdict_accuracy": round(verdict_correct / verdict_total, 4) if verdict_total else None,
        "auto_pass_rate_approved": round(auto_pass_approved / approved_n, 4) if approved_n else None,
        "warning_false_flag_rate": round(warn_false_flag_approved / approved_n, 4) if approved_n else None,
        "latency_mean": round(statistics.mean(latencies), 3) if latencies else None,
        "latency_p95": round(sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)], 3) if latencies else None,
        "sft_extraction_missing_count": missing_extraction,
        "sft_output_unparseable_count": unparseable,
        "sft_empty_fields_count": sum(
            1 for r in qwen_outputs.values()
            if r and isinstance(r.get("fields"), dict) and not r["fields"]
        ),
        "misses": misses[:50],   # cap to keep the report readable
    }


def _print_side_by_side(qwen: dict, claude_path: Path) -> None:
    if not claude_path.exists():
        print(f"\n(skipping side-by-side: {claude_path} not found)")
        return
    claude = json.loads(claude_path.read_text())

    def fmt(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.2%}" if v < 1 else f"{v:.3f}"
        return str(v)

    rows = [
        ("test set size",                "n",                          1),
        ("approved labels in test set",  "approved_n",                 1),
        ("field extraction accuracy",    "field_extraction_accuracy",  1),
        ("end-to-end verdict accuracy",  "verdict_accuracy",           1),
        ("auto-pass rate on approved",   "auto_pass_rate_approved",    1),
        ("warning false-flag rate",      "warning_false_flag_rate",   -1),  # lower is better
        ("latency mean (s)",             "latency_mean",              -1),
        ("latency p95 (s)",              "latency_p95",               -1),
    ]
    print()
    print("=" * 80)
    qlabel = LABEL.capitalize()
    print(f"{'Metric':<32} {'Claude':>12} {qlabel:>12}   {'Δ (' + qlabel + ' − Claude)':>20}")
    print("-" * 80)
    for label, key, direction in rows:
        c, q = claude.get(key), qwen.get(key)
        delta = ""
        if isinstance(c, (int, float)) and isinstance(q, (int, float)):
            d = q - c
            arrow = ""
            if abs(d) > 1e-6:
                if (direction > 0 and d > 0) or (direction < 0 and d < 0):
                    arrow = " ↑"
                else:
                    arrow = " ↓"
            delta = f"{d:+.4f}{arrow}"
        print(f"{label:<32} {fmt(c):>12} {fmt(q):>12}   {delta:>20}")
    print("=" * 80)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="sft",
                    help="Label for this model in the report (e.g. qwen, internvl3, donut)")
    ap.add_argument("--jsonl", required=True,
                    help="JSONL of model outputs from a Colab eval notebook")
    ap.add_argument("--csv",   default=str(REPO_ROOT / "test" / "eval" / "data" / "cola_sample.csv"),
                    help="Ground-truth CSV (same one run_eval.py uses)")
    ap.add_argument("--out", required=True,
                    help="Write the report here (same shape as test/eval/report.json)")
    ap.add_argument("--compare", default=str(REPO_ROOT / "test" / "eval" / "report.json"),
                    help="Existing Claude report to side-by-side against")
    args = ap.parse_args()

    jsonl = Path(args.jsonl).expanduser()
    if not jsonl.exists():
        print(f"ERROR: --jsonl not found: {jsonl}", file=sys.stderr)
        print("Run notebooks/eval_qwen_drive.ipynb in Colab first;")
        print("it downloads qwen_outputs.jsonl to ~/Downloads.")
        return 1

    global LABEL
    LABEL = args.label
    report = replay(jsonl, Path(args.csv))
    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")

    _print_side_by_side(report, Path(args.compare))
    return 0


if __name__ == "__main__":
    sys.exit(main())
