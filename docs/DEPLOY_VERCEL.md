# Vercel deployment — public Haiku path

Treasury-facing demo URL on Vercel. Frontend served from CDN edge,
FastAPI backend runs as a Python serverless function, label extraction
goes to Anthropic's Haiku API.

This is the "public path" deployment. For the privacy-first variant
(no external API calls), see `backend/modal_deploy/serve_full_app.py`
and the Modal section of `README.md`.

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
vercel env add ANTHROPIC_API_KEY production   # paste your key (sk-ant-...)
vercel env add INFERENCE_MODE  production     # value: cloud
vercel env add CLOUD_MODEL     production     # value: claude-haiku-4-5
vercel env add CORS_ORIGINS    production     # value: https://your-project.vercel.app
```

Pre-set defaults from `vercel.json` (INFERENCE_MODE, CLOUD_MODEL) get
overwritten by these. `ANTHROPIC_API_KEY` must be set manually — it's
never committed.

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
- Warm request: 3-5 s total (~200 ms function execution + ~3-5 s
  Anthropic round-trip)
- maxDuration is 30 s — generous given our typical 5 s warm latency,
  but worth knowing if batch verification ever blows up

## What the user sees

Treasury opens `https://your-project.vercel.app` →
- Frontend loads instantly (CDN edge)
- They pick a sample or upload their own label
- Click Verify
- Serverless function fires, calls Haiku, returns the verdict (3-5 s)
- ResultPage renders with bucket + per-field statuses + 27 CFR citations

Identical UX to the Modal privacy-first path. Same routes, same
endpoints, same `VerificationResult` JSON.

## Privacy trade-off (Treasury will ask)

This deployment sends label images to Anthropic's API for extraction.
Anthropic's data usage policy: API inputs are not used for training
unless explicitly opted in. But the image bytes do leave the Vercel
function during the API call.

For TTB submissions that contain PII or that must stay within FedRAMP
boundaries, use the Modal deployment instead — that path uses an
on-prem Qwen LoRA and makes no external API calls.

## Cost

- Vercel: free tier covers ~100K function invocations/month + 100 GB
  bandwidth. Demo / TTB pilot will not hit any limits.
- Anthropic: claude-haiku-4-5 vision is ~$0.001/image. 1000 labels =
  ~$1. Well under $50/mo even at sustained agent use.

Total: realistically **$0-50/month** for the full Vercel path.
