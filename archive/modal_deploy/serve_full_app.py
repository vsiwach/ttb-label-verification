"""Modal deployment of the WHOLE TTB MVP — privacy-first Qwen path.

Single container exposes the same UX Treasury would get from a local
`make serve-api`:
  - Static React frontend (built `dist/`) served at /
  - FastAPI backend at /api/*, /health, /crops/*
  - Qwen2.5-VL 7B + v2.1 LoRA loaded once per container, reused across requests
  - Rules engine runs inline (deterministic Python)

Critically: NO external API calls. Data uploaded to /api/verify never
leaves this container. That's the privacy-first deployment story —
contrast with the Vercel + Haiku variant which routes through Anthropic.

One-time setup (run from repo root):

    npm run build                                   # produces dist/
    backend/.venv/bin/modal token new
    backend/.venv/bin/modal volume put --force ttb-qwen-adapter \\
        backend/models/qwen2_5_vl_7b_v2/adapter /adapter

Deploy:

    backend/.venv/bin/modal deploy backend/modal_deploy/serve_full_app.py

The deploy prints an HTTPS URL like:
    https://<user>--ttb-mvp-onprem-asgi-app.modal.run

That URL is the link Treasury opens. Cold start ~30-60s on first request
after 2 min idle; warm requests ~3-5s.

Cost model (A10G):
    - $0.40/hr while a container is running
    - container_idle_timeout=120 means scale-to-zero after 2 min idle
    - Demo / sparse traffic: ~$1-15/mo
"""
from __future__ import annotations

from pathlib import Path

import modal

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── Image: backend + ML deps + dist/ baked in ───────────────────────────────
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # ML stack — matches notebooks/sft_qwen2_5_vl_v2.ipynb pins
        "transformers==4.51.3",
        "peft>=0.13",
        "torchao>=0.16",
        "accelerate>=0.30",
        "protobuf>=5.27",
        "torch>=2.5",
        "qwen-vl-utils",
        "numpy>=2.0,<2.2",
        "bitsandbytes>=0.44",
        # Backend deps — matches backend/requirements.txt post-CVE-patch
        "fastapi==0.135.4",
        "uvicorn[standard]==0.48.0",
        "python-multipart==0.0.29",
        "pydantic==2.13.4",
        "pydantic-settings==2.7.0",
        "httpx==0.28.1",
        "requests==2.34.2",
        "Pillow==12.2.0",
        "anthropic>=0.104.0",        # imported defensively by extractor factory; not used in this mode
    )
    # Bake the backend Python package + built frontend into the image.
    # Adding the local files means we don't need a separate volume for
    # source code — the deploy is hermetic.
    .add_local_dir(REPO_ROOT / "backend" / "app", remote_path="/srv/backend/app")
    .add_local_dir(REPO_ROOT / "dist",            remote_path="/srv/dist")
)

adapter_volume  = modal.Volume.from_name("ttb-qwen-adapter",  create_if_missing=True)
hf_cache_volume = modal.Volume.from_name("ttb-qwen-hf-cache", create_if_missing=True)

app = modal.App("ttb-mvp-onprem")


@app.function(
    image=image,
    gpu="A10G",                      # 24 GB, fits Qwen 7B BF16 + LoRA
    volumes={
        "/adapter":                  adapter_volume,
        "/root/.cache/huggingface":  hf_cache_volume,
    },
    container_idle_timeout=120,      # scale-to-zero after 2 min idle (cheap)
    timeout=600,                     # 10 min max per request — generous for batch
    min_containers=0,                # truly scale-to-zero
)
@modal.concurrent(max_inputs=4)      # one warm container serves up to 4 concurrent requests
@modal.asgi_app()
def asgi_app():
    """Mount the FastAPI app + static frontend in a single ASGI handler.

    The existing backend FastAPI app keeps all its routes intact
    (/api/verify, /api/verify-batch, /api/samples, /health, /crops/*).
    We add a catch-all at the end that serves static files from
    /srv/dist for any path that wasn't matched by an API route — that's
    the SPA fallback so /upload, /result, /batch, /review all resolve
    to index.html and the React router takes over.
    """
    import os
    import sys
    from pathlib import Path as _P

    # Backend lives at /srv/backend/app; make it importable
    sys.path.insert(0, "/srv/backend")

    # Force on-prem inference. ANTHROPIC_API_KEY is explicitly NOT set so
    # any accidental fallthrough to the cloud extractor fails loud.
    os.environ["INFERENCE_MODE"] = "sft"
    os.environ["SFT_MODEL_DIR"]  = "/adapter"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.setdefault("CORS_ORIGINS", "*")

    from fastapi.responses import FileResponse, Response

    # Import the backend FastAPI app (all routes already wired)
    from app.main import app as backend_app

    DIST = _P("/srv/dist")

    # SPA catch-all — runs AFTER the backend's own routes since FastAPI
    # matches in registration order. Serves an actual asset if it exists
    # under dist/, else falls back to index.html for client-side routing.
    @backend_app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> Response:
        # If a real file exists at the requested path, serve it
        candidate = DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        # Otherwise: SPA route → index.html (React router resolves it)
        return FileResponse(DIST / "index.html")

    return backend_app
