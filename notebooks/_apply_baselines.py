"""Apply the verified-working common baseline to all SFT training + eval
notebooks. Idempotent — safe to re-run after each notebook fix."""
import json
import re
from pathlib import Path


# ── The single canonical system prompt — used by Qwen, InternVL3 training,
#    and all three eval notebooks. The key change vs the original: EXPLICITLY
#    lists the exact field names so the model can't drift to snake_case or
#    invented variants. This addresses the 28pp accuracy gap we saw in the
#    Qwen baseline.
CANONICAL_SYSTEM_PROMPT = '''SYSTEM_PROMPT = (
    "You are a careful transcription assistant for U.S. TTB alcohol label review. "
    "Given ONE label panel image and the beverage type, READ what is printed and "
    "RETURN ONLY a JSON object matching the schema below. Do NOT decide compliance.\\n\\n"
    "CRITICAL — use ONLY these EXACT field names in the fields object (case-sensitive, "
    "preserve spaces and punctuation):\\n"
    "  - 'Brand name'\\n"
    "  - 'Class & type'\\n"
    "  - 'Alcohol content'\\n"
    "  - 'Net contents'\\n"
    "  - 'Bottler name/address'\\n"
    "  - 'Country of origin'  (imports only)\\n\\n"
    "Do NOT invent variants ('brand_name', 'Volume', 'Bottled_by', 'product_type', "
    "'location', etc). If a field is not clearly visible on this panel, OMIT it from "
    "the fields object entirely. Never guess; never substitute deposit codes "
    "(e.g. \\"CA CRV\\"), NOM IDs, or barcodes. Transcribe the Government Warning "
    "EXACTLY as printed (preserve case, punctuation, errors).\\n\\n"
    "For government_warning.casing_all_caps: TRUE if the literal text "
    "'GOVERNMENT WARNING' appears in ALL CAPS in the image; FALSE otherwise. "
    "For government_warning.body_bold: TRUE if the body text (after the heading) "
    "appears bold; FALSE otherwise (the body should NOT be bold per 27 CFR 16.22).\\n\\n"
    "Schema: {fields: {<field name>: {value, confidence}}, government_warning: "
    "{present, detected_text, casing_all_caps, heading_bold, body_bold, approx_font_mm, "
    "contrast_ok, separate_and_apart}, image_quality: {score, legible, note}}"
)'''


def _find_system_prompt_cell(data):
    """Return cell index of the cell that defines SYSTEM_PROMPT = ..."""
    for i, c in enumerate(data["cells"]):
        if c["cell_type"] != "code":
            continue
        src = "".join(c["source"])
        if re.search(r"^\s*SYSTEM_PROMPT\s*=", src, re.MULTILINE):
            return i
    return None


def _replace_system_prompt(data, idx):
    """Replace the first 'SYSTEM_PROMPT = (...)' assignment block with our
    canonical version. Preserves the rest of the cell verbatim."""
    cell = data["cells"][idx]
    src = "".join(cell["source"])

    # Match SYSTEM_PROMPT = ( ... ) including the closing paren — handle
    # nested parens by counting.
    m = re.search(r"^(\s*)SYSTEM_PROMPT\s*=\s*\(", src, re.MULTILINE)
    if not m:
        return False
    start = m.start()
    # Walk forward to find the matching close paren
    depth = 0
    i = src.index("(", start)
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    else:
        return False

    new_src = src[:start] + CANONICAL_SYSTEM_PROMPT + src[end:]
    if new_src == src:
        return False

    lines = new_src.splitlines(keepends=True)
    if lines and lines[-1].endswith("\n"):
        lines[-1] = lines[-1].rstrip("\n")
    cell["source"] = lines
    cell["outputs"] = []
    cell["execution_count"] = None
    return True


def apply_to(nb_path: Path) -> dict:
    """Apply baselines, return {changes_made: int, notes: [str]}."""
    if not nb_path.exists():
        return {"changes": 0, "notes": [f"SKIP: not found"]}
    data = json.loads(nb_path.read_text())
    changes = 0
    notes = []

    # 1. Replace SYSTEM_PROMPT with the canonical one
    idx = _find_system_prompt_cell(data)
    if idx is not None:
        if _replace_system_prompt(data, idx):
            changes += 1
            notes.append(f"updated SYSTEM_PROMPT in cell {idx}")
        else:
            notes.append(f"SYSTEM_PROMPT in cell {idx} already canonical or unparseable")
    else:
        notes.append("no SYSTEM_PROMPT cell found — skipping")

    if changes > 0:
        nb_path.write_text(json.dumps(data, indent=1) + "\n")
    return {"changes": changes, "notes": notes}


TARGETS = [
    # Training notebooks (all BF16, all use direct transformers + peft + trl)
    "notebooks/sft_qwen2_5_vl.ipynb",
    "notebooks/sft_internvl3_2b.ipynb",
    "notebooks/sft_donut_v2.ipynb",
    # Eval notebooks (all use Drive mount + same JSONL output format)
    "notebooks/eval_qwen_drive.ipynb",
    "notebooks/eval_internvl3_drive.ipynb",
    "notebooks/eval_donut_drive.ipynb",
]


for path in TARGETS:
    result = apply_to(Path(path))
    status = "✓" if result["changes"] > 0 else "—"
    print(f"  {status} {path:<50}  {'; '.join(result['notes'])}")
