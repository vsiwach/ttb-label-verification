# TTB Label Verification

**AI-assisted compliance review for U.S. Treasury TTB alcohol labels.**

A web app + backend that takes a label image + the applicant's COLA form data,
extracts the label's printed fields with a vision-language model, and verifies
the result against **27 CFR Parts 4 / 5 / 7** (mandatory fields) and **Part 16**
(the Government Warning) using a deterministic rules engine that cites the
regulation behind every decision.

```
         "The AI reads. The rules decide."
        ─────────────────────────────────────
```

The model only ever reports what it sees + how confident. A hand-coded Python
rules engine makes every match / likely / flag decision and attaches the
exact 27 CFR citation. This keeps the legal logic deterministic, auditable,
and stable across model upgrades.

---

## Headline result

| Metric | Claude Vision | Qwen2.5-VL-7B LoRA (ours) |
|---|---|---|
| Field extraction accuracy | 69.83% | **63.41%** (within 6pp) |
| **Government Warning false-flag rate** | 26.67% | **25.00% — beats Claude** |
| Latency (Modal A10G, warm) | n/a (API) | **3-5 s/image** |
| Cost per 1000 labels | $5 (cloud API) | **~$1 (Modal scale-to-zero)** |

Full apples-to-apples analysis: [`test/eval/QWEN_VS_CLAUDE.md`](test/eval/QWEN_VS_CLAUDE.md)

---

## System architecture

```
       ┌──────────────────────────────────────────────────────────────────────────┐
       │  Browser — React + Vite (Vercel-deployable static bundle)                │
       │                                                                          │
       │   /upload  ──►  /result   ──►  /review                                   │
       │      │              │              │                                     │
       │      ▼              ▼              ▼                                     │
       │   dropzone     fields + warning   keyboard "Confirm next" queue          │
       │   + form       + verdict + HITL   (for batch triage)                     │
       │      │              decision                                             │
       │      ▼              panel                                                │
       │   /batch  ──► triage dashboard (grouped by verdict bucket)               │
       └────────────────────────────────┬─────────────────────────────────────────┘
                                        │ HTTPS multipart
                                        │ POST /api/verify  (single)
                                        │ POST /api/verify-batch (N images)
                                        ▼
       ┌──────────────────────────────────────────────────────────────────────────┐
       │  Backend — FastAPI + Pydantic                                            │
       │                                                                          │
       │  ┌─────────────────┐  ┌────────────────┐  ┌──────────────────────────┐  │
       │  │ image_pipeline  │  │ LabelExtractor │  │  rules engine (no AI)    │  │
       │  │ • validate      │─►│ (swappable)    │─►│  • field_match (3-state) │  │
       │  │ • measure       │  │ • mock         │  │  • govt_warning (16.21/  │  │
       │  │ • legibility    │  │ • cloud Claude │  │     16.22 + verbatim)    │  │
       │  │ • crop store    │  │ • claude-code  │  │  • mandatory_fields      │  │
       │  └─────────────────┘  │ • onprem (OCR) │  │  • net_contents (mL/oz)  │  │
       │                       │ • sft (Qwen)   │  │  • citations             │  │
       │                       │ • modal-remote │  └─────────┬────────────────┘  │
       │                       └────────────────┘            │                   │
       │                                                     ▼                   │
       │                              ┌────────────────────────────────────┐     │
       │                              │  VerificationResult                │     │
       │                              │    fields[]  (match/likely/flag)   │     │
       │                              │    governmentWarning (verbatim ok?)│     │
       │                              │    + regulation citations everywhere│    │
       │                              └────────────────────────────────────┘     │
       └──────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                          group_for(result) → "auto-pass" / "needs-confirm" / "needs-review"
```

**Why this matters:** the rules engine is the durable value. Swap Claude → Qwen
→ Phi-3.5-vision → next-year-frontier-model — the engine stays the same. Every
verdict is deterministic, auditable, and citable.

---

## User workflow

### Single label (with Human-in-the-Loop)

