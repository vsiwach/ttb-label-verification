"""CPU-only Modal endpoint — Tesseract OCR for the deterministic 16.22 inputs.

Split out of serve_qwen_v2.py to keep the Qwen container small and warm.
This file's container has NO GPU, NO ML deps, and starts in ~1-2s cold —
small enough to run in parallel with the Qwen call from the Vercel side
without pushing the warm-path latency budget.

Outputs (returned as JSON):
  - warning_bbox_h_px : pixel height of the "GOVERNMENT WARNING" preamble.
                        Combined with image DPI in the rules engine, gives
                        the 27 CFR 16.22 mm-per-line measurement.
  - dpi               : DPI read from PIL EXIF (None when the image lacks
                        the JPEG/PNG header field).
  - warning_text      : Verbatim transcription from "GOVERNMENT WARNING:"
                        onward. Used as the warning-text source when
                        Haiku isn't configured.
  - alcohol_content   : Regex match against the OCR text (deterministic
                        fallback when Haiku misreads or isn't configured).
  - net_contents      : Same.

Cold start: ~1-2s (Debian slim + tesseract apt package + pytesseract).
Warm:       ~0.5-1s per request (Tesseract on a 1200-3000px image).

Deploy:
    backend/.venv/bin/modal deploy backend/modal_deploy/serve_tesseract.py
"""
from __future__ import annotations

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("tesseract-ocr", "libtesseract-dev")
    .pip_install(
        "pytesseract>=0.3.10",
        "pillow",
        "fastapi[standard]",
    )
)

app = modal.App("ttb-tesseract")


def _tesseract_observe(raw_image_bytes: bytes) -> dict:
    """One OCR pass yields the four deterministic warning observations.

    Tesseract gets the full-resolution image (not a downscaled version)
    and benefits from at least 1200px tall when body text is ~12-16px on
    the original. Cap at 3000px to keep latency bounded.
    """
    import io
    import re
    import pytesseract
    from PIL import Image
    from pytesseract import Output

    out: dict = {
        "alcohol_content":   "",
        "net_contents":      "",
        "warning_text":      "",
        "warning_bbox_h_px": None,
        "dpi":               None,
    }

    try:
        ocr_img = Image.open(io.BytesIO(raw_image_bytes)).convert("RGB")
        w0, h0 = ocr_img.size  # ORIGINAL image dims — paired with EXIF DPI
        scale = 1.0
        if h0 < 1200:
            scale = 1200 / h0
            ocr_img = ocr_img.resize((int(w0 * scale), int(h0 * scale)), Image.LANCZOS)
        elif h0 > 3000:
            scale = 3000 / h0
            ocr_img = ocr_img.resize((int(w0 * scale), int(h0 * scale)), Image.LANCZOS)
    except Exception as e:
        out["tesseract_error"] = f"open: {e}"
        return out

    # DPI from EXIF (read from raw bytes, not the resized OCR image)
    try:
        exif_img = Image.open(io.BytesIO(raw_image_bytes))
        dpi = exif_img.info.get("dpi")
        if dpi and isinstance(dpi, tuple) and dpi[1] > 0:
            out["dpi"] = float(dpi[1])
    except Exception:
        pass

    try:
        data = pytesseract.image_to_data(ocr_img, output_type=Output.DICT)
    except Exception as e:
        out["tesseract_error"] = str(e)
        return out

    words = data.get("text", [])
    n = len(words)
    full_text = " ".join(w for w in words if (w or "").strip())

    abv_m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*%\s*(?:Alc\.?\s*(?:/|by\s+)?Vol\.?(?:ume)?|ALC\.?\s*/?\s*VOL\.?|alc\.?\s*/?\s*vol\.?)",
        full_text,
        flags=re.IGNORECASE,
    )
    if abv_m:
        value = abv_m.group(1).replace(",", ".")
        out["alcohol_content"] = f"{value}% Alc./Vol."
    else:
        proof_m = re.search(r"(\d+(?:[.,]\d+)?)\s*Proof\b", full_text, flags=re.IGNORECASE)
        if proof_m:
            value = proof_m.group(1).replace(",", ".")
            out["alcohol_content"] = f"{value} Proof"

    net_m = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(mL|ml|ML|L\b|fl\.?\s*oz|FL\.?\s*OZ|pints?|gal(?:lons?)?|liter|litre)",
        full_text,
    )
    if net_m:
        value = net_m.group(1).replace(",", ".")
        unit = net_m.group(2)
        unit_norm = re.sub(r"\s+", " ", unit).strip()
        if re.match(r"^ml$", unit_norm, flags=re.IGNORECASE):
            unit_norm = "mL"
        elif re.match(r"^l$", unit_norm, flags=re.IGNORECASE):
            unit_norm = "L"
        elif re.match(r"^fl\.?\s*oz$", unit_norm, flags=re.IGNORECASE):
            unit_norm = "fl oz"
        out["net_contents"] = f"{value} {unit_norm}"

    # Government Warning — find "GOVERNMENT" then the next non-empty
    # token starting with "WARNING". Tesseract sprinkles empty strings
    # between real words; we walk past them. The heights returned by
    # Tesseract are in the UPSCALED image coordinates (we may have
    # resized small images up to 1200px tall for OCR accuracy); divide
    # by `scale` so the returned bbox is in ORIGINAL image pixels, which
    # is what the rule engine pairs with the EXIF DPI for mm/line math.
    warning_start_idx = None
    for i in range(n):
        wi = (words[i] or "").strip().upper()
        if wi != "GOVERNMENT":
            continue
        for j in range(i + 1, n):
            wj = (words[j] or "").strip().upper()
            if not wj:
                continue
            if wj.startswith("WARNING"):
                warning_start_idx = i
                h_upscaled = max(int(data["height"][i] or 0), int(data["height"][j] or 0))
                if h_upscaled > 0:
                    # Back-scale to original-image pixel coordinates so
                    # `bbox_h_px / original_dpi * 25.4` gives true mm.
                    out["warning_bbox_h_px"] = max(int(round(h_upscaled / scale)), 1)
            break
        if warning_start_idx is not None:
            break

    if warning_start_idx is not None:
        preamble_h = max(int(data["height"][warning_start_idx] or 0), 1)
        text_words = []
        last_y = int(data["top"][warning_start_idx] or 0)
        for k in range(warning_start_idx, n):
            w = (words[k] or "").strip()
            if not w:
                continue
            y = int(data["top"][k] or 0)
            if y - last_y > preamble_h * 6:
                break
            text_words.append(w)
            last_y = y
        out["warning_text"] = " ".join(text_words)

    return out


@app.function(image=image, timeout=60, scaledown_window=300)
@modal.fastapi_endpoint(method="POST", docs=True)
def tesseract_web(payload: dict) -> dict:
    """POST {image_b64} → deterministic OCR observations.

    Designed to be called in parallel with the Qwen Modal endpoint from
    the Vercel function. Wall-clock per warm call: ~0.5-1s.
    """
    import base64
    import time

    img_b64 = payload.get("image_b64")
    if not img_b64:
        return {"error": "missing image_b64 in payload"}

    t0 = time.time()
    try:
        result = _tesseract_observe(base64.b64decode(img_b64))
    except Exception as e:
        return {"error": str(e)[:300]}
    result["latency_sec"] = round(time.time() - t0, 3)
    return result


@app.function(image=image, timeout=10)
@modal.fastapi_endpoint(method="GET", docs=True)
def health_web() -> dict:
    """Warm-check probe. Returns immediately when the container is alive."""
    return {"ok": True}
