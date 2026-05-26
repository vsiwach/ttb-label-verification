"""Vercel serverless entrypoint for the TTB MVP — Haiku public path.

Vercel's @vercel/python runtime expects a single file exporting an ASGI
`app` (Mangum-style). This file is that bridge:
  - sys.path tweak so we can import the existing backend/app/* modules
    from this file's location (api/index.py at repo root)
  - Force INFERENCE_MODE=cloud and CLOUD_MODEL=claude-haiku-4-5 so this
    path uses Anthropic (no GPU needed — Vercel functions don't have one)
  - Import the existing FastAPI app verbatim (same code as the Modal
    privacy-first deploy uses, just configured for cloud extraction)

The frontend is served statically from /dist by Vercel's CDN (configured
in vercel.json). This function handles /api/*, /health, and /crops/*.

Required Vercel env vars (set in Vercel dashboard, not committed):
  ANTHROPIC_API_KEY   — for the cloud extractor
  CORS_ORIGINS        — set to your Vercel domain (or '*' for the demo)

The Modal privacy-first path lives in backend/modal_deploy/serve_full_app.py
and uses INFERENCE_MODE=sft + a Qwen LoRA. Same backend code, same routes,
same frontend — only the extractor wiring differs. That's the "same MVP,
two deployments" guarantee.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root is the parent of this file's directory (api/ is at repo root)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Force cloud-extractor mode. Set BEFORE importing app.main so the
# settings/extractor factory pick it up. The fail-fast in the factory
# requires ANTHROPIC_API_KEY to be set as a Vercel env var.
os.environ.setdefault("INFERENCE_MODE", "cloud")
os.environ.setdefault("CLOUD_PROVIDER", "anthropic")
os.environ.setdefault("CLOUD_MODEL",    "claude-haiku-4-5")

# Import the existing FastAPI app — exposes /api/verify, /api/verify-batch,
# /api/samples, /health, /crops/*. Frontend is served by Vercel CDN, NOT
# by this function (vercel.json rewrites segregate them).
from app.main import app  # noqa: E402

# Vercel's @vercel/python looks for `app` (ASGI) or `handler` (WSGI).
# FastAPI is ASGI-native, so `app` is what we expose.