```
  ┌────────┐                                                       ┌─────────────────┐
  │ Agent  │                                                       │  HITL decision  │
  └───┬────┘                                                       └────────┬────────┘
      │                                                                     │
      │  1. Drop image                                                      │
      │  2. Enter/paste COLA application data                               │
      │  3. Submit                                                          │
      ▼                                                                     │
  ┌─────────────────┐                                                       │
  │ Client downsizes│                                                       │
  │ → 2MP JPEG      │                                                       │
  └────────┬────────┘                                                       │
           │ POST /api/verify (multipart)                                   │
           ▼                                                                │
  ┌────────────────────────────────────────────────────────────┐            │
  │  Backend: assess image → extract fields → run rules engine │            │
  └─────────────────────────┬──────────────────────────────────┘            │
                            │ VerificationResult                            │
                            ▼                                               │
        ┌─────────────────────────────────┐    ┌──────────────────────────┐ │
        │  /result                        │    │  GREEN  auto-pass        │ │
        │  ┌──────────┐ ┌──────────────┐  │    │  ▸ "Approve" (1 click)   │◄┘
        │  │  label   │ │  per-field   │──┼────┤                          │
        │  │  image   │ │  cards       │  │    │  AMBER  needs-confirm    │
        │  │  +       │ │  + warning   │──┼────┤  ▸ "Confirm" or          │
        │  │  evidence│ │  panel       │  │    │    "Override" (~15 sec)  │
        │  │  crops   │ │  + verdict   │  │    │                          │
        │  └──────────┘ └──────────────┘  │    │  RED  needs-review       │
        └─────────────────────────────────┘    │  ▸ Read engine flag,     │
                                               │    inspect image,        │
                                               │    "Approve with note"   │
                                               │    or "Request image"    │
                                               │    or "Escalate"         │
                                               └──────────────────────────┘
```

**Five HITL design principles baked into the engine** (so the agent always has signal, never noise):

1. **Engine is conservative.** When in doubt, route UP (auto-pass → needs-confirm → needs-review). Never down.
2. **Low confidence demotes "match".** Any field below 0.60 confidence gets demoted to `likely` → forces agent attention.
3. **Missing fields don't auto-fail.** COLAs are multi-image; a missing field becomes `likely` with a note ("may be on another panel").
4. **Engine never explains away a warning.** If `casing_all_caps=false`, the engine flags it regardless of how confident the extraction was.
5. **Every status carries a citation.** Not "this is flagged" but "this is flagged under 27 CFR 4.32(a)(1)".

### Batch upload (with triage)

```
   Agent drops 250 label images
                │
                ▼
   POST /api/verify-batch
                │
                ▼
   ┌─────────────────────────────────────┐
   │  asyncio.Semaphore(N) bounded       │
   │  concurrent fan-out:                │
   │                                     │
   │  image1 → extractor → engine ──┐    │
   │  image2 → extractor → engine ──┤    │
   │  image3 → extractor → engine ──┼─►  list[BatchItemResult]
   │   ...                          │    │
   │  imageN → extractor → engine ──┘    │
   │                                     │
   │  ⚠ per-item failure isolated —      │
   │  bad item → group=needs-review,     │
   │  rest of batch returns normally     │
   └─────────────────────────────────────┘
                                         │
                                         ▼
        ┌──────────────────────────────────────────────────┐
        │  /batch dashboard                                │
        │                                                  │
        │  ┌────────────┐ ┌──────────────┐ ┌────────────┐  │
        │  │ auto-pass  │ │ needs-confirm│ │needs-review│  │
        │  │    125     │ │     80       │ │     45     │  │
        │  └────┬───────┘ └──────┬───────┘ └─────┬──────┘  │
        │       │                │                │        │
        └───────┼────────────────┼────────────────┼────────┘
                │                │                │
                ▼                ▼                ▼
          one-click            click into        click into
          approve all          /review queue     /review queue
          (green)              (keyboard:        (substantive
                               Confirm/Skip/     agent decision
                               Override)         per label)
```

**Agent productivity** — for a 250-label batch under realistic Qwen-LoRA accuracy:

| Bucket | Typical share | Time / item | Subtotal |
|---|---|---|---|
| auto-pass | ~50% (125 items) | ~5 sec confirm | 10 min |
| needs-confirm | ~30% (80 items) | ~15 sec glance | 20 min |
| needs-review | ~20% (45 items) | ~3 min substantive | 135 min |
| **Total** | | | **~2.75 hr vs ~12 hr unassisted** |

