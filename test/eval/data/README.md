# eval/data/ — real COLA dataset

Real COLA labels for the real-eval harness. Mostly gitignored — only
`cola_sample.csv` (the curated, reproducible subset) is committed.

## Populate locally

```
make build-eval-data
```

That runs `test/eval/build_dataset.py`, which:

1. Downloads the COLA Cloud free sample pack
   (https://colacloud.us — CC0, ~500 KB zip → 3 CSVs).
2. Filters to images that show the Government Warning (per OCR_TEXT).
3. Drops keg-size COLAs (the label often shows a different keg size than the
   dataset's OCR_VOLUME captured).
4. Stratifies across product categories.
5. Downloads each chosen image as WebP from the CDN.
6. Writes `cola_sample.csv` with the per-image rows the harness consumes,
   plus 8 mutation rows that flip declared application data on copies of
   approved labels (rejection-detection cases).

## What's checked into the repo

- `cola_sample.csv` — the curated subset (~50 rows). Small, reproducible,
  references downloaded images.
- `.gitignore` — keeps the bulk source data and downloaded images out of
  the repo.
- This README.

## Layout when populated

```
data/
├── cola_sample.csv             # committed
├── cola.csv                    # gitignored (source)
├── cola_image.csv              # gitignored (source)
├── cola_image_barcode.csv      # gitignored (source)
├── cola-sample-pack-v1.zip     # gitignored (source archive)
└── images/                     # gitignored (downloaded WebP)
    └── <TTB_IMAGE_ID>.webp
```

`make eval-real` requires the images to be on disk; if they aren't, run
`make build-eval-data` first.

## Optional CSV column

`expected_outcome` (`auto-pass` | `needs-review`) lets the harness score
approved vs rejected cases. The build script tags approved rows `auto-pass`
and adds 8 mutation rows (declared net contents / brand / ABV flipped on
copies of approved labels) tagged `needs-review`.
