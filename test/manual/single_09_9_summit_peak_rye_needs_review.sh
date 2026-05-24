#!/bin/bash
# Demo: 9_summit_peak_rye
# Expected verdict: needs-review
# Application says brand 'SUMMIT RIDGE' but label reads 'SUMMIT PEAK' -> substantive brand mismatch = flag. Tests TEST_PLAN D6.

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_9_summit_peak_rye.png"

APP_DATA="{\"brandName\": \"SUMMIT RIDGE\", \"classType\": \"Straight Rye Whiskey\", \"alcoholContent\": \"47% Alc./Vol. (94 Proof)\", \"netContents\": \"750 mL\", \"bottlerNameAddress\": \"Summit Spirits, Denver, Colorado\", \"beverageType\": \"spirits\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_9_summit_peak_rye.png"
echo " Expected group: needs-review"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