---

## Inference modes (six interchangeable backends)

Set `INFERENCE_MODE` in `backend/.env`. All implement the same `LabelExtractor` interface — the rules engine doesn't care which one is running.

```
                       INFERENCE_MODE selects one of these:
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │                                                                              │
   │  mock          Deterministic fixtures, no auth, no network                   │
   │  ─────         use case: local dev, CI gate, frontend wiring tests           │
   │                                                                              │
   │  cloud         Anthropic API (claude-sonnet-4-6 default; haiku/gemini opt.)  │
   │  ─────         use case: best raw accuracy, $0.005/label, ~8s latency        │
   │                                                                              │
   │  claude-code   Routes through `claude` CLI; bills against Max subscription   │
   │  ───────────   use case: dev/demo without API credit burn, ~30s latency      │
   │                                                                              │
   │  onprem        Tesseract OCR + optional Phi-3.5-vision via Ollama            │
   │  ──────        use case: air-gapped agency networks, no outbound calls       │
   │                                                                              │
   │  sft           Locally-loaded Qwen2.5-VL-7B LoRA (BF16, transformers+peft)   │
   │  ───           use case: on-prem GPU; matches training-time dtype; 3-10s     │
   │                                                                              │
   │  modal         Calls a Modal-hosted Qwen endpoint over HTTPS                 │
   │  ─────         use case: production demo, scale-to-zero, $0 idle, ~3-5s      │
   │                                                                              │
   └──────────────────────────────────────────────────────────────────────────────┘
```

| Mode | Latency | Cost | GPU needed locally? | Supply chain |
|---|---|---|---|---|
| `mock` | <100ms | $0 | no | n/a |
| `cloud` | ~8s | ~$0.005/label | no | US (Anthropic) |
| `claude-code` | ~30s | flat (Max sub) | no | US |
| `onprem` | varies | $0 (existing HW) | yes (for VLM tier) | US (Microsoft Phi) |
| `sft` | 3-10s | $0 marginal | yes (≥16 GB VRAM) | China (Qwen base) — reference |
| `modal` | 3-5s warm / 30-60s cold | ~$0.001/req, $0 idle | no | China (Qwen base) — reference |

See [`docs/MODEL_PRIORITY.md`](docs/MODEL_PRIORITY.md) for the strategic framework.

---

## Configurability — full env var matrix

All configuration is in `backend/.env` (see `backend/.env.example`).

```
┌─────────────────────────┬─────────────────────────────────────────────────────────┐
│ Env var                 │ Meaning                                                 │
├─────────────────────────┼─────────────────────────────────────────────────────────┤
│ INFERENCE_MODE          │ mock | cloud | claude-code | onprem | sft | modal       │
│ CORS_ORIGINS            │ Comma-sep list of allowed frontend origins              │
│                         │                                                         │
│ ── cloud mode ──        │                                                         │
│ CLOUD_PROVIDER          │ anthropic | openai | google                             │
│ CLOUD_MODEL             │ e.g. claude-sonnet-4-6, gemini-2.5-flash                │
│ ANTHROPIC_API_KEY       │ provider key (only one needed, matches CLOUD_PROVIDER)  │
│ OPENAI_API_KEY          │                                                         │
│ GOOGLE_API_KEY          │                                                         │
│                         │                                                         │
│ ── onprem mode ──       │                                                         │
│ ONPREM_VLM_URL          │ Ollama / vLLM endpoint (default localhost:11434)        │
│ ONPREM_VLM_MODEL        │ e.g. phi3.5                                             │
│                         │                                                         │
│ ── sft mode ──          │                                                         │
│ SFT_MODEL_DIR           │ Path to bundle (default backend/models/qwen2_5_vl_7b)   │
│                         │                                                         │
│ ── modal mode ──        │                                                         │
│ MODAL_ENDPOINT_URL      │ URL from `modal deploy` output                          │
│ MODAL_TIMEOUT           │ HTTP timeout in seconds (default 60)                    │
└─────────────────────────┴─────────────────────────────────────────────────────────┘

Frontend has ONE env var (in .env.local at repo root):

  VITE_API_BASE_URL        Backend base URL (e.g. http://localhost:8000/api).
                           If empty → frontend uses mock data, no backend needed.
```

