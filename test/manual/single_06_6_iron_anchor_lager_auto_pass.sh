#!/bin/bash
# Demo: 6_iron_anchor_lager
# Expected verdict: auto-pass
# Beer with NO ABV on label and none declared. Tests TEST_PLAN A3: the app must NOT flag a missing alcohol statement for malt beverages.

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_6_iron_anchor_lager.png"

APP_DATA="{\"brandName\": \"IRON ANCHOR\", \"classType\": \"Premium Lager Beer\", \"alcoholContent\": \"\", \"netContents\": \"12 FL OZ\", \"bottlerNameAddress\": \"Iron Anchor Brewing Co., Milwaukee, Wisconsin\", \"beverageType\": \"beer\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_6_iron_anchor_lager.png"
echo " Expected group: auto-pass"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
