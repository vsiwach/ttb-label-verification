# Real-data audit — every clean COLA Cloud sample

Generated against http://localhost:8000 (claude-code mode). 67 samples processed in 1.4 min.

## Summary

**By expected (TTB ground truth):**

- `auto-pass`: 51
- `needs-review`: 16

**By engine verdict:**

- `auto-pass`: 15
- `needs-confirm`: 11
- `needs-review`: 41

**Agreement matrix (expected → engine):**

| Expected | Engine | Count |
|---|---|---|
| auto-pass | auto-pass | 10 |
| auto-pass | needs-confirm | 5 |
| auto-pass | needs-review | 36 |
| needs-review | auto-pass | 5 |
| needs-review | needs-confirm | 6 |
| needs-review | needs-review | 5 |

## Per-row results

| Brand | Beverage | Import | Expected | Engine | M/L/F | GW | Latency |
|---|---|---|---|---|---|---|---|
| Arrowood Farm Brewery | beer | domestic | auto-pass | **needs-review** ~ | 4/0/0 | p=0/v=0/c=0 | 39.6s |
| Brix City Brewing | beer | domestic | auto-pass | **auto-pass** ✓ | 4/0/0 | p=1/v=1/c=1 | 31.2s |
| Cabro Imported Beer | beer | imported | auto-pass | **needs-confirm** ~ | 4/1/0 | p=1/v=1/c=1 | 36.9s |
| City Walk Brewing | beer | domestic | auto-pass | **needs-review** ~ | 3/1/0 | p=0/v=0/c=0 | 30.9s |
| Diaspora | beer | domestic | auto-pass | **needs-review** ~ | 3/0/1 | p=1/v=1/c=1 | 34.5s |
| Fonta Flora Brewery | beer | domestic | auto-pass | **needs-review** ~ | 4/0/0 | p=1/v=0/c=1 | 39.5s |
| Gallo Imported Beer | beer | imported | auto-pass | **needs-confirm** ~ | 4/1/0 | p=1/v=1/c=0 | 35.9s |
| Golden Extra Imported Beer | beer | imported | auto-pass | **auto-pass** ✓ | 5/0/0 | p=1/v=1/c=1 | 26.0s |
| Great Notion | beer | domestic | auto-pass | **needs-review** ~ | 4/0/0 | p=0/v=0/c=0 | 30.0s |
| Great Notion | beer | domestic | auto-pass | **auto-pass** ✓ | 4/0/0 | p=1/v=1/c=1 | 30.6s |
| Pilsener Imported Beer | beer | imported | auto-pass | **needs-confirm** ~ | 4/1/0 | p=1/v=1/c=1 | 25.5s |
| Pilsener Imported Beer | beer | imported | auto-pass | **needs-review** ~ | 4/0/1 | p=1/v=1/c=1 | 27.3s |
| Wander Back Beerworks | beer | domestic | auto-pass | **needs-confirm** ~ | 3/1/0 | p=1/v=1/c=1 | 25.8s |
| Wander Back Beerworks | beer | domestic | auto-pass | **needs-review** ~ | 3/0/1 | p=1/v=1/c=1 | 35.7s |
| Abashiri | malt | imported | auto-pass | **auto-pass** ✓ | 5/0/0 | p=1/v=1/c=1 | 44.6s |
| Blendings Winery | malt | domestic | needs-review | **needs-confirm** ~ | 3/1/0 | p=1/v=1/c=0 | 5.7s |
| Blendings Winery | malt | domestic | needs-review | **needs-confirm** ~ | 3/1/0 | p=1/v=1/c=0 | 5.9s |
| Blendings Winery | malt | domestic | needs-review | **needs-confirm** ~ | 3/1/0 | p=1/v=1/c=0 | 10.1s |
| Bokbunja-Mmm | malt | imported | auto-pass | **needs-review** ~ | 4/0/1 | p=1/v=1/c=1 | 41.1s |
| James Bay Distillers | malt | domestic | auto-pass | **needs-review** ~ | 1/2/1 | p=1/v=1/c=0 | 53.3s |
| Momentum | malt | domestic | auto-pass | **needs-review** ~ | 2/1/1 | p=1/v=1/c=1 | 44.8s |
| Tropical Club | malt | imported | auto-pass | **needs-review** ~ | 2/1/2 | p=1/v=1/c=1 | 85.2s |
| Upside Down | malt | domestic | auto-pass | **needs-review** ~ | 2/1/1 | p=0/v=0/c=0 | 40.9s |
| Adversary | spirits | domestic | auto-pass | **needs-review** ~ | 3/0/2 | p=1/v=1/c=1 | 49.2s |
| Agave Desmadre | spirits | imported | needs-review | **needs-review** ✓ | 6/0/0 | p=1/v=0/c=1 | 20.2s |
| Assemblage Bourbon | spirits | domestic | auto-pass | **needs-review** ~ | 2/2/1 | p=1/v=1/c=1 | 45.8s |
| Blairmont | spirits | imported | auto-pass | **needs-review** ~ | 5/0/1 | p=1/v=1/c=1 | 62.9s |
| Bondstone | spirits | domestic | auto-pass | **needs-review** ~ | 3/1/1 | p=1/v=1/c=1 | 45.5s |
| Bunnahabhain | spirits | imported | auto-pass | **needs-review** ~ | 4/1/1 | p=1/v=1/c=1 | 67.6s |
| Cardenal Mendoza | spirits | imported | needs-review | **needs-review** ✓ | 2/2/2 | p=1/v=1/c=1 | 6.3s |
| Carroll Noir | spirits | domestic | auto-pass | **needs-review** ~ | 2/2/1 | p=1/v=1/c=1 | 62.5s |
| Casa Huitzila Blanco | spirits | imported | auto-pass | **needs-review** ~ | 2/2/2 | p=1/v=1/c=1 | 73.6s |
| Casa Maestri | spirits | imported | auto-pass | **needs-review** ~ | 4/1/1 | p=1/v=1/c=1 | 74.8s |
| Depot Shine | spirits | domestic | auto-pass | **needs-review** ~ | 3/1/1 | p=1/v=1/c=0 | 54.0s |
| Foursquare | spirits | imported | auto-pass | **needs-review** ~ | 2/3/1 | p=1/v=1/c=1 | 62.6s |
| Gold Snow | spirits | imported | needs-review | **needs-review** ✓ | 4/2/0 | p=0/v=0/c=0 | 10.1s |
| Holyrood Distillery | spirits | imported | auto-pass | **needs-confirm** ~ | 3/3/0 | p=1/v=1/c=1 | 67.4s |
| James Bay Distillers | spirits | domestic | auto-pass | **needs-review** ~ | 1/3/1 | p=1/v=0/c=1 | 49.0s |
| La Que Manda | spirits | imported | auto-pass | **needs-review** ~ | 4/0/2 | p=1/v=1/c=1 | 74.1s |
| Lagavulin | spirits | imported | auto-pass | **needs-review** ~ | 0/5/1 | p=1/v=1/c=1 | 66.7s |
| Lanthier Winery Distillery | spirits | domestic | auto-pass | **needs-review** ~ | 5/0/0 | p=0/v=0/c=0 | 68.3s |
| Leiper's Fork Distillery | spirits | domestic | auto-pass | **needs-review** ~ | 2/2/1 | p=1/v=1/c=0 | 82.2s |
| Lost Lantern | spirits | domestic | auto-pass | **needs-review** ~ | 3/0/2 | p=1/v=0/c=1 | 84.7s |
| Lucky One | spirits | domestic | auto-pass | **needs-review** ~ | 3/0/2 | p=0/v=0/c=0 | 77.7s |
| Lupita | spirits | imported | needs-review | **needs-confirm** ~ | 4/2/0 | p=1/v=1/c=0 | 15.9s |
| Matchbook Distilling Co | spirits | domestic | auto-pass | **auto-pass** ✓ | 5/0/0 | p=1/v=1/c=1 | 50.3s |
| Matchbook Distilling Co | spirits | domestic | auto-pass | **auto-pass** ✓ | 5/0/0 | p=1/v=1/c=1 | 78.9s |
| Matchbook Distilling Co | spirits | domestic | auto-pass | **auto-pass** ✓ | 5/0/0 | p=1/v=1/c=1 | 79.2s |
| O-Mea-Raq 25 | spirits | imported | needs-review | **needs-confirm** ~ | 5/1/0 | p=1/v=1/c=0 | 11.5s |
| Old Grand Dad | spirits | domestic | auto-pass | **needs-review** ~ | 3/1/1 | p=1/v=1/c=1 | 49.5s |
| Osprey Point Whiskey | spirits | domestic | auto-pass | **needs-review** ~ | 2/2/1 | p=1/v=1/c=1 | 79.5s |
| Port Askaig | spirits | imported | auto-pass | **needs-review** ~ | 5/0/1 | p=1/v=1/c=1 | 64.4s |
| Satoh | spirits | imported | auto-pass | **auto-pass** ✓ | 6/0/0 | p=1/v=1/c=1 | 58.4s |
| Vetiver Liqueur | spirits | domestic | auto-pass | **needs-review** ~ | 3/0/2 | p=1/v=1/c=1 | 54.6s |
| Well Made | spirits | domestic | auto-pass | **auto-pass** ✓ | 5/0/0 | p=1/v=1/c=1 | 58.7s |
| Well Made | spirits | domestic | auto-pass | **auto-pass** ✓ | 5/0/0 | p=1/v=1/c=1 | 75.2s |
| West Track | spirits | domestic | auto-pass | **needs-review** ~ | 2/2/1 | p=1/v=1/c=1 | 54.3s |
| Wild Common | spirits | imported | auto-pass | **needs-review** ~ | 4/2/0 | p=1/v=0/c=1 | 71.0s |
| Wolves | spirits | domestic | auto-pass | **needs-review** ~ | 2/2/1 | p=0/v=0/c=0 | 58.2s |
| Cremisan | wine | imported | needs-review | **auto-pass** ~ | 6/0/0 | p=1/v=1/c=0 | 16.5s |
| Cremisan | wine | imported | needs-review | **auto-pass** ~ | 6/0/0 | p=1/v=1/c=0 | 19.8s |
| Moonbeam | wine | domestic | needs-review | **auto-pass** ~ | 5/0/0 | p=1/v=1/c=0 | 15.0s |
| Moonbeam | wine | domestic | needs-review | **auto-pass** ~ | 5/0/0 | p=1/v=1/c=0 | 20.4s |
| Moonbeam | wine | domestic | needs-review | **auto-pass** ~ | 5/0/0 | p=1/v=1/c=0 | 21.4s |
| Navarre Coulee Vineyards | wine | domestic | needs-review | **needs-confirm** ~ | 4/1/0 | p=1/v=1/c=1 | 15.9s |
| Pichon Comtesse | wine | imported | needs-review | **needs-review** ✓ | 5/0/1 | p=1/v=1/c=1 | 11.1s |
| Ruby | wine | imported | needs-review | **needs-review** ✓ | 4/0/2 | p=1/v=1/c=1 | 6.5s |