---

## Deployment architectures

### Architecture A — local dev (no GPU)

```
   ┌────────────────┐     ┌──────────────────────┐
   │  npm run dev   │────►│ uvicorn (mock mode)  │
   │  localhost:5173│     │ localhost:8000       │
   └────────────────┘     └──────────────────────┘
   No GPU. No API keys. Mock fixtures. <100ms per request.
   Used for: frontend dev, CI tests.
```

### Architecture B — cloud (Claude API path)

```
   ┌────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
   │  Vercel        │────►│ Render / Fly.io      │────►│ Anthropic API    │
   │  (frontend)    │HTTPS│ (FastAPI cloud mode) │HTTPS│ claude-sonnet-4-6│
   └────────────────┘     └──────────────────────┘     └──────────────────┘
   No GPU. ~$0.005/label. ~8s per request.
   Used for: demo, prototype phase, low-volume production.
```

### Architecture C — Modal-served SFT (recommended production demo)

```
   ┌────────────────┐    ┌──────────────────────┐    ┌────────────────────────┐
   │  Vercel        │───►│ Render / Fly.io      │───►│ Modal (A10G, scale-to- │
   │  (frontend)    │    │ (FastAPI modal mode) │    │ zero, BF16 Qwen + LoRA)│
   └────────────────┘    │                      │    │                        │
                         │ rules engine here    │    │ inference here         │
                         │ (no GPU needed)      │    │ (auto-suspends when    │
                         └──────────────────────┘    │  idle, $0/hr)          │
                                                     └────────────────────────┘

   ~3-5s warm / ~30-60s cold. $0 idle / ~$0.001/req active.
   Best for: TTB pitch demo, low-traffic pilots.
   Runbook: docs/DEPLOY_RUNBOOK.md
```

### Architecture D — agency on-prem (FedRAMP / Azure Government)

```
           ╔═══════════════════════════════════════════════════════╗
           ║       Agency network boundary (Azure Gov VNet)        ║
           ║                                                       ║
           ║  ┌──────────────┐     ┌──────────────────────────┐    ║
           ║  │ Frontend     │────►│ Backend (sft mode)       │    ║
           ║  │ (Azure SWA)  │     │ rules engine + extractor │    ║
           ║  └──────────────┘     │ on agency GPU (NC-series)│    ║
           ║                       └──────────────────────────┘    ║
           ║                                                       ║
           ║   No outbound calls. Everything inside accreditation. ║
           ║                                                       ║
           ╚═══════════════════════════════════════════════════════╝

   For sensitive workloads + FedRAMP requirements.
   Same code as Architecture C; deployment topology changes only.
   See: PRD §7.2 (production architecture).
```

---

## Quick start

### Local dev — Claude Code CLI (no API spend, ~2 min)

The default local path uses the `claude` CLI (your Max subscription), so you can
run unlimited verifications without burning API tokens. Slower per call (~30 s)
but free.

```bash
make install         # creates backend/.venv
make test            # 114 backend tests, ~3 s
make serve           # backend on :8000 via Claude Code CLI

# in another terminal
VITE_API_BASE_URL=http://localhost:8000/api npm run dev
# open http://localhost:5173
```

Pre-requisite: `claude` CLI installed and logged in (one time: `brew install claude` / login via the desktop app).

### Local dev — paid Anthropic API (~10 s per call)

```bash
cp backend/.env.example backend/.env
# edit backend/.env: set ANTHROPIC_API_KEY=sk-ant-...
make serve-api       # cloud mode, ~8-12 s per verification
```

### Production — Qwen LoRA on Modal (~3-5 s per call, scale-to-zero)

```bash
backend/.venv/bin/pip install modal
backend/.venv/bin/modal token new
make modal-upload-adapter    # uploads LoRA weights (~190 MB) to Modal volume
make modal-deploy            # builds container + deploys
# copy the printed URL into backend/.env as MODAL_ENDPOINT_URL
make serve-modal
```

