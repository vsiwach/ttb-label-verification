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
from fastapi.responses import StreamingResponse

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
    response (not streamed). Used by the batch fan-out in client.ts and by
    smoke-test tooling. The streaming variant lives at /api/verify/stream."""
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


def _ndjson(event: str, data: dict) -> bytes:
    return (json.dumps({"event": event, "data": data}, default=str) + "\n").encode("utf-8")


@app.post("/api/verify/stream")
async def verify_stream(
    image: UploadFile = File(...),
    applicationData: str = Form(...),
) -> StreamingResponse:
    """Verify a single label, streaming events as the pipeline progresses.

    Wire format is NDJSON — one JSON object per line:
        {"event":"image_quality", "data":{...ImageQuality...}}
        {"event":"field",         "data":{...VerificationField...}}
        ...
        {"event":"warning",       "data":{...GovernmentWarningAnalysis...}}
        {"event":"done",          "data":{"group":"...", "timing":{...}}}

    Why this matters: the parallel branches (Qwen / Haiku / Tesseract)
    finish at different times. With the non-streaming /api/verify the
    user stares at a spinner for 5s and then sees everything at once.
    Here image_quality lands at ~200 ms, Qwen-owned fields (brand /
    class / bottler / country) at ~3s, Haiku-owned fields (ABV / net /
    warning text + casing) at ~3.5s, with the final 'done' verdict at
    ~5s. Total wall is unchanged; perceived latency drops to under 3s
    for the first useful UI render.
    """
    app_data = _parse_application_data(applicationData)
    image_bytes = await image.read()

    async def event_stream():
        t0 = time.perf_counter()
        try:
            try:
                measurement = _assess_or_none(image_bytes)
            except ImageError as e:
                yield _ndjson("error", {"detail": str(e)})
                return

            iq = ImageQuality(
                score=measurement.score if measurement is not None else 1.0,
                legible=measurement.legible if measurement is not None else True,
                note=measurement.note if measurement is not None else None,
            )
            yield _ndjson("image_quality", iq.model_dump())

            try:
                extractor = get_extractor(brand_hint=app_data.brandName)
            except InferenceError as e:
                yield _ndjson("error", {"detail": f"inference setup failed: {e}"})
                return

            emitted_fields: set[str] = set()
            last_warning_sig: Optional[str] = None
            final_snapshot = None

            try:
                async for snapshot in extractor.extract_streaming(image_bytes, app_data.beverageType):
                    if measurement is not None:
                        snapshot.image_quality_score = measurement.score
                        snapshot.image_legible = measurement.legible
                        snapshot.image_quality_note = measurement.note
                        snapshot.image_dpi = measurement.dpi

                    partial = run_rules(snapshot, app_data)
                    _attach_crops(image_bytes, snapshot, partial)

                    for f in partial.fields:
                        if f.fieldName in emitted_fields:
                            continue
                        # Only emit fields with real extracted data — fields
                        # that ended up "likely / Could not extract" stay
                        # pending until either (a) a later snapshot fills
                        # them in or (b) the final-pass loop below.
                        ef = snapshot.fields.get(f.fieldName)
                        if ef is None or not (ef.value or "").strip():
                            continue
                        emitted_fields.add(f.fieldName)
                        yield _ndjson("field", f.model_dump())

                    gw = partial.governmentWarning
                    sig = json.dumps(
                        [gw.present, gw.verbatimMatch, gw.casingBoldOk, gw.detectedText, gw.fontSizeMm],
                        default=str,
                    )
                    if sig != last_warning_sig and (gw.present or gw.detectedText):
                        last_warning_sig = sig
                        yield _ndjson("warning", gw.model_dump())

                    final_snapshot = snapshot
            except InferenceError as e:
                yield _ndjson("error", {"detail": f"inference failed: {e}"})
                return

            if final_snapshot is None:
                yield _ndjson("error", {"detail": "no extraction produced"})
                return

            # Final pass: run the rules engine over the complete extracted
            # label and emit anything that wasn't covered by a partial
            # (e.g. fields that the model never read → "likely / Could
            # not extract" placeholders so the UI shows a verdict for
            # every mandatory row).
            final = run_rules(final_snapshot, app_data)
            _attach_crops(image_bytes, final_snapshot, final)
            for f in final.fields:
                if f.fieldName not in emitted_fields:
                    emitted_fields.add(f.fieldName)
                    yield _ndjson("field", f.model_dump())

            # Emit the final warning state if the streaming loop never
            # produced one (e.g. extractor yielded only once with no
            # warning data) OR if the final-pass rules engine produced
            # something different (e.g. the type-size check resolved
            # once Tesseract's bbox + DPI landed).
            final_gw = final.governmentWarning
            final_sig = json.dumps(
                [final_gw.present, final_gw.verbatimMatch, final_gw.casingBoldOk, final_gw.detectedText, final_gw.fontSizeMm],
                default=str,
            )
            if final_sig != last_warning_sig:
                yield _ndjson("warning", final_gw.model_dump())

            total_ms = int((time.perf_counter() - t0) * 1000)
            timing = TimingInfo(
                inferenceMode=settings.inference_mode,
                extractorMs=total_ms,
                rulesMs=0,
                totalMs=total_ms,
                extractorSource=final_snapshot.extractor_source,
            )
            yield _ndjson("done", {
                "group": group_for(final),
                "imageQuality": final.imageQuality.model_dump(),
                "timing": timing.model_dump(),
            })
            logger.info(
                "verify-stream brand=%s beverage=%s group=%s ms=%d",
                app_data.brandName, app_data.beverageType, group_for(final), total_ms,
            )
        except Exception as e:
            logger.exception("verify-stream pipeline error")
            yield _ndjson("error", {"detail": f"unexpected error: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


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
