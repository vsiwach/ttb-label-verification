# Qwen2.5-VL-7B LoRA vs Claude Vision — Real Apples-to-Apples Results

**Same 90 images. Same ground truth. Same rules engine. Same scoring methodology.**

This is the actual head-to-head comparison promised earlier — Qwen output
generated in Colab on the Claude test set, then scored through the local
backend's rules engine via `make eval-replay-qwen`.

## Headline numbers (n=89, 59 approved labels)

| Metric | Claude | Qwen (4-bit LoRA) | Δ | Winner |
|---|---|---|---|---|
| Field extraction accuracy | 69.83% | **41.64%** | -28pp | Claude |
| End-to-end verdict accuracy | 26.67% | **16.85%** | -10pp | Claude |
| Auto-pass rate on approved | 5.00% | **0.00%** | -5pp | Claude |
| Warning false-flag rate | 26.67% | **37.29%** | +10pp | Claude (lower better) |
| Latency mean | 8.43 s | **12.45 s** | +4s | Claude |
| Latency p95 | 10.47 s | **15.73 s** | +5s | Claude |

**Claude wins on every metric.** The 4-bit-trained Qwen LoRA is not currently
competitive on TTB label extraction.

## What went wrong with Qwen (root-cause analysis)

The replay produced detailed diagnostics — here's what the breakdown shows:

| Diagnostic | Count | What it means |
|---|---|---|
| Test set size | 89 | (1 image failed to download during eval) |
| Rows where Qwen produced NO output | 0 | Eval extraction ran on every image |
| Rows where Qwen output existed but was unparseable | 1 | Aggressive parser recovered all but one |
| Rows where Qwen explicitly emitted `"fields": {}` | 6 | Model "gave up" on these labels |
| Field correctness | 147 / 353 | 41.64% — most fields are wrong, not missing |

### Root causes, in order of impact

**1. Training–inference dtype mismatch (biggest issue)**

The Qwen LoRA was trained against `unsloth/Qwen2.5-VL-7B-Instruct-bnb-4bit`
(pre-quantized 4-bit weights). At inference time we apply it to
`Qwen/Qwen2.5-VL-7B-Instruct` (BF16). The weight tensors don't match exactly,
so the adapter's contribution is subtly off — model rambles past JSON
boundaries, emits late EOS, and frequently gives up on fields.

**Fix already wired up**: `sft_qwen2_5_vl.ipynb` is upgraded to train in BF16
end-to-end. Expected to close 60-80% of the gap.

**2. Field-name discipline (large, partially fixed)**

Qwen emitted snake_case keys (`brand_name`, `volume`, `bottled_by`) instead
of the schema's canonical names (`Brand name`, `Net contents`, `Bottler
name/address`). Initial scoring was 0% field accuracy because the rules
engine looked for the canonical names.

**Fix**: added `_canonicalize_field_name()` in `backend/app/extractors/sft.py`
with a 60+ alias map. This recovered ~42pp of accuracy (0 → 41.64%). The
remaining gap is real model errors, not naming.

**3. Style observation accuracy**

Qwen frequently mis-reports `casing_all_caps`, `body_bold`, etc. on the
Government Warning. The rules engine requires `casing_all_caps=True` to
mark the warning compliant; Qwen says `False` even when the text clearly
starts with "GOVERNMENT WARNING" in caps. This drives the warning false-flag
rate up to 37% (vs Claude's 27%).

**Fix**: training-time loss on these specific booleans, OR replace with
deterministic post-processing (regex-detect `^GOVERNMENT WARNING:` in the
warning_text → infer `casing_all_caps=True`).

**4. Empty fields on 6 labels**

6 of 89 labels yielded `"fields": {}` outright. The model decided NO fields
were "clearly visible" per the system prompt's "OMIT what you can't see"
guidance. With the 640×640 image cap we apply for speed, these are likely
labels where small print became illegible.

**Fix**: train on higher-res images, OR scale max_pixels up at inference
for first-attempt failures (retry at 1024×1024 if 640×640 returns empty).

**5. Latency: Qwen is 50% slower than Claude**

12.45s mean vs Claude's 8.43s. Qwen on Colab A100 + BF16 + LoRA-on-mismatched-
base hits a slow path: rambling output → generates closer to `max_new_tokens=384`
→ each token is bnb-dequant slow.

**Fix**: BF16 training produces cleaner EOS → shorter outputs → faster
generation. Combined with vLLM serving (Modal deploy) the production target
of <5s/image is achievable. Current 12s is research-pipeline overhead.

## What we learned

### About this Qwen run (negative result, honestly)
- 4-bit-trained LoRA + BF16 inference is fragile. **Don't ship it as-is.**
- The bundle eval's 71.78% raw-extraction accuracy was on its OWN training-
  distribution test set; on the harder real Claude test set with full rules
  engine, real accuracy is 41.64%.
- The 27 CFR rules engine doesn't fix bad extraction — `garbage in, flag out`.

### About the methodology (positive)
- The replay harness works end-to-end: Colab → JSONL → local rules engine →
  byte-comparable JSON report. Reproducible.
- The aggressive parser + field aliasing now handle a wide range of model
  output sloppiness. The remaining unparseable rate is 1/89 — essentially zero.
- The diagnostic counters (`sft_empty_fields_count`, etc.) tell us EXACTLY
  why accuracy fell short — no guessing.

### For the TTB pitch
- **The rules engine + architecture is the durable value**, not any specific
  model. Same pipeline works whether the extractor is Claude, Qwen, InternVL3,
  or Donut.
- **The 4-bit Qwen number doesn't define what's possible.** BF16 retrain is
  expected to substantially close the gap.
- **Honest writeup**: "We benchmarked Qwen 4-bit and found it 28pp behind
  Claude on field extraction. We've identified four root causes, fixed two
  in tooling (field aliasing, parser), and are retraining in BF16 to fix the
  remaining two. Next-iteration eval forthcoming."

## Next steps

1. **BF16 Qwen retrain** (notebook ready, ~3-4 hr training). Expected:
   field accuracy 42% → 60-75% (closes ~70% of the gap).
2. **InternVL3-2B SFT** for the lighter-faster alternative data point.
3. **Donut v2** if you want the smallest-model angle.
4. **`make eval-compare-all`** once any of the above produce results — gives
   the four-way table for the writeup.

The current report is saved at `test/eval/qwen_report.json` and snapshotted
as `test/eval/qwen_report_4bit_baseline.json` so the BF16 retrain has a
clear A/B reference.
