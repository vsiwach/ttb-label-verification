# Deployment Runbook — Qwen2.5-VL v2 + Tesseract on Modal

End-to-end deployment of the two Modal services that back the production
`INFERENCE_MODE=modal` fan-out: the BF16-trained Qwen v2 LoRA (GPU,
A10G) and the deterministic Tesseract bbox + EXIF DPI service (CPU).
Total time: **~30 min** the first time, ~5 min for redeploys.

## Prerequisites (one-time, ~10 min)

1. **Modal account** (free tier covers demo usage; $30/month credit auto-applied)

   ```bash
   pip install modal
   modal token new      # opens browser, authenticate
   ```

2. **Adapter weights on disk** at `backend/models/qwen2_5_vl_7b/adapter/`.

   Verify:
   ```bash
   ls -lh backend/models/qwen2_5_vl_7b/adapter/adapter_model.safetensors
   # Expect ~180-190 MB
   ```

   If missing, unzip the bundle:
   ```bash
   mkdir -p backend/models/qwen2_5_vl_7b
   unzip ~/Downloads/ttb_sft_qwen2_5_vl_7b.zip -d backend/models/qwen2_5_vl_7b/
   ```

## Step 1 — Upload the LoRA adapter to Modal (~2 min)

```bash
make modal-upload-adapter
```

Behind the scenes this runs:
```
modal volume create ttb-qwen-adapter         # creates if missing, no-op otherwise
modal volume put --force ttb-qwen-adapter \
    backend/models/qwen2_5_vl_7b/adapter /adapter
```

You should see:
```
Uploading file: backend/models/qwen2_5_vl_7b/adapter/adapter_model.safetensors (181.6MB)
Uploading file: backend/models/qwen2_5_vl_7b/adapter/adapter_config.json (1.1kB)
...
Volume 'ttb-qwen-adapter' updated.
```

To verify:
```bash
modal volume ls ttb-qwen-adapter
```

## Step 2 — Deploy the Qwen v2 inference app (~5 min first time, ~30 s subsequent)

```bash
make modal-deploy-v2
```

Behind the scenes:
```
modal deploy backend/modal_deploy/serve_qwen_v2.py
```

This is the production app (`ttb-qwen-extractor-v2`). `make modal-deploy`
is still wired to the v1 `serve_qwen.py` for legacy / head-to-head eval;
the live production stack uses v2.

First deploy builds the Docker image (transformers, peft, torch — ~3 GB).
Modal caches the image, so subsequent deploys are fast.

When done, Modal prints something like:

```
✓ App deployed in 287.5s! 🎉

View Deployment: https://modal.com/apps/<your-user>/ttb-qwen-extractor-v2
Endpoint: https://<your-user>--ttb-qwen-extractor-v2-extract-web.modal.run
```

**Copy that endpoint URL.**

## Step 3 — Deploy the Tesseract bbox + DPI service (~3 min first time)

```bash
modal deploy backend/modal_deploy/serve_tesseract.py
```

This is the `ttb-tesseract` CPU container — no GPU, no model. It returns
the Government Warning bbox back-scaled to the original image pixels
plus EXIF DPI (or null when absent — the backend then defaults to a
300-DPI submission baseline and surfaces `fontSizeDpiSource: "assumed"`).

Modal prints two endpoints — the `extract-web` URL is what the backend
calls, and the health URL is what the UI uses to pre-warm the container.

## Step 4 — Wire the backend to call both Modal services

```bash
# Edit backend/.env (or create from backend/.env.example):
echo "INFERENCE_MODE=modal" >> backend/.env
echo "MODAL_ENDPOINT_URL=https://<your-user>--ttb-qwen-extractor-v2-extract-web.modal.run" >> backend/.env
echo "MODAL_TESSERACT_URL=https://<your-user>--ttb-tesseract-extract-web.modal.run" >> backend/.env
echo "MODAL_HEALTH_URL=https://<your-user>--ttb-qwen-extractor-v2-health-web.modal.run" >> backend/.env
echo "MODAL_TIMEOUT=8" >> backend/.env
echo "ANTHROPIC_API_KEY=sk-ant-..." >> backend/.env   # Haiku is the hybrid layer
```

The backend fans out Qwen + Haiku + Tesseract via `asyncio.gather`
(see `backend/app/extractors/modal_remote.py`). If Qwen exceeds
`MODAL_TIMEOUT`, the backend falls back to Haiku's full extraction +
Tesseract overlay and tags the response with
`extractorSource: "haiku-fallback"`.

## Step 5 — Run the backend locally pointed at Modal

