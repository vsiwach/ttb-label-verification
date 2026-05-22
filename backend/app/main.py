"""FastAPI app implementing the TTB label verification contract.

Pipeline per request:
  1. LabelExtractor reads the image -> ExtractedLabel (raw observations only).
  2. The deterministic rules engine consumes ExtractedLabel + ApplicationData
     and produces the public VerificationResult with citations.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .extractors import InferenceError, get_extractor
from .mock_data import thumb_for
from .models import ApplicationData, BatchItemResult, VerificationResult, group_for
from .rules import verify as run_rules

logger = logging.getLogger("ttb")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="TTB Label Verification API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "inferenceMode": settings.inference_mode}


def _parse_application_data(raw: str) -> ApplicationData:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"applicationData is not valid JSON: {e}")
    try:
        return ApplicationData.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"applicationData failed validation: {e}")


async def _run_pipeline(image_bytes: bytes, app_data: ApplicationData) -> VerificationResult:
    """The single-label pipeline: extractor -> rules engine -> VerificationResult."""
    extractor = get_extractor(brand_hint=app_data.brandName)
    try:
        extracted = await extractor.extract(image_bytes, app_data.beverageType)
    except InferenceError as e:
        raise HTTPException(status_code=502, detail=f"inference failed: {e}")
    return run_rules(extracted, app_data)


@app.post("/api/verify", response_model=VerificationResult)
async def verify(
    image: UploadFile = File(...),
    applicationData: str = Form(...),
) -> VerificationResult:
    """Verify a single label. Returns the FULL VerificationResult as one JSON
    response (not streamed) — matches the real path in src/api/client.ts."""
    app_data = _parse_application_data(applicationData)
    image_bytes = await image.read()
    started = time.perf_counter()
    result = await _run_pipeline(image_bytes, app_data)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "verify brand=%s beverage=%s group=%s ms=%d",
        app_data.brandName, app_data.beverageType, group_for(result), elapsed_ms,
    )
    return result


@app.post("/api/verify-batch", response_model=list[BatchItemResult])
async def verify_batch(
    images: list[UploadFile] = File(...),
    applicationData: Optional[str] = Form(None),
) -> list[BatchItemResult]:
    """Verify a batch of labels. Returns BatchItemResult[]."""
    if not images:
        raise HTTPException(status_code=400, detail="no images provided")
    shared = _parse_application_data(applicationData) if applicationData else None
    out: list[BatchItemResult] = []
    # Rotate through saved scenarios when caller doesn't pin a single application,
    # mirroring the frontend's verifyBatch mock behavior so the dashboard sees a mix.
    from .mock_data import SAVED_APPLICATIONS
    for idx, img in enumerate(images):
        image_bytes = await img.read()
        app_data = shared if shared is not None else SAVED_APPLICATIONS[idx % len(SAVED_APPLICATIONS)]
        scenario_key = _scenario_key(app_data)
        result = await _run_pipeline(image_bytes, app_data)
        item = BatchItemResult(
            id=f"b-{int(time.time() * 1000)}-{idx}-{uuid.uuid4().hex[:6]}",
            fileName=img.filename or f"label-{idx + 1}.jpg",
            thumbnailUrl=thumb_for(scenario_key),
            result=result,
            group=group_for(result),
        )
        out.append(item)
    logger.info("verify-batch n=%d", len(images))
    return out


def _scenario_key(app_data: ApplicationData) -> str:
    brand = (app_data.brandName or "").upper()
    if "STONE" in brand:
        return "B"
    if "NORTHWIND" in brand:
        return "C"
    return "A"
