"""Vercel serverless entrypoint for the TTB MVP — Vercel UI + Modal Qwen v2.

Vercel's @vercel/python runtime expects a single file exporting an ASGI
`app` (Mangum-style). This file is that bridge:
  - sys.path tweak so we can import the existing backend/app/* modules
    from this file's location (api/index.py at repo root)
  - Default INFERENCE_MODE=modal so extraction goes to the deployed Qwen v2
    LoRA endpoint on Modal. The rules engine (deterministic 27 CFR) still
    runs inside this Vercel function — Modal only does vision extraction.
  - Override via Vercel env to fall back to INFERENCE_MODE=cloud (Haiku).

The frontend is served statically from /dist by Vercel's CDN (configured
in vercel.json). This function handles /api/*, /health, and /crops/*.

Vercel env vars (set in Vercel dashboard, not committed):
  INFERENCE_MODE       — defaults to "modal" (this file); override to "cloud" for Haiku
  MODAL_ENDPOINT_URL   — Modal Qwen v2 endpoint (default below points at production)
  MODAL_TIMEOUT        — httpx timeout in seconds (must be < Vercel maxDuration=30)
  ANTHROPIC_API_KEY    — only needed if INFERENCE_MODE=cloud override is set
  CORS_ORIGINS         — set to your Vercel domain (or '*' for the demo)

Same FastAPI app, same routes, same rules engine as the local dev path and
the Modal full-app deploy (backend/modal_deploy/serve_full_app.py).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root is the parent of this file's directory (api/ is at repo root)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Default to modal mode — Vercel function routes inference to the deployed
# Qwen v2 endpoint on Modal. Override INFERENCE_MODE=cloud in Vercel env
# to use Haiku instead. Set BEFORE importing app.main so settings pick it up.
os.environ.setdefault("INFERENCE_MODE",    "modal")
os.environ.setdefault("MODAL_ENDPOINT_URL", "https://vsiwach--ttb-qwen-extractor-v2-extract-web.modal.run")
os.environ.setdefault("MODAL_TIMEOUT",     "8")   # Snap to Haiku fallback if Modal is cold/slow
# Cloud fallback config (used only if env explicitly sets INFERENCE_MODE=cloud)
os.environ.setdefault("CLOUD_PROVIDER", "anthropic")
os.environ.setdefault("CLOUD_MODEL",    "claude-haiku-4-5")

# Import the existing FastAPI app — exposes /api/verify, /api/verify-batch,
# /api/samples, /health, /crops/*. Frontend is served by Vercel CDN, NOT
# by this function (vercel.json rewrites segregate them).
from app.main import app  # noqa: E402

# Vercel's @vercel/python looks for `app` (ASGI) or `handler` (WSGI).
# FastAPI is ASGI-native, so `app` is what we expose.
