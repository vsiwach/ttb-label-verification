"""Pick a held-out test set from the scraped TTB-live corpus.

Run ONCE after the full stratified scrape lands and BEFORE building any
training JSONL. Sets aside ~2K ttb_ids the trainer never sees, used for
the apples-to-apples Haiku vs Qwen-v1 vs Qwen-v2 head-to-head.

Stratified by beverage_type so each bucket is fairly represented in the
holdout (not just whichever family happens to dominate the corpus).

Output:
  test/eval/data/ttb_live_test/holdout_ttbids.txt   one ttb_id per line
  test/eval/data/ttb_live_test/holdout_manifest.json  counts + seed

Downstream behavior:
  - build_qwen_jsonl.py skips any ttb_id listed in holdout_ttbids.txt
  - audit_ttb_live.py --holdout-only runs the engine on JUST these rows
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TTB_CSV = REPO / "test" / "eval" / "data" / "ttb_live" / "ttb_live.csv"
OUT_DIR = REPO / "test" / "eval" / "data" / "ttb_live_test"
HOLDOUT_TXT = OUT_DIR / "holdout_ttbids.txt"
MANIFEST = OUT_DIR / "holdout_manifest.json"


def _derive_beverage(row: dict) -> str:
    """Mirror build_qwen_jsonl._derive_beverage so the strata line up."""
    desc = (row.get("class_type_description") or "").lower()
    if any(k in desc for k in ("beer","ale","malt","stout","porter","lager")):
        return "malt"
    if any(k in desc for k in (
        "whisky","whiskey","bourbon","rye","scotch","vodka","gin","rum",
        "brandy","tequila","mezcal","cordial","liqueur","cocktail","spirit",
        "schnapps","aquavit","absinthe","grappa","cognac","agave","bitters",
    )):
        return "spirits"
    if any(k in desc for k in ("wine","sake","cider","mead","champagne","port","sherry","vermouth")):
        return "wine"
    return "wine"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=2000, help="Total holdout size (default 2000)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--force", action="store_true",
                   help="Overwrite an existing holdout list (default: refuse)")
    args = p.parse_args()

    if HOLDOUT_TXT.exists() and not args.force:
        sys.exit(f"refusing to overwrite {HOLDOUT_TXT}; pass --force to regenerate "
                 "(this would invalidate any previously-trained Qwen-v2 comparison)")

    if not TTB_CSV.exists():
        sys.exit(f"missing {TTB_CSV}; run `make scrape-ttb-stratified` first")

    rows = list(csv.DictReader(open(TTB_CSV)))
    # Only consider rows with a downloaded composite image — same filter the
    # builder applies, so train/test definitions stay consistent.
    img_dir = REPO / "test" / "eval" / "data" / "ttb_live" / "images"
    rows = [r for r in rows if r.get("image_filename") and (img_dir / r["image_filename"]).exists()]
    print(f"corpus with images: {len(rows)} rows")

    by_bev: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_bev[_derive_beverage(r)].append(r["ttb_id"])

    print(f"per-bucket: {dict((k, len(v)) for k, v in by_bev.items())}")

    # Allocate holdout proportional to bucket size — keeps the test set's
    # beverage mix matching the training set's.
    total = sum(len(v) for v in by_bev.values())
    if total < args.n:
        sys.exit(f"need {args.n} samples but only {total} rows available; "
                 "let the scrape finish or lower --n")

    random.seed(args.seed)
    holdout: list[str] = []
    for bev, ids in by_bev.items():
        share = round(args.n * len(ids) / total)
        sampled = random.sample(ids, min(share, len(ids)))
        holdout.extend(sampled)
        print(f"  {bev:10}: pulled {len(sampled)} of {len(ids)}")

    # Topup/trim if rounding put us off by a few
    if len(holdout) > args.n:
        holdout = random.sample(holdout, args.n)
    elif len(holdout) < args.n:
        remaining = [tid for ids in by_bev.values() for tid in ids if tid not in set(holdout)]
        holdout.extend(random.sample(remaining, args.n - len(holdout)))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HOLDOUT_TXT.write_text("\n".join(sorted(holdout)) + "\n")

    # Re-derive beverage counts ON the holdout itself so the manifest is honest
    holdout_set = set(holdout)
    holdout_bev = Counter()
    for r in rows:
        if r["ttb_id"] in holdout_set:
            holdout_bev[_derive_beverage(r)] += 1

    MANIFEST.write_text(json.dumps({
        "n_holdout":         len(holdout),
        "corpus_total":      len(rows),
        "beverage_counts":   dict(holdout_bev),
        "seed":              args.seed,
        "source_csv":        str(TTB_CSV.relative_to(REPO)),
    }, indent=2))

    print(f"\nwrote {HOLDOUT_TXT}  ({len(holdout)} ttb_ids)")
    print(f"wrote {MANIFEST}")
    print(f"holdout beverage mix: {dict(holdout_bev)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
