"""FastAPI app implementing the TTB label verification contract.

In MOCK mode the endpoints return the same three demo scenarios the frontend
uses, so wiring is end-to-end real without an inference key.
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
from .mock_data import pick_scenario, thumb_for
from .models import ApplicationData, BatchItemResult, VerificationResult, group_for

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


def _scenario_key_for(app_data: ApplicationData | None) -> str:
    if app_data is None:
        return "A"
    brand = (app_data.brandName or "").upper()
    if "STONE" in brand:
        return "B"
    if "NORTHWIND" in brand:
        return "C"
    return "A"


@app.post("/api/verify", response_model=VerificationResult)
async def verify(
    image: UploadFile = File(...),
    applicationData: str = Form(...),
) -> VerificationResult:
    """Verify a single label. Returns the FULL VerificationResult as one JSON
    response (not streamed) — matches the real path in src/api/client.ts."""
    app_data = _parse_application_data(applicationData)
    # Drain the upload so a future inference adapter can use the bytes; for the
    # mock we just acknowledge it and don't persist anything.
    _ = await image.read()
    started = time.perf_counter()
    if settings.inference_mode == "mock":
        result = pick_scenario(app_data)
    else:
        # cloud / onprem adapters come online in Step 2.
        raise HTTPException(status_code=501, detail=f"INFERENCE_MODE={settings.inference_mode} not yet implemented")
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("verify ok brand=%s beverage=%s ms=%d", app_data.brandName, app_data.beverageType, elapsed_ms)
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

    keys = ["A", "B", "C"]
    out: list[BatchItemResult] = []
    for idx, img in enumerate(images):
        _ = await img.read()
        # Rotate through scenarios so the demo dashboard sees all three groups,
        # matching the frontend's verifyBatch mock behavior.
        key = keys[idx % len(keys)] if shared is None else _scenario_key_for(shared)
        scenario = pick_scenario(_app_for_key(key)) if shared is None else pick_scenario(shared)
        item = BatchItemResult(
            id=f"b-{int(time.time() * 1000)}-{idx}-{uuid.uuid4().hex[:6]}",
            fileName=img.filename or f"label-{idx + 1}.jpg",
            thumbnailUrl=thumb_for(key),
            result=scenario,
            group=group_for(scenario),
        )
        out.append(item)
    logger.info("verify-batch ok n=%d", len(images))
    return out


def _app_for_key(key: str) -> ApplicationData:
    """Helper so the batch endpoint can synthesize an application when none
    was supplied — pick_scenario keys off brandName."""
    from .mock_data import SAVED_APPLICATIONS
    idx = {"A": 0, "B": 1, "C": 2}.get(key, 0)
    return SAVED_APPLICATIONS[idx]
