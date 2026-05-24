#!/bin/bash
# Demo: 3_northwind_beer
# Expected verdict: needs-review
# Fields fine; Government Warning is title-case + paraphrased + sub-minimum font.

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_3_northwind_beer.png"

APP_DATA="{\"brandName\": \"NORTHWIND BREWING\", \"classType\": \"India Pale Ale\", \"alcoholContent\": \"6.8% Alc./Vol.\", \"netContents\": \"12 FL OZ\", \"bottlerNameAddress\": \"Northwind Brewing Co., Bend, Oregon\", \"beverageType\": \"beer\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_3_northwind_beer.png"
echo " Expected group: needs-review"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
