# TTB Label Verification — Backend

Python + FastAPI service that implements the contract defined in
`src/api/types.ts`. Three inference modes (`mock` / `cloud` / `onprem`) share
the same endpoints, models, and 27 CFR rules engine.

## Architecture

```
              ┌─────────────────────────────────────────────────┐
              │   FastAPI: POST /api/verify, /api/verify-batch  │
              └────────────────┬────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │   image_pipeline.assess_image   │  ← validate + measure
              └────────────────┬────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │   LabelExtractor (swappable)    │  ← mock / cloud / onprem
              │     reads + reports observations │     (NO verdicts here)
              └────────────────┬────────────────┘
                               │ ExtractedLabel
              ┌────────────────▼────────────────┐
              │   rules.verify  (27 CFR engine) │  ← deterministic, audited
              │   field_match • net_contents •  │     match / likely / flag
              │   government_warning • mandatory│     + regulation citations
              └────────────────┬────────────────┘
                               │ VerificationResult
                               ▼
                       JSON to frontend
```

The model only reads. The deterministic Python module decides.

## Quick start (mock mode — no API keys)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Smoke-test:

```bash
curl -s http://localhost:8000/health
# {"status":"ok","inferenceMode":"mock"}

echo "fake" > /tmp/label.jpg  # any bytes — mock mode tolerates placeholders
curl -s -X POST http://localhost:8000/api/verify \
  -F "image=@/tmp/label.jpg" \
  -F 'applicationData={"brandName":"STONE'\''S THROW","classType":"California Red Table Wine","alcoholContent":"13.5% Alc./Vol.","netContents":"750 mL","bottlerNameAddress":"Stone'\''s Throw Cellars, Sonoma, California","beverageType":"wine"}' \
  | python3 -m json.tool
```

## Run the test suite

```bash
cd backend && source .venv/bin/activate && python -m pytest
```

Covers the rules engine (33 cases), the image pipeline, and end-to-end
endpoints via FastAPI's TestClient.

## Inference modes

Selected by `INFERENCE_MODE` in `.env`:

| Mode    | When to use | Extra setup |
|---------|-------------|-------------|
| `mock`  | local development, frontend wiring tests | none |
| `cloud` | real label images, pay-per-token | `ANTHROPIC_API_KEY` in `.env` |
| `claude-code` | real label images, **billed against your Claude Code / Max subscription instead of API credits** | Claude Code installed + logged in (`claude` on PATH); no API key needed |
| `onprem`| firewalled / air-gapped (Azure Government, agency VNet) | `tesseract-ocr` + `pip install pytesseract`; optional self-hosted Phi-3.5-vision at `ONPREM_VLM_URL` |

Switch by editing `.env`:

```ini
INFERENCE_MODE=cloud
CLOUD_PROVIDER=anthropic
CLOUD_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
```

### Claude Code (Max subscription) — recommended for the demo

If you have Claude Code installed and a Max / Pro subscription, you can route
extraction through the `claude` CLI's headless mode instead of paying per
token via the API:

```ini
INFERENCE_MODE=claude-code
CLOUD_MODEL=claude-sonnet-4-6
# No ANTHROPIC_API_KEY required.
```

```bash
make serve-max   # or: INFERENCE_MODE=claude-code uvicorn app.main:app --reload
```

Under the hood the adapter writes the uploaded image to a short-lived temp
file, then runs:

```
claude -p --output-format json --json-schema <ExtractedLabel schema> \
       --model claude-sonnet-4-6 \
       --add-dir /tmp/<dir>  --allowed-tools Read \
       "Read the label at @/tmp/<file>.webp; extract per the schema."
```

Latency is ~30–40 s/label (vs ~10 s on the direct API path) because of the
CLI subprocess + agent loop. Same model, same vision capability, but billed
against your Max plan.

### Cloud (Anthropic Claude API)

- Single API call per label using **tool_use** with a fixed JSON schema, so
  the response shape is guaranteed and the model is forbidden from
  paraphrasing the Government Warning text in the transcription.
- **Prompt caching** is enabled on the system prompt and the tool definition,
  so a session/batch only pays full token cost on the first request.
- 30-second timeout; raises a typed `InferenceError` -> `502` to callers.

OpenAI and Google routes are stubbed — implement them in
`backend/app/extractors/cloud.py` if you need them.

### On-prem

- Tesseract via `pytesseract` always runs. With no VLM, field assignment
  is heuristic — the rules engine handles uncertainty by routing low-
  confidence cases to AMBER ("needs-confirm") rather than auto-failing.
- A self-hosted VLM (Phi-3.5-vision on Ollama at `http://localhost:11434`
  is the recommended default) can be plugged into the extractor to do
  structured field extraction. The seam is in `extractors/onprem.py`.

## Connect the frontend

The Vite client auto-detects: when `VITE_API_BASE_URL` is set, it stops
using the mock fixtures and posts to the backend.

```bash
# at project root (not backend/)
echo "VITE_API_BASE_URL=http://localhost:8000/api" > .env.local
npm run dev
```

(That `.env.local` is already in this repo.) Confirm CORS by opening the
browser — `backend/app/main.py` allows `localhost:5173` and `127.0.0.1:5173`.

## Deployment notes

**Prototype demo.** Frontend on Vercel, backend on a small always-on host
(Render / Railway / Fly.io). Vercel Python serverless can host the backend
*only if* the on-prem path stays disabled — Tesseract isn't supported on
serverless. `INFERENCE_MODE=cloud` here.

**Docker.**
```bash
docker build -t ttb-backend backend/
docker run -p 8000:8000 --env-file backend/.env ttb-backend
```

**Air-gapped / Azure Government.** Use the on-prem path inside the agency
VNet. The Dockerfile in this repo is the cloud variant; for on-prem add
`tesseract-ocr` (`apt-get install tesseract-ocr`) and `pytesseract` in a
derived image. The frontend, the API, and the inference all stay inside
the boundary; no outbound calls.

## Files

- [app/main.py](app/main.py) — endpoints + request pipeline
- [app/models.py](app/models.py) — Pydantic models mirroring `src/api/types.ts`
- [app/constants.py](app/constants.py) — `VERBATIM_GOVERNMENT_WARNING`
- [app/image_pipeline.py](app/image_pipeline.py) — Pillow validation, legibility, ephemeral crops
- [app/extractors/](app/extractors/) — `LabelExtractor` interface + mock/cloud/onprem adapters
- [app/rules/](app/rules/) — the 27 CFR rules engine (pure, audited, no AI)
- [tests/](tests/) — unit + integration tests
- [SECURITY.md](SECURITY.md) — data-handling posture
