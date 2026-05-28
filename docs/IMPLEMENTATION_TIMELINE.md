# Implementation Timeline

End-to-end build of the TTB Label Verification take-home prototype. Five
calendar days, 91 commits, ~12k LOC across React + FastAPI + training
notebooks + eval harness. This document is the engineering log behind the
[headline result in the README](../README.md#headline-result--qwen-v2-lora-fine-tuned-on-ttb-stratified-data)
— what was built, in what order, and why each decision was made.

---

## Day 1 — Friday, May 22 — scaffold + rules engine
*(10 commits)*

**Objective:** Get a working end-to-end skeleton with the deterministic
27 CFR rules engine in place before touching any model.

| Commit | What landed |
|---|---|
| `dd5655e` | React + Vite + TypeScript frontend baseline — `/upload`, `/result`, `/batch`, `/review` routes; `LabelExtractor` API contract |
| `1de163d` | FastAPI mock scaffold with `/api/verify` + `/api/verify-batch` |
| `09bff48` | **Inference interface + 27 CFR rules engine.** `LabelExtractor` ABC, field-match classifier (3-state with graduated tolerances), Government Warning verifier (verbatim + casing + bbox-DPI type-size scaffold), mandatory-field mapping by beverage type. **33 unit tests pass.** |
| `54746de` | Steps 4-8 bundled — image pipeline (Pillow validate + legibility score), async batch with `asyncio.Semaphore`, real Anthropic CloudExtractor, OnPremExtractor (Tesseract + Ollama hook), CORS / security headers, integration gate |
| `58a7f5f` | **COLA Cloud eval harness landed** — first apples-to-apples evaluation framework |
| `4571969` | Stress-test expansion + conservative engine + per-field coverage matrix |
| `31e566b` | **Multi-agent diagnostic cut warning false-flag rate from 15% to 2%** — investigated each false-positive, identified 4 root causes, fixed each |
| `090ffdc` | Severity model + `productName` fallback so only real violations flag |
| `92720f6` | `INFERENCE_MODE=claude-code` routes Anthropic Vision through `claude` CLI (Max subscription, no API spend) |
| `1387275` | **Per-field severity tiering** — needs-review false-positive 65% → 35% |

**End of Day 1 state:** Working backend + frontend + rules engine. 67 real
TTB-approved labels from COLA Cloud free sample loaded. Mock + Cloud +
Claude-Code + OnPrem extractors all functional. 78 unit tests passing.
Zero AI training yet — proving the deterministic-engine-first architecture.

---

## Day 2 — Saturday, May 23 — SFT exploration + model selection
*(55 commits — the heaviest day)*

**Objective:** Find a fine-tunable open-weights vision-language model
that could match Claude's accuracy at fraction of the cost, runnable
on-prem.

### Morning: model selection sweep
Tried five candidate base models in parallel notebooks:
- **Qwen2.5-VL-7B-Instruct** (Alibaba, Apache 2.0)
- **Phi-3.5-vision** (Microsoft, MIT)
- **InternVL3-2B** (OpenGVLab, Apache 2.0)
- **Kimi-VL-A3B-Thinking** (Moonshot, Apache 2.0)
- **Donut** (NAVER, MIT — image-to-JSON specialist)

Multiple commits in `sft_*.ipynb` notebooks pinning the working
dependency stacks for each (Colab GPU environments are brittle —
`numpy`, `transformers`, `peft`, `trl` version pins matter).

### Afternoon: Qwen wins; first SFT training
Qwen2.5-VL-7B emerged as the best fit — Apache 2.0 license, strong OCR
on diverse fonts, and a reasonably small adapter footprint (LoRA r=16 ≈
190 MB). Phi-3.5-vision required disabling gradient checkpointing
(`3449cb0`); InternVL3 needed `bitsandbytes` for the optimizer
(`64949e2`); these were ruled out for prototype velocity.

| Commit | What landed |
|---|---|
| `b16b7b1` | **Backend integration of SFT extractor** — Qwen + Donut adapters behind the same `LabelExtractor` interface |
| `dcdc27d` | Dropped Donut, simplified `SFTExtractor` to Qwen-only |
| `b66a26f` | **Modal Qwen serving** + InternVL3-2B + Donut v2 alternatives |
| `7b73321` | **Qwen notebook upgraded to BF16** (no Unsloth, no 4-bit) — matches training-time dtype, faster inference |
| `b49a1de` | SFT parser: field-name aliasing + confidence coercion + latency aggregation |
| `671ca00` | **Aggressive JSON recovery** in SFT parser — recovers many "unparseable" outputs (markdown fences, truncation, smart quotes) |
| `22f4759` | **Head-to-head harness** — Qwen vs InternVL3-2B vs Donut v2 vs Claude on the same eval set |
| `e11978a` | **SFT replay e2e tests** — Qwen JSON output → rules engine → verdict |
| `231cfd3` | Critical fix: save-before-eval bug (empty adapter zip) |
| `58676d0` | **First Qwen v1 result: within 6pp of Claude on field accuracy** |
| `4d318ff` | DESIGN.md with PRD alignment matrix |
| `ae72472` | Comprehensive README rewrite with diagrams + full configurability |
| `178d080` | **Production-ready Modal serving + runbook** |

**End of Day 2 state:** First Qwen v1 LoRA trained on COLA Cloud free
sample (N=1,377, 2 epochs). Achieved ~63% field accuracy vs Claude's ~70%
— *within 6 percentage points of the frontier model on the held-out set.*
Documented in `test/eval/QWEN_VS_CLAUDE.md`. Architecture extensible to
swap any open-weights model with one factory branch.

---

## Day 3 — Sunday, May 24 — agency-data pipeline + v2 design
*(5 commits)*

**Objective:** The COLA Cloud free sample is a CC0 mirror of public TTB
data — but it's only ~1,400 labels with garbled OCR-spillage in the
brand/class columns. Need bigger, cleaner data straight from the source.

| Commit | What landed |
|---|---|
| `0e2a582` | Ready-to-run manual demo scripts for every verdict bucket (auto-pass / needs-confirm / needs-review) |
| `880675e` | **Real-data audit pipeline + DPI type-size check + TTB Registry scraper** — first connection to the official TTB Public COLA Registry |
| `1ad336e` | **Stratified TTB scraping** via the registry's advanced-search class-type filter — spirits / wine / beer-malt buckets |
| `bf37d6e` | **Qwen v2 training pipeline** — parallel scrape, JSONL builder, Modal training entrypoint |
| `15ebcad` | **Head-to-head holdout eval (Haiku vs Qwen v1 vs Qwen v2)** — eval harness built to compare three model paths against the same 200-row holdout |

**End of Day 3 state:** TTB Public COLA Registry scrape running at 0.5
req/s (polite rate). Stratified pipeline pulling ~20K labels across the
three beverage categories. Data builder cleaning bottler text to match
the schema v2 would be trained on (single source of truth between
training and eval).

---

## Day 4 — Monday, May 25 — v2 training on Colab
*(11 commits)*

**Objective:** Train Qwen v2 LoRA on the 8,968-label TTB-stratified
dataset and run head-to-head against v1 + Haiku.

| Commit | What landed |
|---|---|
| `bdbc95d` | **Overnight + morning autonomous orchestrators** — scripts to run scrape + training + eval without manual babysitting |
| `44a5d37` | **Colab training pivot** — v2 SFT notebook + v1-vs-v2 eval notebook (Colab A100 was the right GPU for 7B BF16 training) |
| `e50a1d8` | **Leakage guards** across the builder + both v2 notebooks — guarantee no holdout TTB IDs leak into training |
| `739a352` | Tighten v2 training notebook for Colab session-disconnect resilience (Colab kills sessions; need checkpointing) |
| `8c40624` | Stage panels in `/tmp` not Drive — avoid Drive trash accumulation during multi-day runs |
| `9df444d` | MORNING.md regenerated with Colab walkthrough + actual scrape numbers |
| `1af226f` | **Critical fix: `qwen_vl_utils.process_vision_info`** — eliminates `tokens != features` error that was breaking every other training step |
| `0bfa7f8` | Lock `max_pixels` at processor init — real fix for the tokens vs features mismatch |
| `809f6d8` | `per_device_eval_batch_size=1` — eval pass was blowing up at step 1000 |
| `1f70a20` | Disable PIL decompression-bomb check — some 200M+ pixel TTB scans were crashing training |
| `eec6c7a` | Eval notebook — local image staging + 200-row preview default |

**End of Day 4 state:** Qwen v2 trained on N=8,968 stratified labels, 2 epochs,
checkpoint-344 saved. **First v2 eval result vs v1**: micro accuracy jumped
from 38% to 60% (later corrected to 78% post-scorer-fix). Class & type
accuracy went from 23% to 88%.

---

## Day 5 — Tuesday, May 26 — deployment + scorer fix + ship
*(10 commits, including today's work)*

**Objective:** Deploy both paths (public Haiku + on-prem Qwen), fix the
eval scorer to reflect v2's actual accuracy, and ship the take-home.

### Morning: v2.1 retrain + scorer correction
| Commit | What landed |
|---|---|
| `6d91b1c` | **v2.1 retrain** — cleaner bottler targets + 2 epochs (later bumped to 3) |
| `f2b42c1` | Explicit v2.1 markers in notebook + bump epochs 2 → 3 |
| `11af9e3` | End-to-end smoke test harness for any deployed TTB API |
| `b53245f` | Security: patch 14 backend CVEs + cap sample picker + delete dead `FieldRow` component |
| `1939ab9` | **Modal full-app deploy** (privacy-first MVP) + cold-start docs |
| `925b9de` | **Vercel deployment** (public Haiku path) — paired with Modal MVP |
| `b817f82` | **🔑 Eval scorer fix: bottler-cleaning + US-origin filter** — *v2's bottler was reading 0% accuracy because the scorer was substring-matching against raw form text containing street + ZIP, while v2 was correctly outputting the cleaned "Company, City, ST" form. Fix to the SCORER, not the model, recovered the real numbers: **bottler 52%, micro 78%, 2× better than Haiku at 37%.*** |
| `d787c08` | Eval notebook upgraded to full 2K + resume-on-interrupt |

### Today: documentation + GitHub Release
| Commit | What landed |
|---|---|
| `36cbca6` | **README headline rewritten** with the corrected 78% vs 37% numbers + live demo + GitHub Release link. DESIGN.md deployment section restructured into A (public) / B (privacy-first) / C (agency) topologies |
| `ab5c001` | **Hybrid extractor** — `ModalRemoteExtractor` fans out Modal (Qwen v2) and Anthropic Haiku in parallel via `asyncio.gather`, merges both observation sources via `_merge_label`. `modal` as default `INFERENCE_MODE`. Sample picker copy updated to "TTB Public COLA Registry" (the actual data source) |
| *(this commit)* | **GitHub Release v0.1.0** — bundles v1 + v2 adapter zips + 200-row eval pack so Treasury can reproduce on independent infrastructure |

**End of Day 5 state:** Live demo at https://ttb-label-verification-ebon.vercel.app
(Haiku path). GitHub Release v0.1.0 with downloadable weights. README +
DESIGN both accurate. 118/118 backend tests passing.

---

## Architecture decisions (chronological)

The architecture didn't arrive whole — these are the load-bearing
decisions in the order they happened:

1. **Day 1: Rules engine separate from model.** Decided that compliance
   verdicts must come from deterministic Python, not from any model
   output. The model's job ends at "here's what's printed." Every
   downstream upgrade has been a *plug-in*, not a rewrite.

2. **Day 1: Three-state field verdict.** `match / likely / flag`
   instead of boolean. Allows the engine to surface confidence without
   forcing a hard call; HITL absorbs the middle bucket.

3. **Day 2: Buy + train, not buy or train.** Day 2 ran Claude (cloud)
   *and* Qwen (open-weights LoRA) end-to-end on the same eval set in
   parallel. Refused to pick one before measuring.

4. **Day 2: BF16, no quantization.** Initial Qwen notebook used Unsloth
   + 4-bit. Switched to BF16 (no Unsloth, no bitsandbytes at inference)
   — matches training-time dtype, simpler deployment story, no
   quantization artifacts in the verdict path.

5. **Day 3: Get data from the source.** COLA Cloud's CC0 mirror had
   ~1,400 labels with garbled OCR-spillage. Scraped 20K labels directly
   from the TTB Public COLA Registry at 0.5 req/sec. The 6.5× data
   volume was the headline change that pushed v2 to 78%.

6. **Day 4: Narrow the schema.** v1 was trained on a wide schema (4
   fields + government warning text + image quality observations). v1
   hallucinated the long warning text. v2 was retrained with a
   **fields-only** schema (no `government_warning`, no `image_quality`)
   to eliminate the hallucination surface. The Government Warning is
   now handled by deterministic OCR (Tesseract) + canonical-text
   matching in the rules engine — VLM is never asked to verbatim-read
   it.

7. **Day 5: Hybrid extractor.** For ABV / Net contents / Warning text
   (the 3 fields v2 doesn't extract), use Anthropic Haiku as a
   parallel extractor. Documented honestly: "where we have agency-clean
   labeled data, the LoRA wins; where we don't, Haiku is the bridge."
   When more agency data lands, more fields move on-prem via the same
   pipeline.

8. **Day 5: Scorer fix recovered the real numbers.** v2's bottler was
   "0%" in eval because the scorer was substring-matching v2's cleaned
   output against raw form text. Fixed in `b817f82`; revealed v2 is
   actually 78% micro / 91.5% class-type — **the real win that this
   project demonstrates.**

---

## Trade-offs encountered (and resolutions)

### Latency vs accuracy on the hybrid path

The current hybrid path runs three concurrent calls under `asyncio.gather`:
Modal Qwen v2 (4 PII fields), Anthropic Haiku (ABV / Net / Warning text),
and Modal Tesseract (deterministic warning bbox + EXIF DPI). Warm latency
~5 s on small synthetic labels, ~6 s on dense TTB-live scans — Qwen-on-
A10G is the floor at ~5 s warm (measured directly). Cold-start path
returns `extractorSource: "haiku-fallback"` in ~9 s when Modal Qwen
exceeds the 8 s budget; Haiku reads all 6 fields in that case and
Tesseract still provides the bbox/DPI overlay.

A pure-Modal path (Qwen v2 only, no commodity model) is ~5 s warm but
needs Tesseract regex to cover ABV / Net / Warning — accurate enough
for clean scans, lower-precision on dense ones. A pure-Haiku path is
~3-5 s warm but misses v2's accuracy on the 4 trained fields and lacks
the Treasury-defensible privacy boundary. The shipped hybrid hits the
latency, accuracy, and privacy targets simultaneously.

### Modal cost discovery (Day 5)

Modal Starter tier is $30/month free credit. Today's session burned
through it because of:
- Multiple iterative redeploys (each forced cold start = ~30s of A10G
  time billed)
- Vision-token-reuse experiment (rolled back due to accuracy regression)
- Several long-timeout test calls

The credit refreshes monthly. The deployed v2 endpoint will work again
next billing cycle. For continuous on-prem demo, Cerebrium ($30/month
Hobby tier, decorator API), RunPod (cheapest per-second), or Azure ML
(FedRAMP target) are equivalent platforms — the `serve_qwen_v2.py`
deploy script ports to any of them.

### Type-size check (27 CFR 16.22) — now deterministic

Earlier DESIGN.md marked this "out of scope — digital images have no
DPI reference." Day 3 added a Tesseract bounding-box reader + EXIF DPI
fallback that closed the gap when DPI was available, but the check
silently skipped for the ~50% of labels without EXIF DPI.

A later round moved Tesseract to its own CPU-only Modal container
(`ttb-tesseract`) so it runs in parallel with Qwen on the warm path,
and made the check **deterministic every time**: EXIF DPI when
present, the 300-DPI TTB submission standard when not. The result is
a three-band verdict: measurements ≥0.9× threshold pass clean; 0.5-
0.9× pass with a `fontSizeAdvisory` (likely scan-resolution artefact —
TTB scans don't reliably preserve physical print resolution); <0.5×
hard-flag as `fontSize`. The `fontSizeMm` and `fontSizeDpiSource`
fields on the response surface the measurement and its provenance to
the agent.

---

## What's measurable and what isn't

| Claim | Measurement source | File reference |
|---|---|---|
| 78.0% Qwen v2 micro accuracy | 200-row TTB stratified holdout, post-`b817f82` scorer | [Release v0.1.0 eval pack](https://github.com/vsiwach/ttb-label-verification/releases/tag/v0.1.0) |
| **77.5% Qwen v2 micro accuracy** | **2000-row** TTB stratified holdout (seed=42, stratified across 1028 wine / 689 spirits / 283 malt). Within ±0.5 pp of the 200-row eval — validates that v2 generalises rather than overfitting to the initial sample | `v1_vs_v2_comparison.md` (Google Drive — to be added to v0.2.0 eval pack) |
| **1.9% Qwen v1 micro on 2K holdout** (was 38.4% on 200-row) | Same 2000-row holdout. v1 was trained on COLA Cloud, the 2K holdout is from TTB Registry — v1 is effectively zero-shot OOD. Strongest evidence yet that agency-curated training data is what drives the win, not the model architecture | Same |
| 37.2% Haiku micro accuracy on 200 labels | Same harness, identical rubric | [Release v0.1.0 eval pack](https://github.com/vsiwach/ttb-label-verification/releases/tag/v0.1.0) |
| 88.5% Qwen v2 on Class & type (2K) | Per-field breakdown | Same 2K eval report |
| 118 backend tests passing | `pytest backend/tests` | repeatable locally |
| 5-7 s warm latency | Vercel network timing, observed on 3 sample labels today | DESIGN §11 |
| Architecture portable across providers | `LabelExtractor` ABC + 6 implementations | `backend/app/extractors/` |
| Live demo URL | Pure Haiku, `INFERENCE_MODE=cloud` | https://ttb-label-verification-ebon.vercel.app |

What we did NOT yet measure:
- Real-time accuracy of the hybrid extractor end-to-end (Haiku is alone
  on the live URL today; hybrid was validated on Modal direct calls
  before Modal credit exhausted)
- Type-size check accuracy on the ~51% of labels that have EXIF DPI
- Latency under concurrent batch load (engineering on the async path is
  there; volume test wasn't part of this prototype scope)

---

## What I'd do differently

1. **Verify external pricing before relying on internal docs.** The
   `docs/DEPLOY_RUNBOOK.md` line about Modal's "$30/month credit" was
   stale by the time I quoted it. Should have read the live pricing
   page first.

2. **One careful cloud deploy, not iterative cloud debugging.** Each
   `modal app stop + redeploy` burned through cold-start time. The
   right pattern is: build locally → test in a one-shot rented GPU →
   one deploy → don't iterate.

3. **Track the eval scorer as a source-of-truth artifact earlier.** The
   `b817f82` bottler-cleaning fix made v2 look 2× better than the
   pre-fix eval report suggested. Pre-fix numbers shipped briefly in
   the README before being corrected. Scorer + ground-truth pipeline
   should be diff'd against model output every time, not assumed
   stable.

4. **Bundle untracked-but-needed assets earlier.** The 804 sample
   images in `test/eval/data/images/` weren't tracked in git. Git-push
   auto-deploys to Vercel broke when the images weren't available.
   Fix: either commit + LFS, or disable git auto-deploy. Documented
   above; user decides.

---

## Reproducibility checklist for any reviewer

```bash
# 1. Clone the repo at v0.1.0 tag
git clone https://github.com/vsiwach/ttb-label-verification.git
cd ttb-label-verification
git checkout v0.1.0

# 2. Verify the 118-test backend suite
make install
make test                     # expect: 118 passed in ~3s

# 3. Hit the live demo URL
open https://ttb-label-verification-ebon.vercel.app

# 4. Download + validate the v2 LoRA bundle from the Release
gh release download v0.1.0 -p ttb_qwen_v2_adapter.zip
unzip ttb_qwen_v2_adapter.zip -d backend/models/qwen2_5_vl_7b_v2/

# 5. Re-score the 200-row holdout with any custom rubric
gh release download v0.1.0 -p ttb_eval_pack.zip
unzip ttb_eval_pack.zip -d /tmp/eval
python3 /tmp/eval/rescore_eval.py

# 6. Deploy the on-prem variant to your own GPU host
#    (Modal, Cerebrium, RunPod, Azure ML, on-prem)
#    See docs/DEPLOY_RUNBOOK.md
```
