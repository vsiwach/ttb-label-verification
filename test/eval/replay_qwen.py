#!/usr/bin/env python3
"""Compatibility shim — kept so old workflows / docs don't break.
The real implementation moved to replay_extractions.py."""
import sys
from pathlib import Path
HERE = Path(__file__).parent
sys.argv = [sys.argv[0], "--label", "qwen",
            "--jsonl", str(Path.home() / "Downloads" / "qwen_outputs.jsonl"),
            "--out", str(HERE / "qwen_report.json")] + sys.argv[1:]
exec(open(HERE / "replay_extractions.py").read())
