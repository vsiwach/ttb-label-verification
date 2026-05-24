#!/bin/bash
# Demo: 2_stones_throw_wine
# Expected verdict: needs-confirm
# Label prints '700 mL' vs declared 750 mL — 6.7% delta is within the 10% border tolerance for net contents -> 'likely' (agent confirms). The graduated tolerance correctly distinguishes a small misfill (verify) from a substantive content difference (>15% would flag). Brand casing-only is now 'match' per the brand-permissive rule.

set -e
API="${API:-http://localhost:8000/api}"
IMG="test/synthetic/label_2_stones_throw_wine.png"

APP_DATA="{\"brandName\": \"STONE'S THROW\", \"classType\": \"California Red Table Wine\", \"alcoholContent\": \"13.5% Alc./Vol.\", \"netContents\": \"750 mL\", \"bottlerNameAddress\": \"Stone's Throw Cellars, Sonoma, California\", \"beverageType\": \"wine\"}"

echo "─────────────────────────────────────────────────────────────────────"
echo " Sending: label_2_stones_throw_wine.png"
echo " Expected group: needs-confirm"
echo "─────────────────────────────────────────────────────────────────────"

curl -s -X POST "$API/verify" \
    -F "image=@$IMG" \
    -F "applicationData=$APP_DATA" \
    | python3 -m json.tool
