#!/bin/bash
# Demo: 5_valley_crest_wine
# Expected verdict: auto-pass
# Compliant wine with CONTAINS SULFITES. Label bottler 'Sonoma, CA' vs app 'Sonoma, California' — under the permissive bottler classifier, an address abbreviation that's clearly the same bottler resolves to 'match' (TTB doesn't reject for address-format variations). Tests TEST_PLAN A2/E1/D4.

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_5_valley_crest_wine.png"

APP_DATA="{\"brandName\": \"VALLEY CREST\", \"classType\": \"Sonoma County Chardonnay\", \"alcoholContent\": \"13.5% Alc./Vol.\", \"netContents\": \"750 mL\", \"bottlerNameAddress\": \"Valley Crest Winery, Sonoma, California\", \"beverageType\": \"wine\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_5_valley_crest_wine.png"
echo " Expected group: auto-pass"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
