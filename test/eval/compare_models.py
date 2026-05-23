#!/usr/bin/env python3
"""Side-by-side comparison of all eval reports (Claude + any SFT models).

Reads whatever {qwen,internvl3,donut}_report.json files exist under
test/eval/, plus the Claude baseline at test/eval/report.json. Prints
a wide table showing per-metric numbers + which model wins each row.

Usage:
    python test/eval/compare_models.py
    python test/eval/compare_models.py --markdown > test/eval/COMPARISON.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR  = REPO_ROOT / "test" / "eval"

# (metric_key, label, direction)  — direction: +1 = higher better, -1 = lower better
METRICS = [
    ("n",                          "test set size",                  0),
    ("approved_n",                 "approved labels in test set",    0),
    ("field_extraction_accuracy",  "field extraction accuracy",     +1),
    ("verdict_accuracy",           "end-to-end verdict accuracy",   +1),
    ("auto_pass_rate_approved",    "auto-pass rate on approved",    +1),
    ("warning_false_flag_rate",    "warning false-flag rate",       -1),
    ("latency_mean",               "latency mean (s)",              -1),
    ("latency_p95",                "latency p95 (s)",               -1),
]

MODELS = [
    ("report.json",            "Claude"),
    ("qwen_report.json",       "Qwen-7B"),
    ("internvl3_report.json",  "InternVL3-2B"),
    ("donut_report.json",      "Donut v2"),
]


def _load_reports():
    reports = {}
    for fname, label in MODELS:
        path = EVAL_DIR / fname
        if path.exists():
            try:
                reports[label] = json.loads(path.read_text())
            except Exception as e:
                print(f"  ⚠️ skipping {fname}: {e}", file=sys.stderr)
    return reports


def _fmt(v):
    if v is None: return "—"
    if isinstance(v, float):
        return f"{v:.2%}" if 0 < v < 1.01 else f"{v:.3f}"
    return str(v)


def _winner(values, direction):
    """Index of the best non-None numeric value, given direction."""
    candidates = [(i, v) for i, v in enumerate(values)
                  if isinstance(v, (int, float))]
    if not candidates or direction == 0:
        return None
    pick = max if direction > 0 else min
    return pick(candidates, key=lambda x: x[1])[0]


def render_text(reports: dict[str, dict]) -> str:
    labels = list(reports.keys())
    col_w = max(12, max(len(L) for L in labels) + 1)
    out_lines = []
    sep = "=" * (34 + col_w * len(labels))
    sub = "-" * (34 + col_w * len(labels))

    header = f"{'Metric':<32}  " + "".join(f"{L:>{col_w}}" for L in labels)
    out_lines.append(sep)
    out_lines.append(header)
    out_lines.append(sub)

    for key, label, direction in METRICS:
        values = [reports[L].get(key) for L in labels]
        win = _winner(values, direction)
        cells = []
        for i, v in enumerate(values):
            cell = _fmt(v)
            if win is not None and i == win and v != reports[labels[0]].get(key):
                cell = f"★ {cell}"
            cells.append(f"{cell:>{col_w}}")
        out_lines.append(f"{label:<32}  " + "".join(cells))

    out_lines.append(sep)
    out_lines.append(f"  ★ marks the best value per metric. — means not measured.")
    return "\n".join(out_lines)


def render_markdown(reports: dict[str, dict]) -> str:
    labels = list(reports.keys())
    lines = ["# TTB Label Extraction — Model Comparison\n"]
    lines.append("Side-by-side metrics from each SFT model vs the Claude baseline.\n")
    lines.append("| Metric | " + " | ".join(labels) + " |")
    lines.append("|" + "---|" * (len(labels) + 1))
    for key, label, direction in METRICS:
        values = [reports[L].get(key) for L in labels]
        win = _winner(values, direction)
        cells = []
        for i, v in enumerate(values):
            cell = _fmt(v)
            if win is not None and i == win:
                cell = f"**{cell}**"
            cells.append(cell)
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("**Bold** = best value per metric.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true",
                    help="Emit a Markdown table instead of plain text")
    args = ap.parse_args()

    reports = _load_reports()
    if not reports:
        print(f"No report files found under {EVAL_DIR}/", file=sys.stderr)
        return 1
    if "Claude" not in reports:
        print(f"⚠️ Claude baseline ({EVAL_DIR}/report.json) is missing — "
              "comparisons will only show SFT models", file=sys.stderr)

    if args.markdown:
        print(render_markdown(reports))
    else:
        print(render_text(reports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
