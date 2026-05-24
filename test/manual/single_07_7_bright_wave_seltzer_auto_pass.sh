#!/bin/bash
# Demo: 7_bright_wave_seltzer
# Expected verdict: auto-pass
# Flavored malt beverage / hard seltzer — ABV present (mandatory for added-flavor products). Tests TEST_PLAN A4.

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_7_bright_wave_seltzer.png"

APP_DATA="{\"brandName\": \"BRIGHT WAVE\", \"classType\": \"Black Cherry Hard Seltzer\", \"alcoholContent\": \"5% Alc./Vol.\", \"netContents\": \"12 FL OZ\", \"bottlerNameAddress\": \"Bright Wave Beverage Co., Austin, Texas\", \"beverageType\": \"malt\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_7_bright_wave_seltzer.png"
echo " Expected group: auto-pass"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
