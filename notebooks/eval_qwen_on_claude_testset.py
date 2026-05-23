"""Paste this whole block as ONE cell into the Colab notebook where you
trained Qwen2.5-VL (the kernel still has `model` and `tokenizer` /
`processor` in memory).

It will:
  1. Prompt you to upload cola_sample.csv (from this repo's
     test/eval/data/ directory) — that's the same ground-truth file
     Claude was scored against.
  2. Re-download every referenced image from the COLA Cloud CDN
     (~117 images, ~1 minute).
  3. Run Qwen on each, parse the JSON output.
  4. Compute per-field accuracy using the SAME `fields_match_loose`
     logic as test/eval/run_eval.py — so the number is directly
     comparable to Claude's report.
  5. Save qwen_on_claude_testset_report.json + auto-download it to
     your Mac's ~/Downloads. We'll commit that into the repo as
     the apples-to-apples comparison.

Expected runtime on A100: ~10 minutes (3 s/image inference).
Output filename: qwen_on_claude_testset_report.json
"""

# ──────────────────────────────────────────────────────────────────────────────
# 1. Upload cola_sample.csv
# ──────────────────────────────────────────────────────────────────────────────
import csv, io, json, re, time, urllib.request, concurrent.futures
from pathlib import Path
from collections import Counter

from google.colab import files
print("Upload test/eval/data/cola_sample.csv from your Mac:")
uploaded = files.upload()
csv_name = next(iter(uploaded))
csv_text = uploaded[csv_name].decode("utf-8")
rows = list(csv.DictReader(io.StringIO(csv_text)))
print(f"Loaded {len(rows)} rows from {csv_name}")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Download images from the COLA Cloud CDN
# ──────────────────────────────────────────────────────────────────────────────
EVAL_DIR = Path("/content/qwen_eval")
EVAL_DIR.mkdir(exist_ok=True)
IMG_DIR = EVAL_DIR / "images"
IMG_DIR.mkdir(exist_ok=True)
CDN = "https://dyuie4zgfxmt6.cloudfront.net/{}.webp"

def _dl(row):
    image_id = row["ttb_image_id"]
    dest = IMG_DIR / f"{image_id}.webp"
    if dest.exists() and dest.stat().st_size > 0:
        return row, True
    try:
        req = urllib.request.Request(CDN.format(image_id),
                                     headers={"User-Agent": "ttb-eval/0.1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            dest.write_bytes(r.read())
        return row, True
    except Exception as e:
        print(f"  download fail {image_id}: {e}")
        return row, False

downloaded = []
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
    for row, ok in ex.map(_dl, rows):
        if ok:
            row["_image_path"] = str(IMG_DIR / f"{row['ttb_image_id']}.webp")
            downloaded.append(row)
print(f"Downloaded {len(downloaded)} / {len(rows)} images")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Run Qwen on each (uses model/tokenizer already in kernel memory)
# ──────────────────────────────────────────────────────────────────────────────
import torch
from PIL import Image
from unsloth import FastVisionModel
FastVisionModel.for_inference(model)  # noqa: F821 — defined earlier in your notebook

SYSTEM_PROMPT = (
    "You are a careful transcription assistant for U.S. TTB alcohol label review. "
    "Given ONE label panel image and the beverage type, READ what is printed and "
    "RETURN ONLY a JSON object matching the schema below. Do NOT decide compliance.\n\n"
    "If a field is not clearly visible, OMIT it from the fields object. Never guess; "
    "never substitute deposit codes (e.g. \"CA CRV\"), NOM IDs, or barcodes. Transcribe "
    "the Government Warning EXACTLY as printed (preserve case, punctuation, errors).\n\n"
    "Schema: {fields: {<field name>: {value, confidence}}, government_warning: "
    "{present, detected_text, casing_all_caps, heading_bold, body_bold, approx_font_mm, "
    "contrast_ok, separate_and_apart}, image_quality: {score, legible, note}}"
)

def _qwen_extract(image_path: str, beverage_type: str) -> dict | None:
    img = Image.open(image_path).convert("RGB")
    msgs = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {"role": "user",   "content": [
            {"type": "image", "image": img},
            {"type": "text",  "text": f"Beverage type: {beverage_type}. Extract per the schema."},
        ]},
    ]
    text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)  # noqa: F821
    inputs = tokenizer(text=text, images=[img], return_tensors="pt").to(model.device)  # noqa: F821
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=512, do_sample=False)  # noqa: F821
    decoded = tokenizer.batch_decode(  # noqa: F821
        out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
    )[0]
    s, e = decoded.find("{"), decoded.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(decoded[s:e+1])
    except json.JSONDecodeError:
        cleaned = re.sub(r",(\s*[}\]])", r"\1", decoded[s:e+1])
        try: return json.loads(cleaned)
        except Exception: return None

# ──────────────────────────────────────────────────────────────────────────────
# 4. Field-match logic — IDENTICAL to test/eval/run_eval.py fields_match_loose
# ──────────────────────────────────────────────────────────────────────────────
_UMBRELLA_CLASSES = {
    "beer", "ale", "lager", "malt beverage", "table red wine", "table white wine",
    "table wine", "table rose wine", "sparkling wine", "dessert wine", "whisky",
    "vodka", "gin", "rum", "tequila", "brandy", "cordial", "liqueur",
    "whisky specialties", "distilled spirits specialty",
}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.,]", "", (s or "").strip().lower()))

