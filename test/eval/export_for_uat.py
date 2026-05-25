"""Export the clean real samples in a form suitable for manual UAT.

Produces two artifacts under test/eval/uat_pack/:
  labels/             — copies of each clean .webp label image, renamed
                        with brand + ttb_id for human readability.
  applications.csv    — one row per label with the parsed application data
                        (brand, class, ABV, net, bottler, COO, beverage).
                        Agent copies a row into the /upload form by hand,
                        then drops the matching label into the dropzone.
  applications.json   — same data as JSON for tooling.

This separates the label artwork from the form data so you can test:
  - Single upload  → drag ONE label, paste fields, click Verify
  - Batch dashboard → drag MANY labels, optionally paste one shared app,
                       hit Start processing.

The pre-paired picker on /upload is a convenience; the UAT pack lets
you exercise the unpaired (production-real) workflow where labels and
applications arrive separately.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
from app.ocr_bottler import extract_bottler  # noqa: E402
CSV  = REPO / "test" / "eval" / "data" / "cola_sample.csv"
IMG  = REPO / "test" / "eval" / "data" / "images"
OUT  = REPO / "test" / "eval" / "uat_pack"


def clean_row(r: dict) -> bool:
    bad = lambda s: not s or len(s) > 50 or any(c in s for c in "(/.")
    if bad(r["brand_name"]) or bad(r["class_type"]):
        return False
    if r.get("mutation"):
        return False
    return (IMG / r["image_filename"]).exists()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    labels_dir = OUT / "labels"
    if labels_dir.exists():
        shutil.rmtree(labels_dir)
    labels_dir.mkdir()

    with open(CSV) as f:
        rows = [r for r in csv.DictReader(f) if clean_row(r)]

    apps = []
    for r in rows:
        brand_slug = slug(r["brand_name"])
        bev = r["beverage_type"]
        dest_name = f"{brand_slug}-{r['ttb_id']}.webp"
        shutil.copy(IMG / r["image_filename"], labels_dir / dest_name)
        apps.append({
            "labelFile": dest_name,
            "ttbId": r["ttb_id"],
            "brandName": r["brand_name"],
            "productName": r.get("product_name", ""),
            "classType": r["class_type"],
            "alcoholContent": r.get("alcohol_content", ""),
            "netContents": r.get("net_contents", ""),
            "bottlerNameAddress": r.get("bottler_name_address") or extract_bottler(r.get("image_ocr_text", "")),
            "countryOfOrigin": r.get("origin", "").title(),
            "beverageType": bev,
            "domesticOrImported": r.get("domestic_or_imported", ""),
            "expectedOutcome": r.get("expected_outcome", ""),
        })

    # CSV
    csv_path = OUT / "applications.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(apps[0].keys()))
        w.writeheader()
        for a in apps:
            w.writerow(a)

    # JSON
    (OUT / "applications.json").write_text(json.dumps(apps, indent=2))

    # README in the pack
    (OUT / "README.md").write_text(
        f"# UAT pack — {len(apps)} real COLA samples\n\n"
        "Labels and applications are separated so you can drive the system\n"
        "the way a real intake works: label image arrives on one path, the\n"
        "filed application data on another.\n\n"
        f"- `labels/` — {len(apps)} `.webp` label images (renamed by brand + ttb_id)\n"
        f"- `applications.csv` — paired application data (brand, class, ABV, net, COO, expected)\n"
        f"- `applications.json` — same data as JSON\n\n"
        "## Single-label workflow\n\n"
        "1. Pick a row from `applications.csv`.\n"
        "2. Open the app → /upload.\n"
        "3. Fill in the form by hand from that CSV row (or paste).\n"
        "4. Drag the matching `labels/<labelFile>` image into the dropzone.\n"
        "5. Click Verify.\n\n"
        "## Batch workflow\n\n"
        "1. Open the app → /batch.\n"
        "2. Drag multiple labels from `labels/` into the dropzone at once.\n"
        "3. (Optional) paste a shared application from `applications.csv`.\n"
        "4. Click Start processing.\n\n"
        "## Cross-check\n\n"
        "`applications.csv` includes the column `expectedOutcome` (TTB's actual\n"
        "disposition for each COLA). Compare with the system's verdict.\n"
        "The audit run in `test/eval/REAL_AUDIT.md` shows the typical engine\n"
        "verdict per sample.\n"
    )

    print(f"Exported {len(apps)} samples to {OUT.relative_to(REPO)}")
    print(f"  labels/         {len(apps)} files")
    print(f"  applications.csv")
    print(f"  applications.json")
    print(f"  README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
