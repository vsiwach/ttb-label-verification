#!/bin/bash
# Demo: 1_old_tom_spirits
# Expected verdict: auto-pass
# (see test/synthetic/expected_results.json for full expected output)

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_1_old_tom_spirits.png"

APP_DATA="{\"brandName\": \"OLD TOM DISTILLERY\", \"classType\": \"Kentucky Straight Bourbon Whiskey\", \"alcoholContent\": \"45% Alc./Vol. (90 Proof)\", \"netContents\": \"750 mL\", \"bottlerNameAddress\": \"Old Tom Distillery, Frankfort, Kentucky\", \"beverageType\": \"spirits\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_1_old_tom_spirits.png"
echo " Expected group: auto-pass"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
