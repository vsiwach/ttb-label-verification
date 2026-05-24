#!/usr/bin/env python3
"""Pretty-print a /api/verify-batch response from stdin."""
import json
import sys
from collections import Counter

items = json.load(sys.stdin)
print()
print(f"  {'#':>3}  {'image':<46}  {'group':<14}")
print(f"  {'-'*3}  {'-'*46}  {'-'*14}")
counts: Counter = Counter()
for i, it in enumerate(items, 1):
    g = it["group"]
    counts[g] += 1
    fn = (it.get("fileName") or "")[:46]
    print(f"  {i:>3}  {fn:<46}  {g:<14}")
print()
# Pretty distribution line
parts = [f"{c} {g}" for g, c in sorted(counts.items())]
print(f"  Distribution:  {' · '.join(parts)}")
print(f"  Total items:   {len(items)}")
