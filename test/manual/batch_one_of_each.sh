#!/bin/bash
# Fast 3-label batch — one image per verdict bucket.
set -e
API="${API:-http://localhost:8000/api}"
SYNTH="test/synthetic"

echo "─────────────────────────────────────────────────────────────────────"
echo " Quick batch verify — 3 labels (one per bucket)"
echo " Expected: 1 auto-pass · 1 needs-confirm · 1 needs-review"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify-batch" \
    -F "images=@$SYNTH/label_1_old_tom_spirits.png" \
    -F "images=@$SYNTH/label_2_stones_throw_wine.png" \
    -F "images=@$SYNTH/label_4_cedar_sage_missing_warning.png" \
    | python3 test/manual/_print_batch.py
