"""Server-side image pipeline.

Two responsibilities:
  1. Validate the upload (open with Pillow, reject corrupt/unsupported files
     with a plain-language error) and measure legibility from pixel data.
  2. Generate cropped evidence images from extractor-returned bounding boxes,
     stored ephemerally in memory and served from /crops/{id} with a TTL.

Crops are NEVER persisted to disk. The store is in-memory only and entries
self-expire — see SECURITY.md.
"""

from __future__ import annotations

import io
import statistics
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageFilter, UnidentifiedImageError


class ImageError(Exception):
    """User-facing image errors -> 400 in the API layer."""


@dataclass
class ImageMeasurement:
    width: int
    height: int
    score: float        # 0..1 legibility score
    legible: bool
    note: Optional[str] = None
    # JPEG/PNG DPI metadata when present (x, y); None for screenshots /
    # stripped images. Needed for the 27 CFR 16.22 type-size check —
    # without DPI we can't convert pixel measurements to mm.
    dpi: Optional[tuple[int, int]] = None


_MIN_LEGIBLE_DIM = 400         # min(width, height) below this is "low resolution"
_TARGET_DIM = 1200             # at or above this is "good resolution"
_LEGIBLE_THRESHOLD = 0.55      # below this -> not legible


def assess_image(image_bytes: bytes) -> ImageMeasurement:
    """Open and measure the image. Raises ImageError on corrupt / unsupported.

    Score is the blended product of a sharpness proxy (variance of an
    edge-filtered grayscale, normalized to 0..1) and a resolution factor.
    """
    if not image_bytes:
        raise ImageError("Empty image upload.")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()  # force decode now so we surface errors here, not later
    except UnidentifiedImageError as e:
        raise ImageError(f"Unsupported or corrupt image file: {e}")
    except Exception as e:
        raise ImageError(f"Could not read image: {e}")

    w, h = img.size
    # Convert to grayscale, edge-filter, then compute variance over pixel
    # values. Higher variance == more high-frequency content == sharper.
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    pixels = list(edges.getdata())
    if not pixels:
        raise ImageError("Image has no decodable pixels.")
    var = statistics.pvariance(pixels)
    # Empirically: sharp phone photos hit var > ~1500, blurry/scanned <300.
    sharp = min(1.0, var / 1500.0)

    min_dim = min(w, h)
    if min_dim >= _TARGET_DIM:
        resolution = 1.0
    elif min_dim <= _MIN_LEGIBLE_DIM:
        resolution = 0.4
    else:
        # linear interpolation between MIN and TARGET
        resolution = 0.4 + 0.6 * (min_dim - _MIN_LEGIBLE_DIM) / (_TARGET_DIM - _MIN_LEGIBLE_DIM)

    score = round(0.55 * sharp + 0.45 * resolution, 3)
    legible = score >= _LEGIBLE_THRESHOLD

    note: Optional[str] = None
    if not legible:
        if sharp < 0.5 and resolution < 0.7:
            note = "Image appears blurry and low-resolution — re-upload a sharper, higher-resolution photo."
        elif sharp < 0.5:
            note = "Image appears blurry — re-upload a sharper photo."
        else:
            note = "Image resolution is low — re-upload a higher-resolution photo."
    elif min_dim < _TARGET_DIM:
        note = "Image is legible but could be sharper for best results."

    # DPI metadata — present for TTB-scraped labels and high-quality
    # scans; absent for phone photos and stripped images. The rules
    # engine uses this to convert pixel measurements to mm for the
    # type-size check.
    dpi_tuple: Optional[tuple[int, int]] = None
    raw_dpi = img.info.get("dpi")
    if raw_dpi and len(raw_dpi) == 2:
        try:
            xd, yd = int(round(raw_dpi[0])), int(round(raw_dpi[1]))
            if 50 <= xd <= 2400 and 50 <= yd <= 2400:  # sanity bounds
                dpi_tuple = (xd, yd)
        except (TypeError, ValueError):
            pass

    return ImageMeasurement(
        width=w, height=h, score=score, legible=legible, note=note, dpi=dpi_tuple,
    )


# ── Ephemeral crop store ────────────────────────────────────────────────────
# In-memory only; never persisted. Each crop has a TTL after which a cleanup
# pass on the next request will drop it. Designed for prototype scale.

_CROP_TTL_SECONDS = 600  # 10 minutes


@dataclass
class _CropEntry:
    data: bytes
    media_type: str
    expires_at: float


_crops: dict[str, _CropEntry] = {}


def _prune_expired(now: float | None = None) -> None:
    now = now if now is not None else time.time()
    expired = [k for k, v in _crops.items() if v.expires_at <= now]
    for k in expired:
        _crops.pop(k, None)


def store_crop(image_bytes: bytes, bbox: tuple[int, int, int, int]) -> Optional[str]:
    """Crop the image to bbox=(x, y, w, h) and store in memory. Returns a URL
    path like /crops/<id>, or None if the bbox is invalid.

    The crop is JPEG-encoded to keep the in-memory footprint modest.
    """
    x, y, w, h = bbox
    if w <= 0 or h <= 0:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        right = max(0, min(img.size[0], x + w))
        bottom = max(0, min(img.size[1], y + h))
        left = max(0, min(img.size[0], x))
        top = max(0, min(img.size[1], y))
        if right <= left or bottom <= top:
            return None
        crop = img.crop((left, top, right, bottom)).convert("RGB")
    except Exception:
        return None
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=82)
    crop_id = uuid.uuid4().hex
    _prune_expired()
    _crops[crop_id] = _CropEntry(
        data=buf.getvalue(),
        media_type="image/jpeg",
        expires_at=time.time() + _CROP_TTL_SECONDS,
    )
    return f"/crops/{crop_id}"


def fetch_crop(crop_id: str) -> Optional[tuple[bytes, str]]:
    _prune_expired()
    entry = _crops.get(crop_id)
    if entry is None:
        return None
    return entry.data, entry.media_type


def crop_store_size() -> int:
    """For test introspection."""
    _prune_expired()
    return len(_crops)


def clear_crop_store() -> None:
    _crops.clear()
