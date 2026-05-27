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
# Note: removed `from .mock_data import application_for_filename` — the old
# batch endpoint used to fall back to a synthetic OLD TOM / STONE'S THROW /
# NORTHWIND round-robin when no application data was provided, which
# produced confusing false-flag mismatches. The new fallback is an empty
# ApplicationData (declared blank, engine surfaces honest notes).
from .models import ApplicationData, BatchItemResult, ImageQuality, TimingInfo, VerificationResult, group_for
from .rules import verify as run_rules
from .rules.mandatory_fields import ALL_FIELDS
from .samples import get_sample_by_id, list_all_samples, list_samples

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
async def health() -> dict:
    """Liveness + Modal warmth probe.

    On the modal inference path, this hits the Modal /health_web
    endpoint with a 5s budget. A sub-second round trip means the Qwen
    v2 GPU container is warm and the next /api/verify will get Qwen
    extraction for the four trained fields. A timeout means Modal is
    still cold-starting (load_model runs ~30-60s) — /api/verify will
    transparently fall back to Haiku-only for that request while the
    warmup completes server-side. Either way the API is healthy.
    """
    out: dict = {"status": "ok", "inferenceMode": settings.inference_mode}
    if settings.inference_mode != "modal" or not settings.modal_health_url:
        return out

    import httpx
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.modal_health_timeout) as client:
            r = await client.get(settings.modal_health_url)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        warm = r.status_code == 200 and elapsed_ms < int(settings.modal_health_timeout * 1000)
        out["modal"] = {
            "warm": warm,
            "latencyMs": elapsed_ms,
            "statusCode": r.status_code,
        }
    except httpx.TimeoutException:
        out["modal"] = {
            "warm": False,
            "latencyMs": int((time.perf_counter() - t0) * 1000),
            "note": f"timed out after {settings.modal_health_timeout}s — container cold-starting",
        }
    except Exception as e:
        out["modal"] = {"warm": False, "error": str(e)[:200]}
    return out


def _serialize_sample(s) -> dict:
    return {
        "id": s.id,
        "kind": s.kind,
        "imageUrl": f"/api/samples/{s.id}/image",
        "applicationData": s.application_data.model_dump(),
        "expectedOutcome": s.expected_outcome,
        "note": s.note,
    }


@app.get("/api/samples")
def get_samples() -> list[dict]:
    """Curated picker subset shown on the /upload page.

    Currently COLA Cloud only: every auto-pass row plus a handful of
    needs-review failures so the demo dropdown surfaces both happy and
    unhappy paths. For the full universe (gallery), see /api/samples/all.
    """
    return [_serialize_sample(s) for s in list_samples()]


@app.get("/api/samples/all")
def get_samples_all() -> list[dict]:
    """Full sample universe shown on the /samples gallery page.

    Includes every COLA Cloud row, every curated TTB-live label, and
    the synthetic CI fixtures. Each card on the gallery links into
    /upload?sample={id} so the user can edit ABV / Net contents
    before submitting.
    """
    return [_serialize_sample(s) for s in list_all_samples()]