def _parse_ml(s: str) -> float | None:
    if not s: return None
    s = s.lower()
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*ml", s)
    if m: return float(m.group(1))
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*l\b", s)
    if m: return float(m.group(1)) * 1000
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*fl\s*oz", s)
    if m: return float(m.group(1)) * 29.5735
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*pint", s)
    if m: return float(m.group(1)) * 473.176
    return None

def fields_match_loose(declared: str, extracted: str, *, field_name: str = "") -> bool:
    a, b = _norm(declared), _norm(extracted)
    if not a or not b: return False
    if a == b or a in b or b in a: return True
    if "net" in field_name.lower():
        da, db = _parse_ml(declared), _parse_ml(extracted)
        if da is not None and db is not None:
            return abs(da - db) / max(da, db) <= 0.05
    if "class" in field_name.lower():
        if a in _UMBRELLA_CLASSES or b in _UMBRELLA_CLASSES: return True
        stop = {"of", "the", "a", "wine", "beer", "table", "and"}
        toks_a = [t for t in re.split(r"\W+", a) if t and t not in stop]
        toks_b = [t for t in re.split(r"\W+", b) if t and t not in stop]
        if toks_a and any(t in b for t in toks_a): return True
        if toks_b and any(t in a for t in toks_b): return True
    return False

# CSV column → schema field name mapping (matches run_eval.py)
CSV_FIELD_MAP = {
    "brand_name":              "Brand name",
    "class_type":              "Class & type",
    "alcohol_content":         "Alcohol content",
    "net_contents":            "Net contents",
    "bottler_name_address":    "Bottler name/address",
    "origin":                  "Country of origin",
}

# ──────────────────────────────────────────────────────────────────────────────
# 5. Run extraction + score
# ──────────────────────────────────────────────────────────────────────────────
field_correct = Counter()
field_total = Counter()
n_parsed = n_unparseable = 0
warn_match = warn_total = 0
latencies = []
misses = []

print(f"\nExtracting on {len(downloaded)} images...")
for i, row in enumerate(downloaded, 1):
    bev = (row.get("beverage_type") or "wine").lower()
    t0 = time.time()
    pred = _qwen_extract(row["_image_path"], bev)
    latencies.append(time.time() - t0)
    if pred is None:
        n_unparseable += 1
        if i % 10 == 0: print(f"  [{i}/{len(downloaded)}] unparseable")
        continue
    n_parsed += 1

    # Per-field
    for csv_col, schema_name in CSV_FIELD_MAP.items():
        declared = (row.get(csv_col) or "").strip()
        if not declared:  # COLA didn't declare this field — skip (matches run_eval.py)
            continue
        field_total[schema_name] += 1
        got = ((pred.get("fields") or {}).get(schema_name) or {}).get("value", "")
        if fields_match_loose(declared, got, field_name=schema_name):
            field_correct[schema_name] += 1
        else:
            misses.append({
                "image_id": row["ttb_image_id"],
                "field": schema_name,
                "declared": declared,
                "extracted": got,
            })

    # Warning presence
    warn_total += 1
    gt_warning = bool((row.get("image_ocr_text") or "").upper().find("GOVERNMENT WARNING") != -1)
    pred_warning = bool((pred.get("government_warning") or {}).get("present"))
    if gt_warning == pred_warning:
        warn_match += 1

    if i % 10 == 0:
        print(f"  [{i}/{len(downloaded)}] parsed={n_parsed} ({_qwen_extract.__name__})")

# ──────────────────────────────────────────────────────────────────────────────
# 6. Report
# ──────────────────────────────────────────────────────────────────────────────
import statistics
report = {
    "mode": "qwen2_5_vl_7b_lora_on_claude_testset",
    "n_total": len(downloaded),
    "n_parsed": n_parsed,
    "n_unparseable": n_unparseable,
    "field_total": sum(field_total.values()),
    "field_correct": sum(field_correct.values()),
    "field_extraction_accuracy": round(sum(field_correct.values()) / max(sum(field_total.values()), 1), 4),
    "warning_present_accuracy": round(warn_match / max(warn_total, 1), 4),
    "per_field_accuracy": {
        f: {"correct": field_correct[f], "total": field_total[f],
            "accuracy": round(field_correct[f] / field_total[f], 4) if field_total[f] else None}
        for f in sorted(field_total)
    },
    "latency_mean": round(statistics.mean(latencies), 3),
    "latency_p95":  round(sorted(latencies)[int(len(latencies)*0.95)], 3) if latencies else None,
    "misses_sample": misses[:30],
}

out_path = EVAL_DIR / "qwen_on_claude_testset_report.json"
out_path.write_text(json.dumps(report, indent=2))
print()
print("=" * 70)
print(f"Aggregate field extraction:  {report['field_correct']}/{report['field_total']} = {report['field_extraction_accuracy']:.2%}")
print(f"Warning presence accuracy:   {warn_match}/{warn_total} = {report['warning_present_accuracy']:.2%}")
print(f"Latency mean / p95:          {report['latency_mean']}s / {report['latency_p95']}s")
print()
for f, v in report["per_field_accuracy"].items():
    print(f"  {f:<24} {v['correct']:>3} / {v['total']:>3} = {(v['accuracy'] or 0):.1%}")
print("=" * 70)
print(f"\nReport written to {out_path} — auto-downloading...")

files.download(str(out_path))
