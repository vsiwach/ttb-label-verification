# TTB Label Verification — Backend

Python + FastAPI service that implements the contract defined in
`src/api/types.ts`. Mock-mode runs without any AI keys.

## Quick start (mock mode)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # defaults to INFERENCE_MODE=mock
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl -s http://localhost:8000/health
# {"status":"ok","inferenceMode":"mock"}
```

Single-label verify (STONE'S THROW scenario — should return a `flag` on net contents):

```bash
echo "fake image bytes" > /tmp/label.jpg
curl -s -X POST http://localhost:8000/api/verify \
  -F "image=@/tmp/label.jpg" \
  -F 'applicationData={"brandName":"STONE'\''S THROW","classType":"California Red Table Wine","alcoholContent":"13.5% Alc./Vol.","netContents":"750 mL","bottlerNameAddress":"Stone'\''s Throw Cellars, Sonoma, California","beverageType":"wine"}' \
  | python3 -m json.tool
```

Batch (returns `BatchItemResult[]` with three groups):

```bash
curl -s -X POST http://localhost:8000/api/verify-batch \
  -F "images=@/tmp/label.jpg" -F "images=@/tmp/label.jpg" -F "images=@/tmp/label.jpg" \
  | python3 -m json.tool
```

## Inference modes

Selected by `INFERENCE_MODE` in `.env`:

| Mode    | Status      | Needs            |
|---------|-------------|------------------|
| `mock`  | ready       | nothing — uses fixtures matching the frontend mock |
| `cloud` | scaffolded  | a provider API key (Anthropic / OpenAI / Google) |
| `onprem`| scaffolded  | local Ollama/vLLM at `ONPREM_VLM_URL` |

## Architecture

- `app/main.py` — FastAPI endpoints; thin glue
- `app/models.py` — Pydantic models that mirror `src/api/types.ts`
- `app/constants.py` — `VERBATIM_GOVERNMENT_WARNING` (byte-identical to frontend)
- `app/mock_data.py` — three demo scenarios reproducing `src/api/mockData.ts`
- `app/config.py` — env-driven settings

The deterministic 27 CFR rules engine and the swappable inference interface
arrive in the next build steps.