@app.get("/api/samples/{sample_id}/image")
def get_sample_image(sample_id: str) -> Response:
    s = get_sample_by_id(sample_id)
    if s is None or not s.image_path.exists():
        raise HTTPException(status_code=404, detail="sample not found")
    suffix = s.image_path.suffix.lower().lstrip(".")
    media = {"png": "image/png", "webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix, "application/octet-stream")
    return Response(
        content=s.image_path.read_bytes(),
        media_type=media,
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
    """The single-label pipeline. Shared by /api/verify and /api/verify-batch.

    Measures wall-clock latency at each stage and attaches a TimingInfo to
    the result so the UI can show end-to-end latency + which inference
    mode produced it (claude-code locally, modal+Qwen in production).
    """
    pipeline_start = time.perf_counter()

    # 1. Validate + measure the image.
    try:
        measurement = _assess_or_none(image_bytes)
    except ImageError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Extract observations. Catch InferenceError from both the factory
    # (e.g. missing API key) and the adapter's extract() call.
    extractor_start = time.perf_counter()
    try:
        extractor = get_extractor(brand_hint=app_data.brandName)
        extracted = await extractor.extract(image_bytes, app_data.beverageType)
    except InferenceError as e:
        raise HTTPException(status_code=502, detail=f"inference failed: {e}")
    extractor_ms = int((time.perf_counter() - extractor_start) * 1000)

    # If the image pipeline measured quality, override the extractor's
    # self-reported number with the deterministic server-side measurement.
    # Also pass DPI through so the rules engine can do the 16.22
    # type-size check (when the extractor returns a warning bbox).
    if measurement is not None:
        extracted.image_quality_score = measurement.score
        extracted.image_legible = measurement.legible
        extracted.image_quality_note = measurement.note
        extracted.image_dpi = measurement.dpi

    # 3. Apply the deterministic 27 CFR rules engine.
    rules_start = time.perf_counter()
    result = run_rules(extracted, app_data)
    rules_ms = int((time.perf_counter() - rules_start) * 1000)

    # 4. Attach ephemeral evidence crops where the extractor gave bboxes.
    _attach_crops(image_bytes, extracted, result)

    result.timing = TimingInfo(
        inferenceMode=settings.inference_mode,
        extractorMs=extractor_ms,
        rulesMs=rules_ms,
        totalMs=int((time.perf_counter() - pipeline_start) * 1000),
        extractorSource=extracted.extractor_source,
    )
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
    applicationsByFilename: Optional[str] = Form(None),
) -> list[BatchItemResult]:
    """Verify a batch of labels with bounded concurrency.

    Per-item errors do NOT fail the batch — failed items come back with a
    synthetic 'flag' result so the dashboard can surface them for review.

    Application data precedence (per-item):
      1. applicationsByFilename[filename] — JSON map sent by the frontend
         sample picker carrying the REAL TTB application data per file
      2. applicationData (shared) — single ApplicationData applied to every
         item, for "all images in this batch are from the same COLA submission"
         flow
      3. empty ApplicationData — for user-dropped files without picker
         metadata. Engine surfaces "Application did not declare this field"
         per field instead of flagging against placeholder data.
    """
    if not images:
        raise HTTPException(status_code=400, detail="no images provided")
    shared = _parse_application_data(applicationData) if applicationData else None

    # Optional per-file map. JSON dict of {filename: ApplicationData-dict}.
    per_file: dict[str, ApplicationData] = {}
    if applicationsByFilename:
        try:
            raw = json.loads(applicationsByFilename)
            if isinstance(raw, dict):
                for fname, app_dict in raw.items():
                    if isinstance(app_dict, dict):
                        per_file[fname] = ApplicationData.model_validate(app_dict)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("ignoring malformed applicationsByFilename: %s", e)

    # Eagerly drain uploads (FastAPI's SpooledTemporaryFile is per-request).
    payloads: list[tuple[int, bytes, str, ApplicationData]] = []
    for idx, img in enumerate(images):
        b = await img.read()
        filename = img.filename or f"label-{idx + 1}.jpg"
        # Precedence: per-file map (real picker data) > shared > empty.
        # The old code used a synthetic round-robin fallback that produced
        # confusing "OLD TOM DISTILLERY vs RICCI" mismatches for picker
        # samples — that's been removed.
        app_data = (
            per_file.get(filename)
            or shared
            or ApplicationData(
                colaNumber="", brandName="", classType="",
                alcoholContent="", netContents="",
                bottlerNameAddress="", beverageType="spirits",
            )
        )
        payloads.append((idx, b, filename, app_data))

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
                thumbnailUrl="",
                result=result,
                group=group_for(result),
            )

    items = await asyncio.gather(*(_one(*p) for p in payloads))
    logger.info("verify-batch n=%d", len(items))
    return list(items)


def _error_result(message: str) -> VerificationResult:
    """Synthesize a 'flag' result for a per-item batch failure."""
    from .models import GovernmentWarningAnalysis, WarningDeviation
    return VerificationResult(
        fields=[],
        governmentWarning=GovernmentWarningAnalysis(
            present=False, verbatimMatch=False, casingBoldOk=False,
            contrastOk=False, separateAndApart=False,
            detectedText="",
            deviations=[WarningDeviation(type="error", message=message)],
        ),
        imageQuality=ImageQuality(score=0.0, legible=False, note=message),
    )