Full deployment runbook: [`docs/DEPLOY_RUNBOOK.md`](docs/DEPLOY_RUNBOOK.md)

---

## Real-data testing — the UAT pack

The repo includes 67 real TTB-approved labels from the COLA Cloud free sample
(CC0). Two ways to use them:

### A. Pre-paired picker (fastest)

`/upload` shows a "Load a sample COLA" picker with ~10 curated reals. Click one
→ form pre-fills + label image loads into the dropzone → click Verify. The
verdict pill on each button is the *typical* engine output for that label
(Claude is non-deterministic, so actual runs may land ±1 bucket).

### B. Standalone UAT pack — for upload + batch workflows

For the realistic production workflow where the label image and the
application data arrive separately:

```bash
make uat-pack   # writes test/eval/uat_pack/{labels/, applications.csv}
```

That produces:

- `test/eval/uat_pack/labels/` — 67 `.webp` label images (renamed by brand + ttb_id)
- `test/eval/uat_pack/applications.csv` — paired application data, including the `expectedOutcome` column

Then in the browser:

- **Single upload**: pick any row in the CSV, paste into `/upload` form, drag the matching label image
- **Batch**: drag many labels into `/batch` at once, optionally paste one shared application

### C. Cross-verify the engine against all reals

```bash
make serve        # in one terminal
make audit-reals  # in another — runs all 67 through /api/verify (concurrency 4)
                  # ~12-20 min on claude-code path; ~3-5 min on modal
```

Outputs:
- `test/eval/REAL_AUDIT.md` — human-readable summary + per-row table
- `test/eval/real_audit.json` — machine-readable for tooling

---

## Routes & pages

| Route | Purpose |
|---|---|
| `/upload` (and `/`) | Drag a label image, downscale on-device, enter the application data, submit |
| `/result` | Side-by-side label + field verdicts, Government Warning panel, evidence crops, HITL decision actions |
| `/batch` | Drop hundreds of labels; triage dashboard groups them by verdict |
| `/review` | Keyboard-driven "Confirm next" flow — step through attention items in seconds |
| `/system` | Architecture explainer, 3-state status model, TypeScript API contract |
| `/styleguide` | Component library demo |
| `/api-demo` | Live request/response viewer for the streaming mock |

---

## The 3-state status model

Every field verdict pairs **color + icon + text** — never color alone (Section 508 compliance).

```
   ✓  GREEN   "Match"                       (auto-pass-able)
   ⚠  AMBER   "Likely match — confirm"      (one-click resolve)
   ✗  RED     "Flag — review"               (substantive issue, agent decides)
```

Verdict bucketing on the result level:

```
                ┌──────────────────────────────────────┐
                │  group_for(VerificationResult)       │
                │                                      │
                │   any field = flag    →  needs-review│
                │   warning issue       →  needs-review│
                │   any field = likely  →  needs-confirm│
                │   else                →  auto-pass   │
                └──────────────────────────────────────┘
```

This logic is **identical on the frontend** (`src/api/ttbRules.ts::groupFor`) **and the backend** (`backend/app/models.py::group_for`).

---

## Test surface

```
   115 backend tests   →   2.9 sec   →   all green
   ─────────────────────────────────────────────────
   • 91 unit tests       (field_match, government_warning, net_contents,
                          mandatory_fields, image_pipeline, engine)
   • 10 HTTP endpoint    (TestClient against /api/verify + /verify-batch)
   • 27 SFT-specific     (parser recovery, field aliasing, confidence
                          coercion, manifest dispatch)
   •  5 SFT replay e2e   (stubbed Qwen output → ExtractedLabel → rules
                          engine → expected VerificationResult)
   •  5 Modal remote     (mocked HTTP path: happy / unparseable / 500 /
                          endpoint-error / missing URL)
   •  1 synthetic CI gate (boots mock backend, runs 9 hand-crafted
                          violation fixtures, asserts 100%)
```

```bash
make test           # full suite
make eval-synth     # deterministic 100%-pass CI gate
make eval-real      # real-data eval against test/eval/data (requires running backend)
make eval-replay-qwen     # apples-to-apples score from a Qwen JSONL (see notebooks/)
make eval-compare-all     # side-by-side table of all model reports
```

