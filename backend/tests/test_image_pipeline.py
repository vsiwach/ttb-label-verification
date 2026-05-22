"""Image pipeline: validation, legibility, ephemeral crops."""

import io

import pytest
from PIL import Image, ImageDraw

from app.image_pipeline import (
    ImageError,
    assess_image,
    clear_crop_store,
    crop_store_size,
    fetch_crop,
    store_crop,
)


def _sharp_png(w=1600, h=1200) -> bytes:
    """Create a high-contrast 'sharp' image with text-like edges."""
    img = Image.new("RGB", (w, h), color="white")
    draw = ImageDraw.Draw(img)
    # Stripes give the edge filter a lot of high-frequency content.
    for x in range(0, w, 20):
        draw.rectangle((x, 0, x + 10, h), fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _blurry_png(w=300, h=200) -> bytes:
    """Tiny, low-content image — low resolution + low edge variance."""
    img = Image.new("RGB", (w, h), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_sharp_image_is_legible_with_high_score():
    m = assess_image(_sharp_png())
    assert m.legible is True
    assert m.score >= 0.7
    assert m.width == 1600 and m.height == 1200


def test_blurry_low_res_image_is_not_legible():
    m = assess_image(_blurry_png())
    assert m.legible is False
    assert m.score < 0.55
    assert m.note  # should suggest re-uploading


def test_corrupt_bytes_raise_image_error():
    with pytest.raises(ImageError):
        assess_image(b"not an image")


def test_empty_bytes_raise_image_error():
    with pytest.raises(ImageError):
        assess_image(b"")


def test_crop_roundtrip_and_ttl_store():
    clear_crop_store()
    img = _sharp_png(800, 600)
    url = store_crop(img, (100, 50, 200, 150))
    assert url is not None and url.startswith("/crops/")
    crop_id = url.split("/")[-1]
    got = fetch_crop(crop_id)
    assert got is not None
    data, media = got
    assert media == "image/jpeg"
    assert len(data) > 0
    assert crop_store_size() >= 1


def test_invalid_bbox_returns_none():
    clear_crop_store()
    img = _sharp_png(800, 600)
    assert store_crop(img, (0, 0, 0, 0)) is None
    assert store_crop(img, (10_000, 10_000, 100, 100)) is None


def test_fetch_unknown_crop_id_returns_none():
    assert fetch_crop("nonexistent") is None
