#!/bin/bash
# Batch demo: send ALL 9 synthetic fixtures in a single request.
# Backend fans them out concurrently, returns one BatchItemResult per image
# (each with a verdict bucket: auto-pass / needs-confirm / needs-review).
#
# Expected mix across the 9 fixtures:
#   auto-pass:      5  (labels 1, 5, 6, 7, 8)
#   needs-confirm:  1  (label 2 — 700 mL vs 750 mL declared)
#   needs-review:   3  (labels 3, 4, 9 — bad warning / missing warning / brand mismatch)

set -e
API="${API:-http://localhost:8000/api}"
SYNTH="test/synthetic"

echo "─────────────────────────────────────────────────────────────────────"
echo " Batch verify — 9 synthetic labels"
echo " Expected: 5 auto-pass · 1 needs-confirm · 3 needs-review"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify-batch" \
    -F "images=@$SYNTH/label_1_old_tom_spirits.png" \
    -F "images=@$SYNTH/label_2_stones_throw_wine.png" \
    -F "images=@$SYNTH/label_3_northwind_beer.png" \
    -F "images=@$SYNTH/label_4_cedar_sage_missing_warning.png" \
    -F "images=@$SYNTH/label_5_valley_crest_wine.png" \
    -F "images=@$SYNTH/label_6_iron_anchor_lager.png" \
    -F "images=@$SYNTH/label_7_bright_wave_seltzer.png" \
    -F "images=@$SYNTH/label_8_glen_arden_scotch.png" \
    -F "images=@$SYNTH/label_9_summit_peak_rye.png" \
    | python3 test/manual/_print_batch.py
