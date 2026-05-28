# Vercel deployment — production three-way fan-out

Treasury-facing demo URL on Vercel. Frontend served from CDN edge,
FastAPI backend runs as a Python serverless function. In the shipping
configuration (`INFERENCE_MODE=modal`) the function fans out three
parallel calls via `asyncio.gather`: Modal Qwen v2 LoRA on A10G (the
4 PII-class fields), Anthropic Haiku 4.5 (the public-text Government
Warning verbatim + ABV + net contents), and Modal Tesseract CPU
(deterministic warning bbox + EXIF DPI for the 27 CFR 16.22 size check).
`INFERENCE_MODE=cloud` is also supported and skips Modal entirely
(Haiku alone) — useful for outage-mode demos.

For the fully on-prem variant (no external API calls at all), see
`archive/modal_deploy/serve_full_app.py` (preserved in the archive
since the live deployment runs the hybrid) and the Modal section
of `README.md`.

## What gets deployed

```
┌─ vercel.json ──── routes config (rewrites /api/* to function, rest to dist/index.html)
├─ api/index.py ── Vercel serverless entrypoint; imports app.main:app
├─ api/requirements.txt ── pinned deps for the function (matches backend/requirements.txt)
├─ backend/app/* ── same backend code; uploaded as a sibling to api/
└─ dist/ ────────── built React frontend (npm run build)
```

## Prerequisites

1. Vercel CLI installed: `npm i -g vercel` (or use the dashboard)
2. Logged in: `vercel login`
3. Linked to a project: `vercel link` (first time only)

## One-time setup — env vars

Set these in the Vercel dashboard (Project → Settings → Environment Variables) **or** via CLI:

```bash
vercel env add ANTHROPIC_API_KEY    production   # paste your key (sk-ant-...)
vercel env add INFERENCE_MODE       production   # value: modal (production); cloud = Haiku-only fallback
vercel env add CLOUD_MODEL          production   # value: claude-haiku-4-5
vercel env add MODAL_ENDPOINT_URL   production   # Qwen v2 endpoint from `make modal-deploy-v2`
vercel env add MODAL_TESSERACT_URL  production   # Tesseract endpoint from `modal deploy serve_tesseract.py`
vercel env add MODAL_HEALTH_URL     production   # used by the UI heartbeat to pre-warm Modal
vercel env add MODAL_TIMEOUT        production   # value: 8 (seconds; Qwen-timeout triggers haiku-fallback)
vercel env add CORS_ORIGINS         production   # value: https://your-project.vercel.app
```

Pre-set defaults from `vercel.json` (INFERENCE_MODE, CLOUD_MODEL) get
overwritten by these. `ANTHROPIC_API_KEY` must be set manually — it's
never committed. The two `MODAL_*_URL` vars come from the Modal deploys
in `docs/DEPLOY_RUNBOOK.md`.

## Deploy

```bash
# Preview deploy (free, gets a unique URL like ttb-xxxx.vercel.app)
vercel

# Production deploy
vercel --prod
```

After the deploy, Vercel prints the URL. Run the smoke test against
it immediately:

```bash
make smoke-deployed URL=https://your-project.vercel.app
```

If smoke passes, the URL is safe to send Treasury.

## Function size + latency notes

- Vercel @vercel/python has a 250 MB unzipped function size limit. Our
  backend (FastAPI + Pillow + anthropic) is well under — ~80 MB.
- Cold start: 200-500 ms (Python serverless cold start, much faster
  than Modal's 30-60 s because no GPU/model to load)
- Warm request: ~4.5-6 s total (function fans out Modal Qwen +
  Anthropic Haiku + Modal Tesseract via `asyncio.gather`; latency is
  the slowest of the three legs). UI pre-warm (`/health` on mount +
  every 4 min) keeps the Modal containers above the 5-min scaledown.
- maxDuration is 30 s — generous given our typical 5 s warm latency,
  but worth knowing if batch verification ever blows up

## What the user sees

Treasury opens `https://your-project.vercel.app` →
- Frontend loads instantly (CDN edge); UI fires `GET /health` to pre-warm Modal
- They pick a sample or upload their own label
- Click Verify
- Serverless function fans out Modal Qwen + Haiku + Modal Tesseract in parallel; returns the merged verdict (~4.5-6 s warm)
- ResultPage renders with bucket + per-field statuses + 27 CFR citations

## Privacy trade-off (Treasury will ask)

In the production three-way fan-out, the split is intentional:
- **Modal Qwen LoRA** (container we control) receives the image for brand / class / bottler / country extraction — these never traverse a third-party API.
- **Anthropic Haiku** receives the image to read the Government Warning verbatim text (fixed by 27 CFR 16.21, public, non-PII) plus the two small numerics ABV and net contents.
- **Modal Tesseract** (CPU container) receives the image for a deterministic bbox + EXIF DPI extraction — no LLM in the loop.

For TTB submissions that must keep ALL fields inside a single accreditation boundary, switch to the fully on-prem deployment in `archive/modal_deploy/serve_full_app.py` (preserved as an alternative topology — not the active deploy) — no Anthropic call at all; Qwen v2 LoRA covers all 6 fields with reduced accuracy on the 2 non-trained ones until more agency data lands.

## Cost

- Vercel: free tier covers ~100K function invocations/month + 100 GB
  bandwidth. Demo / TTB pilot will not hit any limits.
- Modal: A10G Qwen container is scale-to-zero at ~$0.001/req warm; the Tesseract CPU container is in the noise.
- Anthropic: claude-haiku-4-5 vision is ~$0.001/image. 1000 labels =
  ~$1. Well under $50/mo even at sustained agent use.

Total: realistically **$0-50/month** for the full Vercel + Modal path.
