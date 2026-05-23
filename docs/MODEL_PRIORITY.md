# Model Priority — Best Bet for (Accuracy + <5s Latency)

Decision framework after the Qwen 4-bit baseline showed Claude wins all metrics.
What model investment most likely produces a deployable SFT extractor that
beats Claude on at least one dimension under TTB constraints?

## Constraints

1. **Accuracy ≥ Claude (~70% field, ~27% verdict)** — otherwise we ship Claude
2. **Inference < 5 sec/image** — agent workflow requirement
3. **US-or-allied origin preferred** — TTB / Treasury FedRAMP context
4. **Deployable on agency hardware** — Azure Gov, on-prem; ≤A100 budget

## Expected-value matrix

| Model | Likely accuracy after fix | Likely p95 latency | P(meets both targets) | Train cost | Inference cost |
|---|---|---|---|---|---|
| **Qwen2.5-VL-7B BF16** | 60-75% | 3-5s | **~70%** | 3-4 hr | $0.59/hr A100 |
| **InternVL3-2B BF16** | 55-70% | 1-2s | ~55% | 1-2 hr | $0.40/hr A10G |
| **Donut v2 (200M)** | 50-80% (high variance) | 0.3-0.5s | ~45% | 1.5 hr | $0.20/hr T4 or free CPU |
| Claude (status quo) | 70% baseline | 8-10s | — | $0 | $0.005/label |

## Recommendation: train in this order

### 1. Qwen2.5-VL-7B BF16 — first (highest accuracy ceiling)

**Why**: Closes the dtype-mismatch + field-naming issues that crippled the
4-bit run. Most likely to actually beat Claude on accuracy. Latency target
hit with merge_and_unload + image cap + vLLM at deploy time.

**Risk**: 3-4 hr training cost. If accuracy stays below 60% on field
extraction, abandon and pivot.

**Decision gate**: after this run, `make eval-replay-qwen` must show
≥55% field accuracy AND ≤5s latency to keep investing.

### 2. InternVL3-2B BF16 — second (best speed-to-accuracy ratio)

**Why**: 3-4× faster than Qwen 7B, similar OCR ceiling per the InternVL3
paper. Fits on T4 for cheapest cloud deployment. The "good enough faster
cheaper" candidate.

**Risk**: Smaller model, may not pick up subtler labels. Same Chinese
supply-chain caveat as Qwen.

**Decision gate**: if accuracy ≥ 50% AND latency ≤ 2s, it's the best
deployment candidate.

### 3. Donut v2 (200M) — only if there's slack

**Why**: Specialized image→JSON, smallest, runs on CPU. Strong "we deploy
on agency hardware with no GPU" pitch.

**Risk**: High accuracy variance — could be amazing or could still struggle
with parse rate. The 4-bit Qwen result suggests fine-tuning quality is
non-trivial for this task even with focused models.

**Decision gate**: if v1 parse rate problem repeats (≥30% unparseable),
abandon — the model isn't suited to this task.

## What NOT to invest in further

| Model | Why skip |
|---|---|
| **Kimi-VL** | MoE + inference-only modeling code → training landmines, already deprecated |
| **Phi-3.5-vision** | Microsoft's custom modeling.py drift vs transformers; multiple async CUDA asserts during training |
| **Llama-3.2-Vision** | Middling OCR scores, not best-in-class — Qwen or InternVL3 dominate |
| **Pixtral-12B (Mistral)** | EU origin (allied but not US), no clear advantage over Qwen 7B |

## Decision tree summary

```
Qwen BF16 ≥ Claude on accuracy?
├── YES → ship Qwen via Modal (production candidate)
├── close (within 5%) → also train InternVL3, ship whichever is faster
└── NO  → ship Claude; document SFT path as "on-prem capable" capability
```

## Deployment cost comparison (assuming each meets accuracy bar)

| Model | $/1000 labels (cloud) | $/1000 labels (agency hardware) |
|---|---|---|
| Claude API | ~$5.00 | n/a (off-network) |
| Qwen 7B on Modal A100 | ~$0.50 | $0 (already-owned GPU) |
| InternVL3-2B on Modal T4 | ~$0.10 | $0 |
| Donut on Modal CPU | ~$0.05 | $0 |

The cost story is decisive once accuracy is acceptable. **For TTB at scale
(say 10k labels/month), Qwen on agency Azure-Gov hardware saves $50/month
vs Claude API; Donut/InternVL3 save more. But only if they perform.**
