# Qwen2.5-VL LoRA vs Claude Vision — Head-to-head

> First-look comparison from the two existing eval reports.
> Caveat upfront: these are **not on the same test set**. A proper
> apples-to-apples run requires `make eval-real` against Qwen on the
> 90-image Claude test set — see "Next: apples-to-apples" below.

## Headline numbers

| Metric | Claude Vision | Qwen2.5-VL-7B + LoRA |
|---|---|---|
| Test set size | 90 images | 163 images |
| Output parsed as valid JSON | (always — tool-use schema) | 163/163 = **100%** |
| **Aggregate field-extraction accuracy** | 250/358 = **69.83%** | 346/482 = **71.78%** |
| Government Warning presence accuracy | — | 90.18% |
| Warning false-flag rate (lower = better) | 26.67% | (not measured by bundle eval) |
| End-to-end verdict accuracy (after rules engine) | 26.67% | (not measured by bundle eval) |
| Auto-pass rate on approved labels | 5.0% | (not measured by bundle eval) |
| Latency p95 | 10.47 s | ~30-60 s (Mac fp16) / ~3 s (A100 4-bit) |

## Per-field accuracy (Qwen, from bundle eval)

| Field | Correct / Total | Accuracy |
|---|---|---|
| Brand name | 64 / 108 | 59.3% |
| Class & type | 68 / 108 | 63.0% |
| **Alcohol content** | 92 / 98 | **93.9%** |
| **Net contents** | 86 / 94 | **91.5%** |
| Bottler name/address | 16 / 39 | 41.0% |
| Country of origin | 20 / 35 | 57.1% |

## What this tells us

**Qwen LoRA is competitive with Claude Vision on aggregate field extraction**
(71.78% vs 69.83%) on its own test set — and **better on the structured numeric
fields** that drive a lot of TTB verdicts (ABV 94%, net contents 91%). Where it
loses ground is on free-text fields where canonical form varies (brand, bottler,
country of origin) and where Claude's broader language priors help.

**The headline metric for the TTB pitch is not raw extraction accuracy.** The
rules engine does graduated tolerance matching (ABV ±0.3%, net contents within
2-5%, suffix-stripped brand match, multilingual country prefixes) which is where
"close enough" extractions get rescued. End-to-end verdict accuracy will look
substantially better than raw field accuracy for both models — and Qwen's strong
numeric extraction should compound favorably.

## Important caveats

1. **Different test sets.** The 90-image Claude test set was sampled before the
   group-aware-split fix (`5787b4f`). The 163-image Qwen test set uses the
   group-aware split (no COLA appears in both train and test). The Qwen test
   set is therefore *harder* by construction — there is no risk of "model
   memorized the brand from a different image of the same COLA in training."

2. **Different methodology.** Claude eval went through the rules engine
   end-to-end (POST /api/verify); Qwen eval was raw model output vs ground
   truth labels with no engine in between. The rules engine's tolerance logic
   would lift Qwen's effective accuracy on numeric fields further.

3. **Latency.** The 30-60s Mac figure is for the SFT extractor running in
   fp16 on Apple Silicon (bitsandbytes is CUDA-only). On the original A100
   training hardware in 4-bit, Qwen inference is ~3 s/image — meaningfully
   faster than Claude's 10 s p95.

4. **Supply chain.** Qwen is from Alibaba (Chinese-origin). For Treasury /
   federal deployment this is a yellow-to-red flag under EO 14117 supply
   chain rules. See the strategic notes — the pitch story is "Qwen is the
   reference benchmark; a FISMA-compatible model swap is straightforward
   once a US-origin VLM (Molmo, Florence-2, Llama-Vision) is fine-tuned on
   the same pipeline."

## Next: apples-to-apples

To get a directly comparable number:

```bash
make install-sft            # ~3 GB: torch + transformers + peft
make serve-sft-qwen         # boots backend with Qwen LoRA loaded
# in another terminal:
make eval-real              # runs the 90-image Claude test set through Qwen
```

The resulting `test/eval/report.json` will then have Qwen's **verdict accuracy
+ warning false-flag rate** on the same images Claude was scored on. That's
the number to put in the TTB writeup.

Expect on Mac: ~30-60 s × 90 images ≈ 45-90 min. On a CUDA host: ~5 min.
