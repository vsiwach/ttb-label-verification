"""FastAPI app implementing the TTB label verification contract.

Pipeline per request:
  1. Validate + measure the uploaded image (Pillow).
  2. LabelExtractor reads the image -> ExtractedLabel (raw observations only).
  3. The deterministic rules engine consumes ExtractedLabel + ApplicationData
     and produces the public VerificationResult with citations.
  4. If the extractor returned bounding boxes, generate ephemeral crops and
     attach evidenceCropUrl to each field + the Government Warning analysis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .extractors import InferenceError, get_extractor
from .image_pipeline import (
    ImageError,
    ImageMeasurement,
    assess_image,
    fetch_crop,
    store_crop,
)
from .mock_data import thumb_for
from .models import ApplicationData, BatchItemResult, ImageQuality, VerificationResult, group_for
from .rules import verify as run_rules
from .rules.mandatory_fields import ALL_FIELDS

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

# Bounded concurrency for the batch endpoint. Tuned for prototype scale.
_BATCH_CONCURRENCY = 8


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "inferenceMode": settings.inference_mode}


@app.get("/crops/{crop_id}")
def get_crop(crop_id: str) -> Response:
    """Serve an ephemeral evidence crop. 404 once the TTL elapses."""
    got = fetch_crop(crop_id)
    if got is None:
        raise HTTPException(status_code=404, detail="crop expired or not found")
    data, media_type = got
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "no-store"})


def _parse_application_data(raw: str) -> ApplicationData:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"applicationData is not valid JSON: {e}")
    try:
        return ApplicationData.model_validate(payload)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"applicationData failed validation: {e}")


def _assess_or_none(image_bytes: bytes) -> Optional[ImageMeasurement]:
    """Run the image pipeline.

    In mock mode we tolerate unparseable bytes (so curl smoke-testing with
    a placeholder works) and return None. In cloud/onprem mode the image
    MUST be valid — raise to the caller for a 400 response.
    """
    try:
        return assess_image(image_bytes)
    except ImageError as e:
        if settings.inference_mode == "mock":
            logger.info("mock-mode: ignoring unparseable image (%s)", e)
            return None
        raise


async def _run_pipeline(image_bytes: bytes, app_data: ApplicationData) -> VerificationResult:
    """The single-label pipeline. Shared by /api/verify and /api/verify-batch."""
    # 1. Validate + measure the image.
    try:
        measurement = _assess_or_none(image_bytes)
    except ImageError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Extract observations. Catch InferenceError from both the factory
    # (e.g. missing API key) and the adapter's extract() call.
    try:
        extractor = get_extractor(brand_hint=app_data.brandName)
        extracted = await extractor.extract(image_bytes, app_data.beverageType)
    except InferenceError as e:
        raise HTTPException(status_code=502, detail=f"inference failed: {e}")

    # If the image pipeline measured quality, override the extractor's
    # self-reported number with the deterministic server-side measurement.
    if measurement is not None:
        extracted.image_quality_score = measurement.score
        extracted.image_legible = measurement.legible
        extracted.image_quality_note = measurement.note

    # 3. Apply the deterministic 27 CFR rules engine.
    result = run_rules(extracted, app_data)

    # 4. Attach ephemeral evidence crops where the extractor gave bboxes.
    _attach_crops(image_bytes, extracted, result)
    return result


def _attach_crops(image_bytes: bytes, extracted, result: VerificationResult) -> None:
    """Crop and inject URLs onto fields + warning where bboxes exist.

    Silent no-op if the bytes don't decode (mock mode with placeholder data)
    or the extractor reported no boxes.
    """
    # Field crops
    label_to_app = {spec.label_name: spec for spec in ALL_FIELDS}
    for f in result.fields:
        spec = label_to_app.get(f.fieldName)
        if spec is None:
            continue
        extracted_field = extracted.fields.get(f.fieldName)
        bbox = getattr(extracted_field, "bbox", None) if extracted_field else None
        if bbox:
            url = store_crop(image_bytes, bbox)
            if url:
                f.evidenceCropUrl = url
    # Government Warning crop is informational on the analysis object itself.
    # The frontend type doesn't have a field for it, so we just generate the
    # crop (for future use / logging) and discard.
    style = getattr(extracted, "warning_style", None)
    if style is not None and getattr(style, "bbox", None):
        store_crop(image_bytes, style.bbox)


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
    """Verify a batch of labels with bounded concurrency.

    Per-item errors do NOT fail the batch — failed items come back with a
    synthetic 'flag' result so the dashboard can surface them for review.
    """
    if not images:
        raise HTTPException(status_code=400, detail="no images provided")
    shared = _parse_application_data(applicationData) if applicationData else None

    from .mock_data import SAVED_APPLICATIONS

    # Eagerly drain uploads (FastAPI's SpooledTemporaryFile is per-request).
    payloads: list[tuple[int, bytes, str, ApplicationData]] = []
    for idx, img in enumerate(images):
        b = await img.read()
        app_data = shared if shared is not None else SAVED_APPLICATIONS[idx % len(SAVED_APPLICATIONS)]
        payloads.append((idx, b, img.filename or f"label-{idx + 1}.jpg", app_data))

    sem = asyncio.Semaphore(_BATCH_CONCURRENCY)

    async def _one(idx: int, image_bytes: bytes, file_name: str, app_data: ApplicationData) -> BatchItemResult:
        async with sem:
            try:
                result = await _run_pipeline(image_bytes, app_data)
            except HTTPException as e:
                logger.warning("batch item %d failed: %s", idx, e.detail)
                result = _error_result(str(e.detail))
            except Exception as e:  # final safety net
                logger.exception("batch item %d unexpected error", idx)
                result = _error_result(f"unexpected error: {e}")
            return BatchItemResult(
                id=f"b-{int(time.time() * 1000)}-{idx}-{uuid.uuid4().hex[:6]}",
                fileName=file_name,
                thumbnailUrl=thumb_for(_scenario_key(app_data)),
                result=result,
                group=group_for(result),
            )

    items = await asyncio.gather(*(_one(*p) for p in payloads))
    logger.info("verify-batch n=%d", len(items))
    return list(items)


def _scenario_key(app_data: ApplicationData) -> str:
    brand = (app_data.brandName or "").upper()
    if "STONE" in brand:
        return "B"
    if "NORTHWIND" in brand:
        return "C"
    return "A"


def _error_result(message: str) -> VerificationResult:
    """Synthesize a 'flag' result for a per-item batch failure."""
    from .models import GovernmentWarningAnalysis, WarningDeviation
    return VerificationResult(
        fields=[],
        governmentWarning=GovernmentWarningAnalysis(
            present=False, verbatimMatch=False, casingBoldOk=False,
            fontSizeOk=False, contrastOk=False, separateAndApart=False,
            detectedText="",
            deviations=[WarningDeviation(type="error", message=message)],
        ),
        imageQuality=ImageQuality(score=0.0, legible=False, note=message),
    )
