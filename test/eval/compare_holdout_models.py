"""Aggregate per-model holdout eval reports into one side-by-side table.

Reads every test/eval/data/holdout_eval/<tag>_report.json file and emits
test/eval/data/holdout_eval/COMPARISON.md with the head-to-head metrics
that decide whether v2 ships.

Decision rule the report exposes (does NOT enforce):
  - Ship Qwen v2 if it improves bucket_agreement_vs_ttb AND
    micro_field_accuracy over Qwen v1 by more than the noise floor (~2%).
  - Field-accuracy-only win is acceptable if v2 doesn't regress bucket
    agreement (i.e. the warning-detection deficit didn't drag the engine
    below v1's bucket numbers).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO / "test" / "eval" / "data" / "holdout_eval"
OUT_MD   = EVAL_DIR / "COMPARISON.md"


def _fmt(v) -> str:
    if v is None: return "—"
    if isinstance(v, float):
        return f"{v:.1%}" if 0 < v <= 1.01 else f"{v:.2f}"
    return str(v)


def main() -> int:
    reports: dict[str, dict] = {}
    for p in sorted(EVAL_DIR.glob("*_report.json")):
        tag = p.stem.removesuffix("_report")
        reports[tag] = json.loads(p.read_text())["summary"]
    if not reports:
        print(f"no *_report.json files under {EVAL_DIR}", file=sys.stderr)
        return 1

    tags = sorted(reports.keys())
    print(f"comparing: {tags}")

    # Choose v1 as the baseline for the delta column if present
    baseline = "qwen_v1" if "qwen_v1" in tags else tags[0]

    rows = [
        ("bucket_agreement_vs_ttb",      "Bucket agreement vs TTB (full engine)", True),
        ("bucket_agreement_fields_only", "Bucket agreement (fields-only, no warning rule)", True),
        ("micro_field_accuracy",         "Field accuracy (micro avg)", True),
        ("warning_present_rate",         "Warning detected", True),
        ("warning_verbatim_rate",        "Warning verbatim match", True),
        ("latency_mean",                 "Latency mean (s)", False),
        ("latency_p95",                  "Latency p95 (s)", False),
    ]

    md = ["# Holdout eval — head-to-head", ""]
    md.append(f"Comparing: {', '.join(tags)}")
    sizes = {t: reports[t].get("n", 0) for t in tags}
    md.append(f"Per-model N: {sizes}")
    md.append("")
    md.append("## Headline metrics")
    md.append("")
    md.append("| Metric | " + " | ".join(tags) + " | Δ vs " + baseline + " (best) |")
    md.append("|" + "|".join(["---"] * (len(tags) + 2)) + "|")
    for key, label, higher_better in rows:
        vals = {t: reports[t].get(key) for t in tags}
        valid = [(t, v) for t, v in vals.items() if isinstance(v, (int, float))]
        best_tag = None
        if valid:
            best_tag = max(valid, key=lambda kv: kv[1])[0] if higher_better else min(valid, key=lambda kv: kv[1])[0]
        cells = []
        for t in tags:
            v = vals[t]
            mark = " 🏆" if t == best_tag else ""
            cells.append(f"{_fmt(v)}{mark}")
        # delta column: best - baseline
        if best_tag and isinstance(vals.get(baseline), (int, float)) and isinstance(vals.get(best_tag), (int, float)):
            delta = vals[best_tag] - vals[baseline]
            delta_str = (f"{delta:+.1%}" if isinstance(delta, float) and abs(delta) < 1.5
                         else f"{delta:+.2f}")
        else:
            delta_str = "—"
        md.append(f"| {label} | " + " | ".join(cells) + f" | {delta_str} |")

    # Per-field comparison
    md.append("")
    md.append("## Per-field accuracy")
    md.append("")
    all_fields: set[str] = set()
    for t in tags:
        all_fields.update((reports[t].get("per_field_accuracy") or {}).keys())
    md.append("| Field | " + " | ".join(tags) + " |")
    md.append("|" + "|".join(["---"] * (len(tags) + 1)) + "|")
    for f in sorted(all_fields):
        cells = []
        for t in tags:
            v = (reports[t].get("per_field_accuracy") or {}).get(f)
            cells.append(_fmt(v))
        md.append(f"| {f} | " + " | ".join(cells) + " |")

    # Bucket breakdown per model
    md.append("")
    md.append("## Bucket distribution per model")
    md.append("")
    md.append("| Bucket | " + " | ".join(tags) + " |")
    md.append("|" + "|".join(["---"] * (len(tags) + 1)) + "|")
    for b in ("auto-pass", "needs-confirm", "needs-review", "ERROR"):
        cells = [str((reports[t].get("buckets") or {}).get(b, 0)) for t in tags]
        md.append(f"| {b} | " + " | ".join(cells) + " |")

    # Decision pointer
    md.append("")
    md.append("## Decision")
    md.append("")
    if "qwen_v1" in reports and "qwen_v2" in reports:
        v1 = reports["qwen_v1"]
        v2 = reports["qwen_v2"]
        d_bucket_full = v2.get("bucket_agreement_vs_ttb", 0)      - v1.get("bucket_agreement_vs_ttb", 0)
        d_bucket_fo   = v2.get("bucket_agreement_fields_only", 0) - v1.get("bucket_agreement_fields_only", 0)
        d_field       = v2.get("micro_field_accuracy", 0)         - v1.get("micro_field_accuracy", 0)
        md.append(f"- v2 vs v1 bucket agreement (full engine): {d_bucket_full:+.1%}")
        md.append(f"- v2 vs v1 bucket agreement (fields-only): {d_bucket_fo:+.1%}")
        md.append(f"- v2 vs v1 field accuracy:                 {d_field:+.1%}")
        md.append("")
        # The fields-only delta is the most informative signal — it
        # isolates v2's training objective from the warning-rule confound.
        if d_field > 0.02 and d_bucket_fo > 0.02 and d_bucket_full > -0.02:
            md.append("- **Ship v2** — clean win on training objective, no full-engine regression.")
        elif d_field > 0.02 and d_bucket_fo > 0.02 and d_bucket_full < -0.02:
            md.append("- **Ship v2 with a chained warning extractor** — v2 wins on fields/bucket where "
                      "it was trained, but the warning gap drags the full engine. Wire a separate "
                      "warning detector (or run v1 in parallel for the warning fields) before promoting.")
        elif d_field > 0.02 and d_bucket_fo < -0.02:
            md.append("- **Hold** — v2 reads individual fields better but the engine still flags more "
                      "rows than v1 even when warning is excluded. Investigate the field-status "
                      "logic (likely tighter exact-match → fuzzier 'likely' bucket).")
        else:
            md.append("- **Hold** — v2 does not clearly improve over v1.")

    OUT_MD.write_text("\n".join(md) + "\n")
    print(f"wrote {OUT_MD.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
