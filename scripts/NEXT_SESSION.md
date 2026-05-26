# Next session — deploy v2.1 to Modal + Vercel, send to Treasury

State as of this checkpoint:

- **v2.1 retrained and validated**: ~80% micro accuracy on 200-row holdout (2× Haiku at 40%), 3.83s mean latency. Adapter lives at `MyDrive/ttb_sft/qwen2_5_vl_7b_v2/adapter/` on Drive.
- **Eval notebook patched** to apply bottler-cleaning to expected ground truth (commit pending) — fixes the misleading bottler=0% from the first eval run. Future eval runs will report the honest ~80% directly.
- **Both deployment artifacts ready**: Modal MVP (`backend/modal_deploy/serve_full_app.py`) and Vercel (`vercel.json` + `api/index.py`).
- **Smoke test harness in place**: `make smoke-deployed URL=...`.
- **14 CVEs patched** to 0. Samples picker capped to 147. Dead FieldRow removed.

## Order of operations (~45 min total)

### 1. Sync v2.1 adapter from Drive to local backend (~2 min)

```bash
cd /Users/vikramsiwach/Downloads/ttb-label-verification

# Pull v2.1 from Drive into the local backend models dir
rsync -av \
  "/Users/vikramsiwach/Library/CloudStorage/GoogleDrive-vsiwach@gmail.com/My Drive/ttb_sft/qwen2_5_vl_7b_v2/adapter/" \
  backend/models/qwen2_5_vl_7b_v2/adapter/

# Verify the safetensors arrived
ls -la backend/models/qwen2_5_vl_7b_v2/adapter/adapter_model.safetensors
# Expect: 190435728 bytes
```

If Drive FUSE times out mid-rsync, retry — it's idempotent.

### 2. Upload v2.1 to Modal's adapter volume (~3 min)

```bash
# Sanity-check Modal auth first
backend/.venv/bin/modal token current

# Push the v2.1 adapter to the volume the Modal app reads from
make modal-upload-adapter SFT_MODEL_DIR=backend/models/qwen2_5_vl_7b_v2
```

This OVERWRITES the v1 adapter that's currently on the `ttb-qwen-adapter`
Modal volume. From here on the privacy-first deploy serves v2.1.

### 3. Build frontend (~10 sec)

```bash
npm run build      # produces dist/ that both deploys bake in
```

### 4. Deploy Modal MVP — privacy-first path (~5 min)

```bash
make modal-deploy-mvp
# → prints HTTPS URL like:
#   https://<user>--ttb-mvp-onprem-asgi-app.modal.run
# Save this as MODAL_URL
```

Pre-warm before testing (one cold-start cost):
```bash
curl -fsS "$MODAL_URL/health"
# First call: 30-60s (cold start). Subsequent: <1s.
```

Smoke-test:
```bash
make smoke-deployed URL="$MODAL_URL"
# Must show: ALL CHECKS PASSED — ship it
```

### 5. Deploy Vercel — public Haiku path (~5 min)

One-time bootstrap if not already done (skip if you've used Vercel CLI before):
```bash
npm i -g vercel
vercel login
vercel link              # link the local checkout to a Vercel project
```

Set required env vars in Vercel (dashboard or CLI):
```bash
vercel env add ANTHROPIC_API_KEY production   # paste value from backend/.env
vercel env add CORS_ORIGINS    production     # value: *
# INFERENCE_MODE / CLOUD_MODEL already pinned via vercel.json
```

Deploy + smoke:
```bash
make vercel-deploy
# → prints HTTPS URL like:
#   https://ttb-verify.vercel.app
# Save as VERCEL_URL

make smoke-deployed URL="$VERCEL_URL"
```

### 6. Final cross-check before sending to Treasury

```bash
# Hit each URL in the browser, do one upload + one batch
open "$MODAL_URL"
open "$VERCEL_URL"
```

Pick a real TTB label you have on hand (not a sample from the picker) and verify:
- /upload → fill form → Verify → ResultPage renders
- /batch → upload 2-3 images → ReviewPage renders
- All 4 fields populated; bucket assignment looks sensible
- Latency badge visible at bottom of ResultPage

### 7. Send Treasury both URLs

Email template lives in `scripts/MORNING.md` (the v2/v2.1 train + eval walkthrough), but the deploy-day version reads roughly:

> Two MVPs of the TTB label-verification system to test against your sample COLAs:
>
> **[Modal / privacy-first]** `$MODAL_URL`
> - On-prem-style: Qwen 2.5-VL 7B fine-tuned on 9K TTB labels
> - **No external API calls — data stays in the container**
> - ~3-5s warm, 30-60s on first request after 2 min idle
> - 80% field accuracy / 91.5% class & type
>
> **[Vercel / public]** `$VERCEL_URL`
> - Cloud extraction via Anthropic Haiku
> - ~3-5s every request (no cold start)
> - 40% field accuracy / 20% class & type
> - Use this for benchmarking accuracy or cold-start-sensitive demos
>
> Both serve identical UX. Both have a "Pick a sample" picker pre-loaded
> with 147 real COLA labels, OR you can upload your own to test against
> your filings.

## If anything goes wrong

| Symptom | Fix |
|---|---|
| `make modal-deploy-mvp` complains about `dist/` missing | run `npm run build` first |
| Smoke test against Modal URL times out at the first /api/verify | normal cold start; retry once after `curl /health` warms it |
| Vercel function 500s | check Vercel dashboard logs for `ANTHROPIC_API_KEY` missing |
| Vercel function timeout (30s) | one of your test images is huge — Vercel limit; downsize or use Modal |
| `make modal-upload-adapter` says "permission denied" | run `backend/.venv/bin/modal token new` first |

## Don't forget

- `backend/models/qwen2_5_vl_7b_v2/adapter/manifest.json` has `epochs: 1` (wrong — actually trained for 3). Cosmetic; fixing in a follow-up commit, doesn't affect inference.
- The old v2 (1-epoch) adapter on Drive is overwritten by v2.1 — its eval numbers are preserved in `MyDrive/ttb_sft/eval/v1_vs_v2_comparison_v2_baseline.md` if you ever need to look back.

## State markers (so the future session knows where we left off)

- ✓ v2.1 training done (Drive: `MyDrive/ttb_sft/qwen2_5_vl_7b_v2/adapter/`)
- ✓ v2.1 evaluated vs Haiku (Drive: `MyDrive/ttb_sft/eval/v1_vs_v2_comparison.md`)
- ✓ Eval scorer patched (this commit)
- ✓ Modal full-app deploy script written (`backend/modal_deploy/serve_full_app.py`)
- ✓ Vercel deploy config written (`vercel.json`, `api/index.py`, `docs/DEPLOY_VERCEL.md`)
- ✓ Smoke test harness (`test/smoke/smoke_deployed.py`)
- ✓ All 14 CVEs patched, samples picker capped, dead code removed
- ⏳ Next: execute the order above
