"""Build Qwen2.5-VL SFT training JSONL from the TTB-live scrape.

Ground truth for the FIELD portion of each training example comes
directly from the TTB Form 5100.31 (test/eval/data/ttb_live/ttb_live.csv):
  brand_name              -> "Brand name"
  class_type_description  -> "Class & type"
  name_address_applicant  -> "Bottler name/address"
  origin_code (if non-US) -> "Country of origin"

These four fields are the only ones with structured ground truth on the
TTB form. Alcohol content, Net contents, and the Government Warning are
NOT carried on the form — they're verified visually on the label image.

The user's design call: train v2 to extract ONLY the fields the form
gives us ground truth for. Don't pollute supervision with model-derived
targets (would just teach the LoRA the upstream model's blind spots).

  --warning-source {none, haiku}
    none      target omits government_warning entirely (default)
    haiku     pull government_warning + image_quality from a prior
              audit run (test/eval/ttb_live_audit.json). Use this only
              if you decide field-only targets degrade bucket agreement
              at eval time and want a warning-supervision pass.

Output layout (paths relative to repo root):
  test/eval/data/qwen_sft/
    train.jsonl
    val.jsonl
    manifest.json     {n_train, n_val, source_csv_rows, warning_source, ...}

Each JSONL line:
  {
    "ttb_id":        "26104001000381",
    "image_path":    "test/eval/data/ttb_live/images/26104001000381.jpg",
    "beverage_type": "wine",
    "target": { "fields": { ... }, ... }
  }

Usage:
  python test/eval/build_qwen_jsonl.py
  python test/eval/build_qwen_jsonl.py --warning-source haiku --val-frac 0.1
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TTB_CSV  = REPO / "test" / "eval" / "data" / "ttb_live" / "ttb_live.csv"
TTB_IMGS = REPO / "test" / "eval" / "data" / "ttb_live" / "images"
HAIKU_JSON = REPO / "test" / "eval" / "ttb_live_audit.json"
OUT_DIR  = REPO / "test" / "eval" / "data" / "qwen_sft"
HOLDOUT_TXT = REPO / "test" / "eval" / "data" / "ttb_live_test" / "holdout_ttbids.txt"

# US states + territories. origin_code = one of these means a US label
# (no "Country of origin" field); anything else is treated as the country.
_US_REGIONS = {
    "ALABAMA","ALASKA","ARIZONA","ARKANSAS","CALIFORNIA","COLORADO","CONNECTICUT",
    "DELAWARE","FLORIDA","GEORGIA","HAWAII","IDAHO","ILLINOIS","INDIANA","IOWA",
    "KANSAS","KENTUCKY","LOUISIANA","MAINE","MARYLAND","MASSACHUSETTS","MICHIGAN",
    "MINNESOTA","MISSISSIPPI","MISSOURI","MONTANA","NEBRASKA","NEVADA",
    "NEW HAMPSHIRE","NEW JERSEY","NEW MEXICO","NEW YORK","NORTH CAROLINA",
    "NORTH DAKOTA","OHIO","OKLAHOMA","OREGON","PENNSYLVANIA","RHODE ISLAND",
    "SOUTH CAROLINA","SOUTH DAKOTA","TENNESSEE","TEXAS","UTAH","VERMONT",
    "VIRGINIA","WASHINGTON","WEST VIRGINIA","WISCONSIN","WYOMING",
    "DISTRICT OF COLUMBIA","PUERTO RICO","US VIRGIN ISLANDS","GUAM",
    "AMERICAN SAMOA","NORTHERN MARIANA ISLANDS",
    # Multi-state designations TTB uses
    "MULTI-STATE","UNITED STATES",
}


def _derive_beverage(row: dict) -> str:
    """Map class_type_description -> beverage_type tag used in the prompt.

    Matches backend/app/rules/engine.py groupFor() and the existing v1
    notebook's _derive_beverage so eval is apples-to-apples.
    """
    desc = (row.get("class_type_description") or "").lower()
    # Beer / malt — explicit keywords win even when wine words also appear
    # (e.g. "wine cooler" is a malt beverage).
    if any(k in desc for k in ("beer", "ale", "malt", "stout", "porter", "lager")):
        return "malt"
    # Spirits — broad coverage of distilled categories
    if any(k in desc for k in (
        "whisky","whiskey","bourbon","rye","scotch","vodka","gin","rum",
        "brandy","tequila","mezcal","cordial","liqueur","cocktail","spirit",
        "schnapps","aquavit","absinthe","grappa","cognac","agave","bitters",
    )):
        return "spirits"
    # Wine — sake too (TTB regulates as wine)
    if any(k in desc for k in ("wine","sake","cider","mead","champagne","port","sherry","vermouth")):
        return "wine"
    return "wine"  # safe default; wine is the largest single bucket on TTB


def _clean_field(s: str) -> str:
    """Tidy whitespace + drop trailing parenthetical TTB notes."""
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    # Drop trailing "(Used on label)" / "(Required)" annotations
    s = re.sub(r"\s*\((?:Used on label|Required)\)\s*$", "", s, flags=re.IGNORECASE)
    return s


def _build_fields(row: dict) -> dict:
    """Build the {field_name: {value, confidence}} dict from form data."""
    fields: dict[str, dict] = {}

    brand = _clean_field(row.get("brand_name", ""))
    if brand:
        fields["Brand name"] = {"value": brand, "confidence": 1.0}

    cls = _clean_field(row.get("class_type_description", ""))
    if cls:
        fields["Class & type"] = {"value": cls, "confidence": 1.0}

    bottler = _clean_field(row.get("name_address_applicant", ""))
    if bottler:
        fields["Bottler name/address"] = {"value": bottler, "confidence": 1.0}

    origin = _clean_field(row.get("origin_code", "")).upper()
    if origin and origin not in _US_REGIONS:
        fields["Country of origin"] = {"value": origin.title(), "confidence": 1.0}

    return fields


def _load_haiku_warnings() -> dict[str, dict]:
    """Index Haiku-extracted warning + image_quality blocks by ttb_id.

    Expects test/eval/ttb_live_audit.json (produced by audit_ttb_live.py).
    Each row in that file has ttb_id + extracted_label.{warning_*, image_*}.
    """
    if not HAIKU_JSON.exists():
        print(f"warning: --warning-source=haiku but {HAIKU_JSON} not found; "
              "treating all warnings as omitted", file=sys.stderr)
        return {}
    data = json.loads(HAIKU_JSON.read_text())
    rows = data.get("rows") or data if isinstance(data, list) else data.get("results", [])
    out: dict[str, dict] = {}
    for r in rows:
        tid = r.get("ttb_id") or r.get("ttbId")
        el = r.get("extracted_label") or r.get("extractedLabel") or {}
        if not tid or not el:
            continue
        out[tid] = {
            "government_warning": {
                "present": bool(el.get("warning_present") or el.get("warningPresent")),
                "detected_text": (el.get("warning_text") or el.get("warningText") or "").strip(),
                "casing_all_caps": bool((el.get("warning_style") or el.get("warningStyle") or {}).get("casing_all_caps", False)),
                "heading_bold":     bool((el.get("warning_style") or el.get("warningStyle") or {}).get("heading_bold", True)),
                "body_bold":        bool((el.get("warning_style") or el.get("warningStyle") or {}).get("body_bold", False)),
                "contrast_ok":      bool((el.get("warning_style") or el.get("warningStyle") or {}).get("contrast_ok", True)),
                "separate_and_apart": bool((el.get("warning_style") or el.get("warningStyle") or {}).get("separate_and_apart", True)),
            },
            "image_quality": {
                "score":   float(el.get("image_quality_score") or el.get("imageQualityScore") or 0.9),
                "legible": bool(el.get("image_legible") if el.get("image_legible") is not None else True),
                "note":    el.get("image_quality_note") or el.get("imageQualityNote"),
            },
        }
    return out


def build(warning_source: str, val_frac: float, seed: int, require_holdout: bool = True) -> dict:
    if not TTB_CSV.exists():
        sys.exit(f"missing {TTB_CSV}; run `make scrape-ttb-stratified` first")

    rows = list(csv.DictReader(open(TTB_CSV)))
    # Keep only rows where the composite image actually downloaded
    rows = [r for r in rows if r.get("image_filename") and
            (TTB_IMGS / r["image_filename"]).exists()]

    # Exclude held-out rows so the trainer never sees the eval corpus.
    holdout: set[str] = set()
    if HOLDOUT_TXT.exists():
        holdout = {line.strip() for line in HOLDOUT_TXT.read_text().splitlines() if line.strip()}
        before = len(rows)
        rows = [r for r in rows if r["ttb_id"] not in holdout]
        print(f"holdout: excluded {before - len(rows)} of {before} rows ({len(holdout)} held-out ttb_ids in file)")
    elif require_holdout:
        sys.exit(
            f"refusing to build JSONL without a holdout list at {HOLDOUT_TXT}.\n"
            "Run `python test/eval/holdout_split.py` first, OR pass\n"
            "--allow-no-holdout if you really want an unguarded build (smoke tests only)."
        )
    else:
        print(f"⚠️  no holdout file at {HOLDOUT_TXT}; building UNGUARDED JSONL (smoke-test mode)")

    haiku_map = _load_haiku_warnings() if warning_source == "haiku" else {}

    examples: list[dict] = []
    bev_counter: Counter[str] = Counter()
    n_with_warning = 0
    for row in rows:
        tid = row["ttb_id"]
        fields = _build_fields(row)
        if not fields:
            continue  # row had no usable form data — skip

        beverage = _derive_beverage(row)
        bev_counter[beverage] += 1

        target: dict = {"fields": fields}

        if warning_source == "haiku" and tid in haiku_map:
            target.update(haiku_map[tid])
            n_with_warning += 1

        img_rel = (TTB_IMGS / row["image_filename"]).relative_to(REPO).as_posix()
        examples.append({
            "ttb_id":        tid,
            "image_path":    img_rel,
            "beverage_type": beverage,
            "target":        target,
        })

    # Train/val split — group-aware is trivial here (each ttb_id = one
    # composite = one example), but keep the same seed-shuffle pattern
    # the v1 notebook used so cross-version comparisons remain coherent.
    random.seed(seed)
    random.shuffle(examples)
    n_val = int(len(examples) * val_frac)
    val_set = examples[:n_val]
    train_set = examples[n_val:]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    train_path = OUT_DIR / "train.jsonl"
    val_path   = OUT_DIR / "val.jsonl"
    with open(train_path, "w") as f:
        for ex in train_set: f.write(json.dumps(ex) + "\n")
    with open(val_path, "w") as f:
        for ex in val_set:   f.write(json.dumps(ex) + "\n")

    manifest = {
        "n_train":         len(train_set),
        "n_val":           len(val_set),
        "n_total":         len(examples),
        "source_csv_rows": len(rows),
        "n_holdout_excluded": len(holdout),
        "warning_source":  warning_source,
        "n_with_warning":  n_with_warning,
        "beverage_counts": dict(bev_counter),
        "val_frac":        val_frac,
        "seed":            seed,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"wrote {train_path}  ({len(train_set)} examples)")
    print(f"wrote {val_path}    ({len(val_set)} examples)")
    print(f"wrote {OUT_DIR / 'manifest.json'}")
    print(f"beverage mix: {dict(bev_counter)}")
    if warning_source == "haiku":
        print(f"warning block populated for {n_with_warning}/{len(examples)} examples")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--warning-source", choices=["none", "haiku"], default="none",
                   help="Where to source government_warning targets. "
                        "'none' = field-only training (default; cleanest signal); "
                        "'haiku' = read from test/eval/ttb_live_audit.json "
                        "(use only if eval shows field-only degrades bucketing).")
    p.add_argument("--val-frac", type=float, default=0.05,
                   help="Validation fraction (default 0.05 = 1K from 20K)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--allow-no-holdout", action="store_true",
                   help="Permit building JSONL when no holdout list exists. "
                        "Dev/smoke-test only — production training MUST have a holdout.")
    args = p.parse_args()
    build(args.warning_source, args.val_frac, args.seed, require_holdout=not args.allow_no_holdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
