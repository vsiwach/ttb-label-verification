# TTB-live audit — engine on real Form 5100.31 data

Generated against http://localhost:8000. 425 samples in 821s.

## Headline

- **auto-pass rate**: 28% (117 of 425)
- **needs-review rate**: 66% (279 of 425)
- needs-confirm: 29
- errors: 0

All TTB-approved labels are by definition "auto-pass" ground truth — this is the **engine's false-flag rate on real filed application data**.


## Per-row results

| Brand | Beverage | Origin | Engine | M/L/F | GW | DPI | Latency |
|---|---|---|---|---|---|---|---|
| 1010 CHOCOLATE MARTINI | spirits | SPAIN | **needs-review** | 3/1/2 | p=1/v=1/c=1 |  | 710.4s |
| 3 DOG WINE | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 96,96 | 543.7s |
| 3 STEVES WINERY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 178.7s |
| 3 STEVES WINERY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 179.0s |
| 3 STEVES WINERY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 184.7s |
| 3 STEVES WINERY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 185.8s |
| 3 STEVES WINERY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 185.8s |
| ALBERTO OGGERO | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 72,72 | 662.9s |
| ALBERTO OGGERO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 72,72 | 662.9s |
| ALEXANDER | spirits | CALIFORNIA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 300,300 | 350.5s |
| AMASTUOLA | wine | ITALY | **needs-review** | 4/1/1 | p=1/v=0/c=1 |  | 212.3s |
| AMERICAN HARVEST | spirits | IDAHO | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 10.6s |
| AMERICAN WINERY | wine | OHIO | **needs-review** | 4/0/1 | p=0/v=0/c=0 | 300,300 | 732.5s |
| ANA LUISA | wine | CHILE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 407.4s |
| ANA LUISA | wine | CHILE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 407.4s |
| ANA LUISA | wine | CHILE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 407.4s |
| ANGELS ENVY | spirits | KENTUCKY | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 695.3s |
| ANNAFRANCESCA | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 153.0s |
| ANONYMOUS | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 72,72 | 522.2s |
| ANTICO MONASTERO | wine | ITALY | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 96,96 | 703.5s |
| ANTIETAM CREEK VINEYARDS | wine | ILLINOIS | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 72,72 | 433.9s |
| APERTURE | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 469.3s |
| APOLLONI VINEYARDS | wine | OREGON | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 330,330 | 432.8s |
| APPLE BRANDY | spirits | MINNESOTA | **needs-review** | 2/1/2 | p=1/v=1/c=1 | 72,72 | 25.9s |
| ARMONIA | spirits | MEXICO | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 223.1s |
| ARNAUD BAILLOT | wine | FRANCE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 192,192 | 727.6s |
| ARTEMIS | wine | PENNSYLVANIA | **needs-review** | 3/2/0 | p=1/v=0/c=0 | 314,314 | 793.5s |
| ARTISANS VIGNERONS DU NORD | wine | GREECE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 95,95 | 456.8s |
| ASTRAEA GIN | spirits | GEORGIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 |  | 423.9s |
| ASTRAEA MEADOW | spirits | OREGON | **needs-review** | 2/2/1 | p=1/v=1/c=1 | 96,96 | 390.1s |
| ASTROS | wine | FRANCE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 543.0s |
| AZ. AGR. RICCI | wine | ITALY | **needs-review** | 5/1/0 | p=1/v=0/c=1 | 300,300 | 18.4s |
| AZ. AGR. RICCI | wine | ITALY | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 300,300 | 102.7s |
| AZ.AGR. RICCI | wine | ITALY | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 300,300 | 101.7s |
| BAIRAKTARIS | wine | GREECE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 95,95 | 85.6s |
| BAIRAKTARIS | wine | GREECE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 86.3s |
| BAIRAKTARIS | wine | GREECE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 95,95 | 471.2s |
| BALIFICO | wine | ITALY | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 143,143 | 440.4s |
| BARBATUS | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 287.0s |
| BARREN'S | spirits | MAINE | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 300,300 | 260.2s |
| BAY VIEW DISTILLERY AND WINERY | wine | MICHIGAN | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 95,95 | 166.2s |
| BCD | spirits | NORTH CAROLINA | **needs-review** | 0/3/2 | p=1/v=1/c=0 | 300,300 | 109.1s |
| BCD | spirits | NORTH CAROLINA | **needs-review** | 1/2/2 | p=1/v=1/c=0 | 300,300 | 109.1s |
| BCD | spirits | NORTH CAROLINA | **needs-review** | 2/1/2 | p=1/v=1/c=1 | 300,300 | 111.4s |
| BEAULIEU VINEYARD | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 178.9s |
| BEE IMMORTAL MEADERY | wine | TEXAS | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 150,150 | 276.6s |
| BELLE MEADE BOURBON | spirits | TENNESSEE | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 300,300 | 485.2s |
| BERO | beer | BELGIUM | **needs-review** | 4/0/1 | p=0/v=0/c=0 | 300,300 | 461.7s |
| BLACK MAGIC SPIRITS | spirits | KENTUCKY | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 143,143 | 589.0s |
| BLACK MAGIC SPIRITS | spirits | KENTUCKY | **needs-review** | 4/0/1 | p=1/v=1/c=0 | 143,143 | 590.5s |
| BLACKTHORNE CELLARS | wine | MARYLAND | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 576.5s |
| BLUE CHAIR BAY | spirits | NORTH CAROLINA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 163,163 | 505.6s |
| BLUE CHAIR BAY | spirits | NORTH CAROLINA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 157,163 | 658.6s |
| BONNAIRE | wine | FRANCE | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 95,95 | 378.6s |
| BONNAIRE | wine | FRANCE | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 95,95 | 381.0s |
| BONNAIRE | wine | FRANCE | **needs-review** | 5/1/0 | p=1/v=0/c=1 | 95,95 | 381.0s |
| BONNAIRE | wine | FRANCE | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 95,95 | 381.0s |
| BONNAIRE | wine | FRANCE | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 95,95 | 390.0s |
| BOSMA ESTATE WINERY | wine | WASHINGTON | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 358.2s |
| BOSMA ESTATE WINERY | wine | WASHINGTON | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 361.2s |
| BOSMOR FAMILY WINES | wine | MICHIGAN | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 299,299 | 239.4s |
| BOSMOR FAMILY WINES | wine | MICHIGAN | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 499,499 | 544.6s |
| BOUCHARD PERE & FILS | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 143,143 | 11.3s |
| BOWERS HARBOR VINEYARDS | wine | MICHIGAN | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 364.1s |
| BUDUREASCA | wine | ROMANIA | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 348.6s |
| BULLY BOY | spirits | MASSACHUSETTS | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 150,150 | 695.3s |
| BURNSIDE | spirits | OREGON | **needs-review** | 2/0/3 | p=1/v=1/c=1 | 120,120 | 645.1s |
| BXT BUBBLES BY TOM | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 96,96 | 302.8s |
| C.A. HOLLIFIELD'S | spirits | NORTH CAROLINA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 727.6s |
| CAELUM | wine | ARGENTINA | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 299,299 | 585.1s |
| CAELUM | wine | ARGENTINA | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 299,299 | 610.1s |
| CALEB LEISURE WINES | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 123.1s |
| CALEB LEISURE WINES | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 126.9s |
| CALEB LEISURE WINES | wine | CALIFORNIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 300,300 | 127.2s |
| CALEB LEISURE WINES | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=0/c=1 | 300,300 | 127.9s |
| CALLICOUNIS | spirits | GREECE | **needs-review** | 3/0/3 | p=1/v=1/c=0 | 96,96 | 69.4s |
| CANA | wine | VIRGINIA | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 288,288 | 726.0s |
| CANTINA DEL TABURNO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 143,143 | 580.8s |
| CAPTAIN MORGAN | wine | CANADA | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 280,280 | 703.5s |
| CAPTAIN'S SELECT | spirits | INDIA | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 299,299 | 805.7s |
| CASA DE COMPOSTELA | wine | PORTUGAL | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 72,72 | 334.1s |
| CASA DE COMPOSTELA | wine | PORTUGAL | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 72,72 | 334.8s |
| CASA VALDUGA | wine | BRAZIL | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 250,250 | 357.1s |
| CASA VALDUGA | wine | BRAZIL | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 250,250 | 464.1s |
| CASA XAMU | spirits | MEXICO | **needs-review** | 5/0/1 | p=1/v=1/c=1 |  | 215.1s |
| CASANOVA | wine | ITALY | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 143,143 | 440.4s |
| CASTELLO DI GRUMELLO | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 144,144 | 467.4s |
| CASTLE SPIRITS | spirits | OKLAHOMA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 786.6s |
| CEDAR RIDGE | spirits | IOWA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 143,143 | 223.1s |
| CELLAR 32 | spirits | CALIFORNIA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 300,300 | 556.3s |
| CHAGLASIAN | wine | ARGENTINA | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 150,150 | 309.0s |
| CHAGLASIAN WINERY & VINEYARDS | wine | ARGENTINA | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 310.5s |
| CHAGLASIAN WINERY & VINEYARDS | wine | ARGENTINA | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 311.6s |
| CHAGLASIAN WINERY & VINEYARDS | wine | ARGENTINA | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 314.1s |
| CHAI DE LA DIVE | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 820.4s |
| CHANT DU COT | wine | FRANCE | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 300,300 | 538.4s |
| CHANTERÊVES | wine | FRANCE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 144,144 | 16.6s |
| CHERRY REPUBLIC WINERY | wine | MICHIGAN | **needs-review** | 4/0/1 | p=1/v=1/c=1 |  | 750.8s |
| COASTAL CLASSICS CORDIALS | spirits | MEXICO | **needs-review** | 3/3/0 | p=1/v=0/c=1 | 200,200 | 158.4s |
| COJO WINES | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 150,150 | 733.6s |
| COJO WINES | wine | CALIFORNIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 150,150 | 737.7s |
| COJO WINES | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 150,150 | 737.7s |
| COMBOIO DE VESÚVIO | wine | PORTUGAL | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 150,150 | 709.4s |
| COMPANY | spirits | TENNESSEE | **needs-review** | 0/3/2 | p=1/v=1/c=1 | 300,300 | 810.8s |
| CONDE DE PICARDO | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=0 | 96,96 | 557.2s |
| CONNIPTION | spirits | NORTH CAROLINA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 150,150 | 326.1s |
| CONNIPTION | spirits | NORTH CAROLINA | **needs-review** | 2/1/2 | p=1/v=1/c=1 | 150,150 | 329.5s |
| COOPER'S HAWK WINERY & RESTAUR | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 757.3s |
| COOPER'S HAWK WINERY & RESTAUR | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=0 | 300,300 | 758.8s |
| COQUITO PABLITO | wine | SPAIN | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 96,96 | 702.6s |
| CORAZÓN DE REY | spirits | MEXICO | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 149,149 | 252.1s |
| CORAZÓN DE REY | spirits | MEXICO | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 149,149 | 252.1s |
| CORAZÓN DE REY | spirits | MEXICO | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 149,149 | 259.4s |
| CORAZÓN DE REY | spirits | MEXICO | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 149,149 | 260.2s |
| CORTEASU VINEYARDS | wine | MARYLAND | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 400,400 | 621.6s |
| COSTENA BEER | beer | COLOMBIA | **needs-review** | 4/0/1 | p=1/v=0/c=1 | 96,96 | 627.5s |
| CRAMOISI VINEYARD | wine | OREGON | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 510.3s |
| CRIMSON LANE VINEYARDS | wine | VIRGINIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 78.4s |
| CUILLERON | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 440.0s |
| CUVEE PIRQUE | wine | CHILE | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 300,300 | 315.3s |
| D'ALESIO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 319.1s |
| D'ALESIO | wine | ITALY | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 96,96 | 355.1s |
| D'ALESIO | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 356.3s |
| D.V. SRL | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 433.9s |
| DAMPFWERK DISTILLING | spirits | MINNESOTA | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 200,200 | 35.2s |
| DAMPFWERK DISTILLING | spirits | MINNESOTA | **needs-review** | 1/4/0 | p=0/v=0/c=0 |  | 117.9s |
| DAMPFWERK DISTILLING | spirits | MINNESOTA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 144,144 | 120.1s |
| DANDELION PROSECCO | wine | ITALY | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 300,300 | 622.9s |
| DAVIDE | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 672.9s |
| DAY SWIGGER | spirits | GEORGIA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 143,143 | 134.4s |
| DESCENDANTS LIEGEOIS DUPONT | wine | WASHINGTON | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 366.5s |
| DESTILERIJA ZARIC | spirits | SERBIA | **needs-review** | 3/1/2 | p=1/v=0/c=1 | 720,720 | 574.1s |
| DISARONNO | spirits | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 720.9s |
| DISOBEDIENT SPIRITS | spirits | PENNSYLVANIA | **needs-review** | 4/0/1 | p=0/v=0/c=0 | 150,150 | 204.0s |
| DOC BROWN FARM & DISTILLERS | spirits | GEORGIA | **needs-review** | 2/2/1 | p=1/v=1/c=1 | 143,143 | 50.0s |
| DOC BROWN FARM & DISTILLERS | spirits | GEORGIA | **needs-review** | 2/2/1 | p=1/v=1/c=1 | 143,143 | 50.5s |
| DOC BROWN FARM & DISTILLERS | spirits | GEORGIA | **needs-confirm** | 2/3/0 | p=1/v=1/c=1 | 143,143 | 54.2s |
| DOC BROWN FARM & DISTILLERS | spirits | GEORGIA | **needs-confirm** | 2/3/0 | p=1/v=1/c=1 | 72,72 | 131.8s |
| DOMAINE ALICE HARTMANN | wine | LUXEMBOURG | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 143,143 | 531.9s |
| DOMAINE DE L'AMAUVE | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 448.6s |
| DOMAINE DE L'AMAUVE | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 448.6s |
| DOMAINE DES CAVARODES | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 150,150 | 815.8s |
| DOMAINE DIDIER AMIOT | wine | FRANCE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 144,144 | 586.3s |
| DOMAINE GEANTET-PANSIOT | wine | FRANCE | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 96,96 | 744.5s |
| DOMAINE GEANTET-PANSIOT | wine | FRANCE | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 96,96 | 745.0s |
| DOMAINE GEANTET-PANSIOT | wine | FRANCE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 746.0s |
| DOMAINE GEANTET-PANSIOT | wine | FRANCE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 749.5s |
| DOMAINE TERREBRUNE | wine | FRANCE | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 300,300 | 390.1s |
| DOUKENIE WINERY | wine | VIRGINIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 72,72 | 519.0s |
| DOUKENIE WINERY | wine | VIRGINIA | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 72,72 | 525.2s |
| DR. KONNEKER'S | spirits | MISSOURI | **needs-review** | 3/0/2 | p=0/v=0/c=0 | 300,300 | 799.0s |
| DUCKHORN WINE COMPANY | wine | CALIFORNIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 300,300 | 370.9s |
| DULCINEA REAL | wine | SPAIN | **needs-confirm** | 2/4/0 | p=1/v=1/c=1 | 96,96 | 456.8s |
| DÉTENTE | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 96,96 | 595.2s |
| ED CATRINA | spirits | MEXICO | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 119,119 | 343.5s |
| EDWIN BRIX VINEYARD | wine | WISCONSIN | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 143,143 | 614.1s |
| EFFIE JEWEL | spirits | GEORGIA | **needs-review** | 0/3/2 | p=1/v=1/c=1 | 143,143 | 54.2s |
| EL CAMINO | spirits | MEXICO | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 286,286 | 213.1s |
| EMMOLO | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 426.6s |
| FABER | spirits | PENNSYLVANIA | **needs-review** | 4/0/1 | p=1/v=0/c=1 | 300,300 | 492.4s |
| FAMILLE COLLOVRAY & TERRIER | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 447.0s |
| FARM STAND | wine | FLORIDA | **needs-review** | 3/0/2 | p=1/v=0/c=1 | 143,143 | 821.2s |
| FATTORIA DEL TESO | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 72,72 | 27.7s |
| FATTORIA DEL TESO | wine | ITALY | **needs-review** | 6/0/0 | p=1/v=0/c=1 | 72,72 | 104.0s |
| FATTORIA DEL TESO | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 72,72 | 111.4s |
| FEELZ SO RIGHT | wine | TEXAS | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 95,95 | 563.4s |
| FERRARI-CARANO | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 501.2s |
| FILARI ANTICHI | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 662.9s |
| FINCA MANZANOS RESERVA | wine | SPAIN | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 200,200 | 637.5s |
| FLYBIRD | wine | MEXICO | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 300,300 | 752.6s |
| FOLLIN-ARBELET | wine | FRANCE | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 120,120 | 689.4s |
| FORLORN HOPE | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=0 | 200,200 | 416.2s |
| FORREST | wine | NEW ZEALAND | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 95,95 | 337.0s |
| FOUR LANTERNS WINERY | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 216,216 | 139.7s |
| FOXY'S | spirits | MARYLAND | **needs-review** | 2/1/2 | p=1/v=1/c=1 | 300,300 | 308.5s |
| FREE WILL BREWING CO | malt | PENNSYLVANIA | **auto-pass** | 4/0/0 | p=1/v=1/c=1 |  | 327.6s |
| FULKERSON WINERY & FARM | wine | NEW YORK | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 718.5s |
| GALLO | beer | GUATEMALA | **needs-review** | 4/1/0 | p=0/v=0/c=0 | 300,300 | 791.5s |
| GARDEN AND GOTHAM | spirits | NEW JERSEY | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 300,300 | 789.9s |
| GARY FARRELL | wine | CALIFORNIA | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 95,95 | 250.4s |
| GENERAL PSYCHOTIC ACTIVITY | wine | CALIFORNIA | **needs-review** | 5/0/0 | p=0/v=0/c=0 | 72,72 | 184.1s |
| GENERAL PSYCHOTIC ACTIVITY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=0 |  | 190.8s |
| GENERAL PSYCHOTIC ACTIVITY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 299,299 | 266.9s |
| GENERAL PSYCHOTIC ACTIVITY | wine | CALIFORNIA | **needs-review** | 5/0/0 | p=0/v=0/c=0 |  | 273.3s |
| GERBIDO | wine | ITALY | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 96,96 | 545.4s |
| GINEVRA CAVALLARO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 448.6s |
| GOOD PEOPLE BREWING COMPANY | beer | ALABAMA | **needs-review** | 3/0/1 | p=0/v=0/c=0 | 150,150 | 783.8s |
| GRANIER ORTIZ | wine | BOLIVIA | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 812.9s |
| GRANVILLE | wine | OREGON | **needs-review** | 4/0/1 | p=0/v=0/c=0 | 144,144 | 204.0s |
| GRIGNANO | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 144,144 | 192.0s |
| HARD TRUTH DISTILING CO. | spirits | INDIANA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 199,199 | 477.7s |
| HARD TRUTH DISTILLING CO. | spirits | INDIANA | **needs-review** | 3/2/0 | p=1/v=0/c=1 | 199,199 | 477.6s |
| HARTMAN'S DISTILLING CO. | spirits | NEW YORK | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 143,143 | 758.8s |
| HAZLITT 1852 VINEYARDS | wine | NEW YORK | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 180,180 | 477.3s |
| HAZLITT 1852 VINEYARDS | wine | NEW YORK | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 180,180 | 478.2s |
| HAZLITT 1852 VINEYARDS | wine | NEW YORK | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 180,180 | 484.1s |
| HEART WARMER | wine | COLORADO | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 143,143 | 567.3s |
| HELLO WORLD | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 143,143 | 102.7s |
| HELLO WORLD | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 143,143 | 167.9s |
| HELLO WORLD | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 143,143 | 173.8s |
| HIDDEN HILLS VINEYARD AND WINE | wine | ILLINOIS | **needs-review** | 2/1/2 | p=1/v=1/c=1 |  | 340.5s |
| HINNANT FAMILY VINEYARDS | wine | NORTH CAROLINA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 561.4s |
| HOPS AND HARDWARE | spirits | MEXICO | **needs-review** | 0/6/0 | p=0/v=0/c=0 | 300,300 | 78.4s |
| HOTEL TANGO | spirits | OHIO | **needs-review** | 4/0/1 | p=0/v=0/c=0 | 96,96 | 20.8s |
| HUIA | wine | NEW ZEALAND | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 776.1s |
| ISLANDJON | spirits | GEORGIA | **needs-review** | 0/5/0 | p=0/v=0/c=0 | 72,72 | 133.9s |
| ISLANDJON | spirits | GEORGIA | **needs-review** | 0/5/0 | p=0/v=0/c=0 | 72,72 | 135.5s |
| JEREMIE HUCHET | wine | FRANCE | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 96,96 | 287.2s |
| JOURNEY DISTILLED | spirits | OREGON | **needs-review** | 4/1/0 | p=1/v=0/c=0 | 300,300 | 197.3s |
| KADENCE WINE CO | wine | AMERICAN | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 299,299 | 397.6s |
| KADENCE WINE CO | wine | NEW YORK | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 299,299 | 397.6s |
| KALLOS | wine | NORTH CAROLINA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 358,358 | 172.2s |
| KAVANAGH | spirits | IRELAND | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 144,144 | 608.2s |
| KAYA | spirits | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 86.3s |
| KENTUCKY RAMBLER | spirits | KENTUCKY | **needs-review** | 2/2/1 | p=0/v=0/c=0 | 150,150 | 251.2s |
| KOSTA BROWNE | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 800.8s |
| KUHEIJI | wine | JAPAN | **needs-review** | 3/1/2 | p=1/v=1/c=1 | 95,95 | 456.4s |
| KULUP RAKI | spirits | TURKEY | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 144,144 | 515.9s |
| L'OUVERTURE | wine | FRANCE | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 143,143 | 591.7s |
| LALIVARA | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 150,150 | 95.2s |
| LALIVARA | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 150,150 | 179.3s |
| LANDUCCI | spirits | ITALY | **needs-review** | 3/1/2 | p=1/v=1/c=1 | 300,300 | 556.5s |
| LAPA | wine | PORTUGAL | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 557.2s |
| LAWRENCEBURG BOURBON COMPANY | spirits | KENTUCKY | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 59,59 | 583.1s |
| LAZY ELM | wine | NORTH CAROLINA | **needs-review** | 4/1/0 | p=1/v=0/c=1 | 150,150 | 198.6s |
| LE CLIVIE | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 573.0s |
| LEGACY SPIRITS | spirits | MICHIGAN | **auto-pass** | 5/0/0 | p=1/v=1/c=1 |  | 231.1s |
| LEGACY SPIRITS | spirits | MICHIGAN | **auto-pass** | 5/0/0 | p=1/v=1/c=1 |  | 231.1s |
| LEGENDS A MEADERY | wine | COLORADO | **needs-review** | 3/1/1 | p=1/v=1/c=1 |  | 456.0s |
| LEIPER'S FORK DISTILLERY | spirits | TENNESSEE | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 95,95 | 96.6s |
| LES LUNES WINE | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 |  | 198.6s |
| LESOM WEINE GBR | wine | GERMANY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 200,200 | 345.3s |
| LITTLEMILL AGED 27 YEARS SINGL | malt | SCOTLAND | **needs-review** | 2/2/1 | p=1/v=1/c=1 | 300,300 | 70.3s |
| LONE PINE | beer | MAINE | **auto-pass** | 4/0/0 | p=1/v=1/c=1 | 150,150 | 570.0s |
| LUCKY EN VUE | wine | FRANCE | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 119,119 | 463.5s |
| LUIGI & GIOVANNI | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 299,299 | 600.9s |
| LUIGI AND GIOVANNI | wine | CALIFORNIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 299,299 | 597.1s |
| LUIGI AND GIOVANNI TASTE OF IT | wine | CALIFORNIA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 299,299 | 596.4s |
| LUSSA | spirits | SCOTLAND | **needs-confirm** | 5/1/0 | p=1/v=1/c=0 | 95,95 | 603.8s |
| LUSSA GIN | spirits | SCOTLAND | **needs-review** | 5/0/1 | p=1/v=1/c=0 | 95,95 | 607.7s |
| MAD PADDLE BREWSTILLERY | spirits | INDIANA | **needs-review** | 4/1/0 | p=1/v=0/c=0 | 143,143 | 413.8s |
| MAISON GLANDIEN | wine | FRANCE | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 143,143 | 439.6s |
| MAISON GLANDIEN | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 498.1s |
| MAISON GLANDIEN | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 200,200 | 498.3s |
| MAISON GLANDIEN | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 498.5s |
| MAISON GLANDIEN | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 149,149 | 503.2s |
| MAISON GLANDIEN | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 149,149 | 504.2s |
| MALIBU WINE COMPANY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 72,72 | 260.2s |
| MALIBU WINE COMPANY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 72,72 | 267.7s |
| MALIBU WINE COMPANY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 72,72 | 269.2s |
| MANTICE | wine | ITALY | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 72,72 | 564.8s |
| MANZONE GIOVANNI | wine | ITALY | **needs-review** | 6/0/0 | p=1/v=0/c=1 | 600,600 | 416.2s |
| MARANI PHERSVI | wine | GEORGIA | **needs-review** | 3/0/2 | p=1/v=1/c=1 | 299,299 | 620.1s |
| MARCHESI DI BAROLO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 95.4s |
| MARGALUZ | spirits | MEXICO | **needs-review** | 1/5/0 | p=0/v=0/c=0 |  | 149.9s |
| MARIANNE | wine | SOUTH AFRICA (UNION OF) | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 772.9s |
| MARTINE HONEYSUCKLE LIQUEUR | spirits | TEXAS | **needs-review** | 2/2/1 | p=0/v=0/c=0 | 72,72 | 305.8s |
| MASSERIA BORGO DEI TRULLI | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 244,241 | 341.7s |
| MATASANTA | spirits | MEXICO | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 96,96 | 697.1s |
| MATTHIASSON | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 500,500 | 820.6s |
| MCKAHN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 299,299 | 778.9s |
| MCKAHN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 299,299 | 784.8s |
| MEIOMI | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 301,301 | 507.5s |
| MILL CAMP WINES & CIDERS | wine | NORTH CAROLINA | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 300,300 | 717.9s |
| MODERN ALCHEMIST | wine | NORTH CAROLINA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 149,149 | 696.5s |
| MOMMENPOP | wine | CALIFORNIA | **needs-review** | 2/0/3 | p=1/v=1/c=1 | 301,301 | 671.9s |
| MOMMENPOP | wine | CALIFORNIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 301,301 | 677.1s |
| MOMMENPOP | wine | CALIFORNIA | **needs-review** | 2/0/3 | p=1/v=1/c=1 | 301,301 | 679.7s |
| MOONSHINER CRAZY CHUCK | spirits | FLORIDA | **needs-review** | 0/5/0 | p=0/v=0/c=0 | 300,300 | 670.9s |
| MOUNT HOLLY CIDER LLC | wine | VERMONT | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 699,699 | 151.9s |
| MURVIEDRO | wine | SPAIN | **auto-pass** | 6/0/0 | p=1/v=1/c=0 | 144,144 | 768.4s |
| MUSSIO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=0 | 300,300 | 303.4s |
| MUSSIO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 303.4s |
| MUSSIO | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 304.0s |
| NADAL | wine | SPAIN | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 531.3s |
| NADAL | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=0/c=1 | 96,96 | 537.3s |
| NECK OF THE WOODS | malt | NEW JERSEY | **auto-pass** | 4/0/0 | p=1/v=1/c=1 | 120,120 | 245.0s |
| NED | wine | AUSTRALIA | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 144,144 | 516.6s |
| NEIGE | wine | CANADA | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 222.0s |
| NEW ENGLAND BARREL COMPANY | spirits | NEW HAMPSHIRE | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 776.1s |
| NIT DEL FOC BRUT | wine | SPAIN | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 96,96 | 637.5s |
| NIT DEL FOC BRUT NATURE | wine | SPAIN | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 96,96 | 633.7s |
| NIT DEL FOC BRUT ROSÉ | wine | SPAIN | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 96,96 | 631.8s |
| OLD ELK | spirits | OHIO | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 144,144 | 646.0s |
| OLE BISON | spirits | LOUISIANA | **needs-review** | 0/3/2 | p=0/v=0/c=0 | 95,95 | 314.3s |
| OLE BISON | spirits | LOUISIANA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 149,149 | 319.5s |
| OLE BISON | spirits | LOUISIANA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 95,95 | 320.0s |
| OLE BISON | spirits | LOUISIANA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 149,149 | 320.9s |
| OLE BISON NO.86 BOURBON | spirits | LOUISIANA | **needs-review** | 2/2/1 | p=1/v=1/c=1 | 149,149 | 324.3s |
| OUTLAW SPIRITS | spirits | TENNESSEE | **needs-review** | 4/0/1 | p=1/v=0/c=0 | 200,200 | 495.8s |
| PACIFIC BLUE | spirits | TENNESSEE | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 150,150 | 548.5s |
| PAGO DE LOS CAPELLANES | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 599,599 | 12.3s |
| PAPA LUNA | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 537.3s |
| PAPA PEDRO | spirits | PUERTO RICO | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 72,72 | 276.6s |
| PARCE RUM | spirits | COLOMBIA | **needs-review** | 3/1/2 | p=1/v=1/c=1 | 143,143 | 511.4s |
| PARCE RUM | spirits | COLOMBIA | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 143,143 | 513.9s |
| PASCAL ROBIN | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 299,299 | 267.7s |
| PATRICIA GREEN CELLARS | wine | OREGON | **needs-review** | 5/0/0 | p=1/v=0/c=1 | 300,300 | 366.5s |
| PENELOPE | spirits | TEXAS | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 150,150 | 239.1s |
| PENET-CHARDONNET | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 120,120 | 433.1s |
| PERENNIAL ARTISAN ALES | malt | MISSOURI | **needs-review** | 3/1/0 | p=1/v=0/c=1 | 72,72 | 611.8s |
| PESTONI FAMILY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 95,95 | 588.2s |
| PESTONI FAMILY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 95,95 | 795.7s |
| PIKE CREEK | spirits | CANADA | **needs-review** | 0/5/1 | p=0/v=0/c=0 | 120,120 | 330.3s |
| PILSEN | beer | COLOMBIA | **needs-review** | 4/0/1 | p=1/v=0/c=1 | 96,96 | 806.1s |
| PINOT VISTA VINEYARDS | wine | OREGON | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 216,216 | 205.0s |
| PLANETES | wine | SPAIN | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 713,713 | 510.8s |
| POKER | beer | COLOMBIA | **needs-review** | 4/0/1 | p=1/v=0/c=1 | 96,96 | 812.6s |
| PRAIRIE RIDGE RESERVE RED WINE | wine | WISCONSIN | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 143,143 | 613.4s |
| PUNTAGAVE | spirits | MEXICO | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 300,300 | 526.7s |
| QUATTRO CASTELLA | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 143,143 | 820.7s |
| RATZFERT | wine | FRANCE | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 200,200 | 717.3s |
| RED BRICK WINERY | wine | CALIFORNIA | **needs-review** | 5/0/0 | p=0/v=0/c=0 | 275,275 | 651.2s |
| RED BRICK WINERY | wine | CALIFORNIA | **needs-review** | 5/0/0 | p=0/v=0/c=0 | 275,275 | 652.3s |
| REDWOOD EMPIRE | spirits | CALIFORNIA | **needs-review** | 4/1/0 | p=0/v=0/c=0 | 600,600 | 471.2s |
| REDWOOD EMPIRE | spirits | CALIFORNIA | **needs-review** | 4/0/1 | p=0/v=0/c=0 | 300,300 | 767.5s |
| RHUM BARBANCOURT | spirits | HAITI | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 299,299 | 638.4s |
| RHUMBEAUX | spirits | GEORGIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 72,72 | 793.5s |
| RIDGEWAY FARM | wine | OHIO | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 172.4s |
| RISING SUN VINEYARD | wine | TEXAS | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 72,72 | 577.0s |
| RUMPLE MINZE | wine | CANADA | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 280,280 | 710.4s |
| SABLONNETTES | wine | FRANCE | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 300,300 | 800.8s |
| SANDARA | wine | SPAIN | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 1200,1200 | 812.9s |
| SANDHILL CRANE VINEYARDS | wine | MICHIGAN | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 400,400 | 130.6s |
| SANDRONE | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 78.4s |
| SANSHU MIKAWA MIRIN | wine | JAPAN | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 119,119 | 162.1s |
| SANTOS IMPORTS | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 299,299 | 570.7s |
| SARL MARCEL LAPIERRE | wine | FRANCE | **needs-review** | 4/0/2 | p=1/v=0/c=1 | 300,300 | 326.0s |
| SEAHORSE FARM WINERY | wine | AMERICAN | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 299,299 | 75.3s |
| SEAHORSE FARM WINERY | wine | AMERICAN | **needs-confirm** | 5/1/0 | p=1/v=1/c=1 | 299,299 | 75.9s |
| SENSHI | wine | MULTIPLE COUNTRIES | **needs-review** | 3/0/3 | p=1/v=1/c=0 | 200,200 | 86.3s |
| SERRA BEVERAGE COMPANY | beer | PENNSYLVANIA | **auto-pass** | 4/0/0 | p=1/v=1/c=1 | 143,143 | 483.9s |
| SESTADISOPRA | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 150,150 | 71.2s |
| SESTADISOPRA | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 150,150 | 72.1s |
| SEÑORÍO DE LOS LLANOS | wine | SPAIN | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 47.3s |
| SHEEHAN WINERY | wine | NEW MEXICO | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 72,72 | 615.2s |
| SHOREHAVEN | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 240.2s |
| SIERRA NEVADA | malt | CALIFORNIA | **auto-pass** | 4/0/0 | p=1/v=1/c=1 | 150,150 | 599.9s |
| SIERRA NEVADA | beer | CALIFORNIA | **auto-pass** | 4/0/0 | p=1/v=1/c=1 | 300,300 | 605.8s |
| SIRIUS | wine | FRANCE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 143,143 | 192.3s |
| SKREWBALL | spirits | ARKANSAS | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 261,261 | 769.7s |
| SMOKIN TAILS DISTILLERY | spirits | NEW YORK | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 462.9s |
| SOHO VODKA | spirits | NORTH CAROLINA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 300,300 | 519.3s |
| SOIRE | spirits | MULTIPLE COUNTRIES | **needs-review** | 1/4/1 | p=1/v=1/c=0 | 143,143 | 488.3s |
| SOLIS | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 35.2s |
| SOLIS | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 35.2s |
| SOLIS | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 43.6s |
| SOLIS | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 44.5s |
| SOPRAVVENTO | wine | ITALY | **needs-confirm** | 5/1/0 | p=1/v=1/c=0 | 119,119 | 276.6s |
| SPIRITS OF ST. LOUIS | spirits | MISSOURI | **needs-review** | 4/0/1 | p=1/v=0/c=1 | 300,300 | 42.7s |
| SPRITZZANTE | wine | ITALY | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 300,300 | 20.1s |
| ST. EVA HILL VINEYARD | wine | CALIFORNIA | **needs-review** | 5/0/0 | p=1/v=0/c=1 | 300,300 | 492.0s |
| ST. EVA HILL VINEYARD | wine | CALIFORNIA | **needs-review** | 5/0/0 | p=1/v=0/c=1 | 300,300 | 492.9s |
| STAGGERING UNICORN WINERY | wine | PENNSYLVANIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 72,72 | 549.7s |
| STARFIELD VINEYARDS | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 432,432 | 338.1s |
| STARIA | spirits | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 |  | 627.9s |
| STILLWATER ARTISANAL | malt | MARYLAND | **needs-review** | 3/0/1 | p=1/v=0/c=0 | 150,150 | 646.4s |
| STILLWATER ARTISINAL | malt | CONNECTICUT | **needs-review** | 2/1/1 | p=0/v=0/c=0 |  | 581.9s |
| STORMWOOD WINES | wine | NEW ZEALAND | **needs-review** | 3/1/2 | p=1/v=1/c=1 | 144,144 | 397.6s |
| SUMMERLONG | wine | CALIFORNIA | **needs-review** | 3/1/1 | p=0/v=0/c=0 | 1000,1000 | 743.5s |
| SUR VALLES WINE GROUP | wine | CHILE | **needs-review** | 5/0/1 | p=1/v=1/c=1 |  | 762.1s |
| TALISMAN TRISTAN TATE | spirits | MEXICO | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 95,95 | 655.2s |
| TANSY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 120,120 | 485.2s |
| TEKIRDAG RAKISI GOBEK | spirits | TURKEY | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 144,144 | 223.1s |
| TENTH WARD DISTILLING COMPANY | spirits | MARYLAND | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 414.8s |
| TENUTA LA MERIDIANA | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 300,300 | 192.7s |
| TERRAE III | wine | ITALY | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 72,72 | 198.6s |
| TERRES DU MOUTHEROT | wine | FRANCE | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 299,299 | 158.7s |
| THE "FARM" A COOK FAMILY VINEY | wine | AMERICAN | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 300,300 | 710.4s |
| THE DAMPFWERK DISTILLERY CO | spirits | MINNESOTA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 200,200 | 120.7s |
| THE DAMPFWERK DISTILLERY CO | spirits | MINNESOTA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 200,200 | 121.3s |
| THE DAMPFWERK DISTILLING | spirits | MINNESOTA | **needs-review** | 4/0/1 | p=1/v=1/c=1 |  | 25.4s |
| THE DAMPFWERK DISTILLING | spirits | MINNESOTA | **needs-review** | 5/0/0 | p=1/v=0/c=1 | 150,150 | 27.7s |
| THE DAMPFWERK DISTILLING | spirits | MINNESOTA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 96,96 | 34.4s |
| THE LAST WYNN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 265,265 | 679.7s |
| THE LAST WYNN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 200,200 | 680.7s |
| THE LAST WYNN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 683.0s |
| THE LAST WYNN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 200,200 | 685.7s |
| THE LAST WYNN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 278,278 | 687.3s |
| THE RARE WINE CO. | wine | ITALY | **auto-pass** | 6/0/0 | p=1/v=1/c=1 | 96,96 | 617.2s |
| THE TALL BLOND | spirits | ESTONIA | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 72,72 | 19.5s |
| THE VILLA ESTATE VINEYARDS | wine | NEW YORK | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 150,150 | 139.5s |
| THE VILLA ESTATE VINEYARDS | wine | NEW YORK | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 150,150 | 143.4s |
| THE VILLA ESTATE VINEYARDS | wine | NEW YORK | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 150,150 | 152.6s |
| THE VILLA ESTATE WINERY | wine | NEW YORK | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 150,150 | 145.9s |
| THE WHISKEY BLENDERY | spirits | TEXAS | **needs-review** | 4/0/1 | p=1/v=1/c=1 |  | 595.0s |
| TIGERLYFE | spirits | KANSAS | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 96,96 | 525.5s |
| TIP TOP | spirits | MICHIGAN | **needs-review** | 3/2/0 | p=0/v=0/c=0 | 96,96 | 420.7s |
| TIRRIDDIS | wine | WASHINGTON | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 144,144 | 424.9s |
| TITOMIROV | spirits | UKRAINE | **needs-confirm** | 5/1/0 | p=1/v=1/c=0 | 96,96 | 672.9s |
| TOAST & HONEY | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 96,96 | 12.3s |
| TOKOEKA ESTATE RESERVE | wine | NEW ZEALAND | **needs-review** | 3/1/2 | p=1/v=1/c=0 | 300,300 | 755.5s |
| TRAPI DEL BUENO | wine | CHILE | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 95,95 | 619.3s |
| TRAS LA YESCA | wine | SPAIN | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 72,72 | 751.4s |
| TRES SABORES | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 150,150 | 549.7s |
| TRES SABORES | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 150,150 | 550.7s |
| TRIBUTARY BREWING CO. | beer | MAINE | **auto-pass** | 4/0/0 | p=1/v=1/c=1 | 100,100 | 687.3s |
| TUFENKIAN HERITAGE | wine | ARMENIA | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 393.7s |
| TUFENKIAN HERITAGE | wine | ARMENIA | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 300,300 | 424.9s |
| TURKS HEAD | wine | CALIFORNIA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 347.7s |
| UNCHARTED | spirits | TENNESSEE | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 72,72 | 702.1s |
| UNCLE BOGUE | spirits | GEORGIA | **needs-review** | 2/0/3 | p=1/v=1/c=1 | 143,143 | 133.1s |
| UNCORKED IN MAYBERRY | wine | NORTH CAROLINA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 300,300 | 399.5s |
| VAGANOV APRICOT BRANDY | spirits | CALIFORNIA | **needs-review** | 2/2/1 | p=1/v=1/c=1 | 72,72 | 173.5s |
| VAGANOV GRAPE BRANDY | spirits | CALIFORNIA | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 600,600 | 290.8s |
| VAGANOV PEACH BRANDY | spirits | CALIFORNIA | **needs-review** | 2/1/2 | p=1/v=1/c=1 | 600,600 | 290.8s |
| VEGABRISA TEMPRANILLO | wine | SPAIN | **needs-review** | 4/1/1 | p=1/v=1/c=1 | 96,96 | 629.4s |
| VERITAS ESTATE | wine | MICHIGAN | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 299,299 | 775.5s |
| VINI D ARTE | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=1 | 72,72 | 727.6s |
| VITIVINICOLA FANGAREGGI | wine | ITALY | **needs-review** | 5/0/1 | p=1/v=1/c=0 | 149,149 | 213.1s |
| WARNER'S | spirits | UNITED KINGDOM | **needs-review** | 3/2/1 | p=0/v=0/c=0 | 96,96 | 156.8s |
| WATERS EDGE WINERY ROSE DISTRI | wine | OKLAHOMA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 120,120 | 351.3s |
| WATERTOWN | spirits | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 144,144 | 95.9s |
| WHISKEY JYPSI | spirits | TENNESSEE | **needs-confirm** | 4/1/0 | p=1/v=1/c=1 | 299,299 | 768.9s |
| WHISKEY JYPSI | spirits | TENNESSEE | **needs-review** | 3/1/1 | p=1/v=1/c=0 | 299,299 | 785.2s |
| WICKED WEED | malt | NORTH CAROLINA | **auto-pass** | 4/0/0 | p=1/v=1/c=1 | 143,143 | 626.1s |
| WILD THANG | wine | TEXAS | **needs-review** | 3/0/2 | p=1/v=1/c=0 | 300,300 | 563.7s |
| WOOLLY MAMMOTH | wine | NEW YORK | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 578.8s |
| YELLOWSTONE | spirits | TEXAS | **needs-review** | 3/1/1 | p=1/v=1/c=1 | 300,300 | 733.6s |
| YOUNG HEARTS DISTILLING COMPAN | spirits | NORTH CAROLINA | **auto-pass** | 5/0/0 | p=1/v=1/c=1 | 144,144 | 646.0s |
| YOUNG HEARTS DISTILLING COMPAN | spirits | NORTH CAROLINA | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 72,72 | 652.9s |
| YOUTHFUL RESERVE | wine | TEXAS | **needs-review** | 4/0/1 | p=1/v=1/c=1 | 300,300 | 205.0s |
| YUTMISO | wine | CHINA | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 299,299 | 233.9s |
| YUTMISO | wine | CHINA | **needs-review** | 4/0/2 | p=1/v=1/c=1 | 299,299 | 240.2s |
| ZAKIN | wine | CALIFORNIA | **auto-pass** | 5/0/0 | p=1/v=1/c=0 | 144,144 | 138.0s |
