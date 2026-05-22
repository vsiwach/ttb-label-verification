# test/ — Test & validation suite

The test/validation suite for the TTB Label Verification system. Unzip at the project root.

```
test/
├── README.md            ← you are here
├── TEST_PLAN.md         full test matrix across products & categories
├── EVALUATION.md        how to download real COLA data + run the eval harness
├── synthetic/           controlled labels with KNOWN expected verdicts
│   ├── label_1_old_tom_spirits.png        (clean pass)
│   ├── label_2_stones_throw_wine.png      (near-match + flag)
│   ├── label_3_northwind_beer.png         (warning violations)
│   ├── label_4_cedar_sage_missing_warning.png (missing warning)
│   ├── expected_results.json              (asserted by the harness)
│   └── SYNTHETIC_README.md
└── eval/
    ├── run_eval.py      the verification harness
    └── data/            real COLA dataset goes here (downloaded — see EVALUATION.md)
```

## Two kinds of "accurate" — read this first

We are **not training a model**, so be precise about what 100% means. The system has two layers:

1. **The rules engine (deterministic).** Given a correctly-extracted set of fields + warning text,
   the verdict is provably correct from 27 CFR. This layer **should be 100% accurate** — and that
   100% is what the rules-engine unit tests (golden field inputs, no image) and the `synthetic/`
   fixtures verify.
2. **The AI extraction (reads the label image).** This is **not** deterministic and **will not** be
   100% — a model can misread a smudged or angled label. So *end-to-end* accuracy is bounded by how
   well the model reads the image, and the human-in-the-loop is the backstop.

Therefore the targets differ by layer: **rules engine + synthetic = 100%**; **real-world end-to-end
= high extraction accuracy + a very low false-positive rate on approved labels** (see `EVALUATION.md §3`).
On clean synthetic labels, extraction is essentially perfect, so synthetic end-to-end should also hit
100%; on real photos it won't, and that's expected.

## Approved vs rejected cases

- **Approved (must PASS):** real approved labels from the COLA registry → expect **auto-pass**. This
  is the false-positive guard: the tool must not reject legitimate labels.
- **Rejected (must FAIL):** the `synthetic/` violation labels, plus — for realism at scale — real
  approved labels with **controlled mutations** (title-case the warning, shrink it, change the
  declared net contents). The registry only publishes *approved* labels, so rejections are
  constructed. See `EVALUATION.md`.

## Run it

Backend up first, then:

```
# Deterministic — expect 100%
python test/eval/run_eval.py --api http://localhost:8000/api --synthetic test/synthetic

# Real-world — extraction-bounded
python test/eval/run_eval.py --api http://localhost:8000/api --csv test/eval/data/cola_sample.csv --images test/eval/data/images
```
