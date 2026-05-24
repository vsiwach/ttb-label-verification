#!/bin/bash
# Demo: 8_glen_arden_scotch
# Expected verdict: auto-pass
# Imported spirit with 'PRODUCT OF SCOTLAND'. Tests TEST_PLAN B2/E6 (country of origin on imports).

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_8_glen_arden_scotch.png"

APP_DATA="{\"brandName\": \"GLEN ARDEN\", \"classType\": \"Blended Scotch Whisky\", \"alcoholContent\": \"40% Alc./Vol. (80 Proof)\", \"netContents\": \"750 mL\", \"bottlerNameAddress\": \"Glen Arden Imports, New York, NY\", \"countryOfOrigin\": \"Scotland\", \"beverageType\": \"spirits\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_8_glen_arden_scotch.png"
echo " Expected group: auto-pass"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