---

## Documentation index

| Document | What's inside |
|---|---|
| [`docs/PRD_TTB_Label_Verification.md`](docs/PRD_TTB_Label_Verification.md) | Product requirements doc — agent personas, evasion patterns, regulatory ground truth |
| [`docs/DESIGN.md`](docs/DESIGN.md) | End-to-end design doc + PRD alignment matrix (honest divergence accounting) |
| [`docs/COVERAGE.md`](docs/COVERAGE.md) | Per-field / per-rule coverage matrix — what the engine decides vs flags for human review |
| [`docs/MODEL_PRIORITY.md`](docs/MODEL_PRIORITY.md) | Model selection framework (Qwen vs InternVL3 vs Donut vs Claude) |
| [`docs/DEPLOY_RUNBOOK.md`](docs/DEPLOY_RUNBOOK.md) | Step-by-step Modal deployment (~30 min from clean checkout to live endpoint) |
| [`docs/TTB_API_Contract_Reference.md`](docs/TTB_API_Contract_Reference.md) | API contract: request/response schemas, error codes, examples |
| [`test/eval/QWEN_VS_CLAUDE.md`](test/eval/QWEN_VS_CLAUDE.md) | Apples-to-apples eval result + strategic implications |
| [`backend/README.md`](backend/README.md) | Backend-specific quick start + inference mode details |
| [`notebooks/README.md`](notebooks/README.md) | SFT training + eval notebooks (Colab-runnable) |
| [`test/EVALUATION.md`](test/EVALUATION.md) | Evaluation methodology |

---

## Repository layout

```
ttb-label-verification/
├── README.md                          ← you are here
│
├── src/                               ← React + Vite + TS frontend
│   ├── api/                              client.ts, types.ts, mockData.ts, ttbRules.ts
│   ├── components/                       11 reusable primitives
│   ├── pages/                            7 routes
│   ├── store/                            local state
│   └── utils/downscaleImage.ts           client-side 2MP downscale + JPEG re-encode
│
├── backend/                           ← Python 3.13 + FastAPI + Pydantic
│   ├── app/
│   │   ├── main.py                       FastAPI app + 4 endpoints
│   │   ├── models.py                     Pydantic schemas + group_for()
│   │   ├── image_pipeline.py             Pillow validation + ephemeral crop store
│   │   ├── extractors/                   6 swappable LabelExtractor implementations
│   │   ├── rules/                        Deterministic 27 CFR engine (no AI)
│   │   └── constants.py                  VERBATIM_GOVERNMENT_WARNING canonical text
│   ├── modal_deploy/serve_qwen.py        Qwen-on-Modal production endpoint
│   ├── tests/                            115 tests
│   └── models/qwen2_5_vl_7b/             LoRA weights (gitignored, 190 MB)
│
├── notebooks/                         ← SFT training + eval (Colab)
│   ├── sft_qwen2_5_vl.ipynb              Qwen training (BF16)
│   ├── sft_internvl3_2b.ipynb            InternVL3 training (alternative)
│   ├── sft_donut_v2.ipynb                Donut training (smallest model)
│   ├── eval_{qwen,internvl3,donut}_drive.ipynb   Inference notebooks
│   └── _apply_baselines.py               Propagates canonical SYSTEM_PROMPT
│
├── test/
│   ├── eval/                             Real-data eval harness + reports
│   └── synthetic/                        9 hand-crafted violation fixtures (CI gate)
│
└── docs/                              ← see Documentation index above
```

---

## License + sources

- **Code**: MIT
- **Training data**: COLA Cloud free sample (https://colacloud.us, CC0)
- **Regulatory ground truth**: 27 CFR Parts 4, 5, 7, 16 (public domain, eCFR)
- **Base models**: Qwen/Qwen2.5-VL-7B-Instruct (Apache 2.0, Alibaba), Claude Vision (Anthropic API)

This is a **prototype**. For production deployment in TTB / Treasury context, see [PRD §7.2 (production architecture)](docs/PRD_TTB_Label_Verification.md#72-production-architecture) and [PRD §13 (phased roadmap)](docs/PRD_TTB_Label_Verification.md#13-phased-roadmap).