```bash
make serve-modal
```

That boots FastAPI on http://localhost:8000 with `INFERENCE_MODE=modal`.
Every /api/verify request goes:
```
[browser] → [local backend] → [Modal Qwen GPU] → [local rules engine] → [verdict]
```

The local backend just routes HTTPS calls + runs the deterministic 27 CFR
rules engine. No GPU needed locally.

## Step 6 — Smoke test

```bash
TEST_IMG=$(ls test/eval/data/images/*.webp | head -1)
APP_DATA='{"brandName":"Test Brand","classType":"table red wine","alcoholContent":"13.5% Alc./Vol.","netContents":"750 mL","bottlerNameAddress":"Test Cellars","beverageType":"wine"}'

curl -s -X POST http://localhost:8000/api/verify \
    -F "image=@$TEST_IMG" \
    -F "applicationData=$APP_DATA" | python3 -m json.tool | head -30
```

First call: ~30-60s (Modal cold start — container spinning up + loading Qwen base from HF cache volume).

Subsequent calls (within ~5 min of idle): ~3-5s.

After 5 min idle, Modal scales the container to zero — next request cold-starts again.

## Cost expectations

| Usage pattern | Modal A10G cost | Notes |
|---|---|---|
| Idle | **$0/hr** | Scale-to-zero (container_idle_timeout=300s) |
| 1 request | ~$0.001 | 3-5s active GPU |
| 100 requests/day | ~$0.10/day = $3/month | Well within free $30/mo credit |
| 10k requests/day | ~$5/day = $150/month | Demo + light pilot scale |
| 100k requests/day (continuous load) | ~$285/month | Container stays warm, full A10G utilization |

For the TTB pitch demo, you'll be in the **$0-$3/month range** thanks to scale-to-zero + free tier.

## Frontend integration (Vercel — separate runbook item)

To get a shareable demo link:

```bash
# Set Vercel env var pointing the frontend at your local backend (via tunnel) OR
# deploy backend to Render/Fly with the same Modal endpoint config.

# For local-only demo:
ngrok http 8000     # exposes local backend at https://<random>.ngrok.io
# then set Vercel env: VITE_API_BASE_URL=https://<random>.ngrok.io/api
```

For a real deploy, see (not yet written): docs/VERCEL_RUNBOOK.md

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `modal: command not found` | Modal CLI not installed | `pip install modal` |
| `Unauthorized` on `modal deploy` | Token expired or missing | `modal token new` |
| `Volume not found: ttb-qwen-adapter` | Forgot Step 1 | `make modal-upload-adapter` |
| Cold-start timeout (>60s on first request) | Qwen base HF download (~16 GB) on first container | Wait it out; second request is fast. HF cache volume persists across restarts. |
| `502 from Modal endpoint` | Container OOM (rare on A10G with BF16 + 24 GB) | Switch to A100 in `serve_qwen.py` (`gpu="A100"`) |
| Backend `InferenceError: timeout after 60s` | First request hit cold start past timeout | Set `MODAL_TIMEOUT=120` in `backend/.env`, retry |

## Rollback

To revert to Claude:
```bash
# In backend/.env:
INFERENCE_MODE=claude-code      # or 'cloud' with ANTHROPIC_API_KEY
```

The Modal endpoint keeps running idle ($0/hr). To fully tear down:
```bash
modal app stop ttb-qwen-extractor
modal volume delete ttb-qwen-adapter
```

## What's deployed

- **Base model**: `Qwen/Qwen2.5-VL-7B-Instruct` (BF16, 16 GB, downloaded once to a persistent HF cache volume)
- **LoRA adapter**: from `backend/models/qwen2_5_vl_7b/adapter/` (~190 MB, on Modal volume)
- **Inference path**: BF16 base → LoRA merged in (no quantization, no PEFT overhead at inference)
- **Image preprocessing**: cap at 640×640 area → ~400 visual tokens (matches eval notebook's `_resize_for_eval`)
- **Generation**: max_new_tokens=384, do_sample=False, pad=eos
- **Expected latency**: 3-5 s on warm container (A10G), 30-60 s cold start

## Validation checklist before showing TTB

- [ ] `make modal-upload-adapter` — exit 0, prints "Volume updated"
- [ ] `make modal-deploy` — exit 0, prints endpoint URL
- [ ] `curl <endpoint>` — first call returns valid JSON within 60 s
- [ ] `make serve-modal` + `make eval-real` — full backend smoke test, verdict accuracy matches `qwen_report.json`
- [ ] Frontend hits backend → verdict shows in UI within ~10 s end-to-end

Then you're live.
