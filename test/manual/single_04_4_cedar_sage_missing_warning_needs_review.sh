#!/bin/bash
# Demo: 4_cedar_sage_missing_warning
# Expected verdict: needs-review
# Mandatory Government Warning is absent.

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_4_cedar_sage_missing_warning.png"

APP_DATA="{\"brandName\": \"CEDAR & SAGE\", \"classType\": \"Distilled Gin\", \"alcoholContent\": \"40% Alc./Vol. (80 Proof)\", \"netContents\": \"750 mL\", \"bottlerNameAddress\": \"Cedar & Sage Spirits, Portland, Oregon\", \"beverageType\": \"spirits\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_4_cedar_sage_missing_warning.png"
echo " Expected group: needs-review"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
