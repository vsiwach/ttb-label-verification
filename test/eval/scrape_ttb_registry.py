"""Polite scraper for the TTB Public COLA Registry.

Pulls the full Form 5100.31 data for a configurable number of recently
approved COLAs + downloads the actual label image (with DPI metadata).

Source: https://www.ttbonline.gov/colasonline/  (public, no auth required)

Why this exists:
  Our COLA Cloud free-sample CSV (test/eval/data/cola_sample.csv) has the
  bottler field empty on ~95% of rows. Without real filed application
  data the engine can't fairly compare declared vs printed. This scraper
  pulls real TTB filings — every field on the form, including bottler —
  so we can measure the engine's accuracy on properly-paired data.

Output layout:
  test/eval/data/ttb_live/
    ttb_live.csv          one row per scraped COLA
    images/
      <ttb_id>.jpg        label artwork (often with DPI metadata)

Usage:
  python test/eval/scrape_ttb_registry.py --count 50
  python test/eval/scrape_ttb_registry.py --count 200 --from 2024-06-01

Polite defaults:
  - 1 request per second (sleep between calls)
  - One session, reused for cookies
  - Resumable: skip ttb_ids already in ttb_live.csv

Maintenance: TTB redesigns this site occasionally. If a parse breaks,
inspect the saved HTML in /tmp/ttb-* (see investigation notes).
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import certifi
import requests
import urllib3

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "test" / "eval" / "data" / "ttb_live"
OUT_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR = OUT_DIR / "images"
IMG_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "ttb_live.csv"

BASE = "https://www.ttbonline.gov/colasonline"
HEADERS = {
    "User-Agent": (
        "TTB-Label-Verification-Prototype/1.0 "
        "(government-research; contact: vsiwach@gmail.com)"
    ),
}
POLITE_DELAY = 0.5  # seconds between requests

# CSV schema — matches the columns we extract from the form view
CSV_COLUMNS = [
    "ttb_id",
    "vendor_code",
    "serial_number",
    "approval_date",
    "status",
    "type_of_application",
    "brand_name",
    "fanciful_name",
    "class_type_description",
    "origin_code",
    "alcohol_content",
    "net_contents",
    "name_address_applicant",     # the bottler/producer line — what we need
    "grape_varietal",
    "wine_appellation",
    "image_filename",
    "image_url",
    "image_dpi",                  # comma-separated, e.g. "200,200"
    "image_type",                 # "Back" / "Brand (front) or keg collar" / etc
    "image_count",                # total label panels available
    "scraped_at",
]


# ── Session helpers ─────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    # Point at certifi's CA bundle (the brew Python venv doesn't pick
    # up the system one). ttbonline.gov uses an Entrust cert but doesn't
    # send the intermediate in the chain, so the verify still fails
    # (curl chases AIA, Python requests doesn't). For public read-only
    # data on a known .gov domain we disable verify and silence the
    # warning. We're only reading, never sending sensitive data.
    s.verify = False
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    _ = certifi.where()  # imported for future when chain is fixed
    # Touch the search page once to establish the JSESSIONID cookie.
    s.get(f"{BASE}/publicSearchColasBasic.do", timeout=15)
    return s


def polite_sleep() -> None:
    time.sleep(POLITE_DELAY)


# ── Search results: returns a list of TTB IDs ───────────────────────────────

def search_ttb_ids(
    session: requests.Session,
    date_from: date,
    date_to: date,
    max_pages: int = 20,
    class_codes: list[str] | None = None,
) -> list[str]:
    """Search the registry by date range; return all TTB IDs found.

    With class_codes set, uses the advanced-search endpoint to filter by
    TTB class type (e.g. wine codes 80-89). Without it, uses the basic
    endpoint (preserves original behavior for `make scrape-ttb`).

    NOTE: TTB hard-caps every search query to 20 results — both endpoints.
    The pn=N pager exists but the server ignores it and returns the same
    first page. So the strategy that actually works is: walk many narrow
    date windows. The caller (scrape loop) does this; this function just
    runs one query and returns up to 20 ttbids.
    """
    if class_codes:
        # Advanced search with class-type filter (multi-value array param)
        payload: list[tuple[str, str]] = [
            ("searchCriteria.dateCompletedFrom", date_from.strftime("%m/%d/%Y")),
            ("searchCriteria.dateCompletedTo",   date_to.strftime("%m/%d/%Y")),
            ("searchCriteria.productNameSearchType", "E"),
            ("searchCriteria.classTypeDesired", "code"),
        ] + [("searchCriteria.classTypeCodeArrayByCode", c) for c in class_codes]
        url = f"{BASE}/publicSearchColasAdvancedProcess.do?action=search"
        print(f"[search] {date_from} → {date_to}  ({len(class_codes)} class codes)", flush=True)
    else:
        payload = list({
            "searchCriteria.dateCompletedFrom": date_from.strftime("%m/%d/%Y"),
            "searchCriteria.dateCompletedTo":   date_to.strftime("%m/%d/%Y"),
            "searchCriteria.productNameSearchType": "E",
        }.items())
        url = f"{BASE}/publicSearchColasBasicProcess.do?action=search"
        print(f"[search] {date_from} → {date_to}", flush=True)

    polite_sleep()
    r = session.post(url, data=payload, timeout=20)
    r.raise_for_status()
    ids: list[str] = re.findall(r"ttbid=(\d+)", r.text)
    # Dedupe while preserving order — the result table renders each ttbid
    # twice (link + display).
    seen: set[str] = set()
    out: list[str] = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    print(f"[search] {len(out)} unique ids", flush=True)
    return out


# ── Form parsing ────────────────────────────────────────────────────────────

_LABEL_DATA_RE = re.compile(
    r'<div class="(?:bold)?label">([^<]+?)</div>\s*<div class="data"[^>]*>([^<]*?)</div>',
    re.DOTALL,
)
_CLASS_TYPE_DESC_RE = re.compile(
    r'<div class="boldlabel">CLASS/TYPE DESCRIPTION</div>\s*<div class="data">\s*([^<]+?)\s*<',
    re.IGNORECASE | re.DOTALL,
)
_APPLICANT_BLOCK_RE = re.compile(
    r'NAME AND ADDRESS OF APPLICANT.*?</div>(.+?)<div class="(?:bold)?label">',
    re.IGNORECASE | re.DOTALL,
)
_FANCIFUL_RE = re.compile(
    r'<div class="boldlabel">7\.\s*FANCIFUL NAME[^<]*</div>\s*<div class="data">\s*([^<]*?)\s*<',
    re.IGNORECASE | re.DOTALL,
)
_IMAGE_RE = re.compile(
    r'src="(/colasonline/publicViewAttachment\.do\?filename=([^"&]+)&filetype=l)"\s*'
    r'width="\d+"\s+height="\d+"\s+alt="Label Image:\s*([^"]+)"',
    re.IGNORECASE | re.DOTALL,
)
_ORIGIN_RE = re.compile(
    r'<div class="label">OR</div>\s*<div class="data">\s*([^<]*?)\s*<',
    re.IGNORECASE | re.DOTALL,
)


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    # Decode HTML entities — TTB form HTML uses numeric character references
    # (&#x27;, &#39;, &#x23;) for punctuation in proper nouns.
    s = html.unescape(s)
    s = s.replace("\xa0", " ")  # non-breaking space → regular space
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_form(html: str) -> dict:
    """Extract the fields we care about from a Form 5100.31 view."""
    out: dict = {}
    for label, val in _LABEL_DATA_RE.findall(html):
        lbl = _clean(label).rstrip(":").upper()
        v = _clean(val)
        if not v:
            continue
        if lbl == "TTB ID":            out["ttb_id"] = v
        elif lbl == "CT":              out["vendor_code"] = v
        elif lbl == "OR":              out["origin_code_basic"] = v
        elif lbl.startswith("4. SERIAL"): out["serial_number"] = v
        elif lbl.startswith("12. PHONE"): out["phone"] = v
        elif lbl.startswith("16. DATE OF APPLICATION"): out["app_date"] = v
        elif lbl.startswith("19. DATE ISSUED"): out["approval_date"] = v

    # Brand name. The boldlabel often contains <I>(Required)</I> inside,
    # so use DOTALL + permissive .*? rather than [^<]*.
    m = re.search(
        r'<div class="boldlabel">\s*6\.\s*BRAND NAME.*?</div>\s*<div class="data"[^>]*>\s*(.*?)\s*</div>',
        html, re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["brand_name"] = _clean(m.group(1))

    # Fanciful name (field 7)
    m = re.search(
        r'<div class="boldlabel">\s*7\.\s*FANCIFUL NAME.*?</div>\s*<div class="data"[^>]*>\s*(.*?)\s*</div>',
        html, re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["fanciful_name"] = _clean(m.group(1))

    # Class/type description (the freetext field — e.g. "Kentucky Straight
    # Bourbon Whiskey" — not the umbrella code).
    m = re.search(
        r'<div class="boldlabel">\s*CLASS/TYPE DESCRIPTION\s*</div>\s*<div class="data"[^>]*>\s*(.*?)\s*</div>',
        html, re.IGNORECASE | re.DOTALL,
    )
    if m:
        out["class_type_description"] = _clean(m.group(1))

    # Applicant name + address (field 8 — the bottler!). The form
    # structure is: <div class="label">8. NAME AND ADDRESS...</div>
    # <br> <div class="data"> NAME<br> STREET<br> CITY, STATE ZIP<br> </div>
    m = re.search(
        r'<div class="label">\s*8\.\s*NAME AND ADDRESS.*?</div>'  # the label div
        r'(?:\s*<br[^>]*>)?\s*'
        r'<div class="data"[^>]*>\s*(.*?)\s*</div>',
        html, re.IGNORECASE | re.DOTALL,
    )
    if m:
        flat = _clean(m.group(1))
        out["name_address_applicant"] = flat[:300]

    # NOTE: TTB Form 5100.31 does NOT have dedicated fields for Alcohol
    # Content or Net Contents — those are verified visually on the label
    # image by the agent. Earlier versions of this scraper had regexes
    # that grabbed unrelated text from the form's qualifications section
    # (e.g. "NET CONTENTS MAY OR MAY NOT BE IMPRINTED..."), which was
    # both wrong and confusing. Leaving these as empty strings is the
    # honest behavior — the engine handles empty declared values by
    # showing the label-extracted value with a note for the agent.

    # Label images: COLAs have multiple panels (front / back / neck /
    # other) and the application is verified across ALL of them. Capture
    # every panel so the scraper can download + stitch them into a
    # single composite the engine can verify in one pass.
    images = _IMAGE_RE.findall(html)
    if images:
        # tuples (url_path, filename, image_type)
        panels = []
        for url_path, fname, alt in images:
            panels.append({
                "url": BASE + url_path.split("/colasonline", 1)[1],
                "remote_filename": fname,
                "image_type": alt.strip(),
            })
        out["_panels"] = panels  # private key used by scrape loop

    return out


def parse_basic_detail(html: str) -> dict:
    """Pull a few extras from the basic detail page (origin, status)."""
    out: dict = {}
    # The basic detail uses <strong>Label: </strong>...<value>... pattern
    chunks = re.split(r"<strong>([^<]+?):\s*</strong>", html)
    for i in range(1, len(chunks) - 1, 2):
        label = _clean(chunks[i]).rstrip(":").upper()
        raw = chunks[i + 1]
        text = re.split(r"<(?:strong|tr|table|p\b|h\d|hr|/td)", raw)[0]
        v = _clean(text)
        if not v or len(v) > 200:
            continue
        if label == "STATUS":
            out["status"] = v
        elif label == "ORIGIN CODE":
            out["origin_code"] = v
        elif label == "TYPE OF APPLICATION":
            out["type_of_application"] = v
        elif label == "CLASS/TYPE CODE":
            out["class_type_code"] = v
    return out


# ── Image download with DPI extraction ──────────────────────────────────────

def download_image(session: requests.Session, url: str, dest: Path) -> tuple[bool, str]:
    """Download an image; return (success, dpi_str). dpi_str like "200,200".

    No polite_sleep here — callers control pacing. This function is also
    invoked from a thread pool (download_panels_parallel) where serialized
    sleeps would defeat the parallelism.
    """
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        dest.write_bytes(r.content)
    except Exception as e:
        print(f"[image] download failed: {e}", flush=True)
        return False, ""

    dpi = ""
    try:
        from PIL import Image  # type: ignore
        img = Image.open(dest)
        dpi_tuple = img.info.get("dpi")
        if dpi_tuple:
            dpi = f"{int(dpi_tuple[0])},{int(dpi_tuple[1])}"
    except Exception:
        pass
    return True, dpi


def download_panels_parallel(
    session: requests.Session,
    panels: list[dict],
    dest_dir: Path,
    max_workers: int = 3,
) -> tuple[list[Path], list[str]]:
    """Download a COLA's panels concurrently. Returns (paths, image_types).

    Stays polite by capping workers at 3 — three concurrent downloads
    to a single .gov host is well within courtesy norms (browsers open
    6-8 conns/host) and the bottleneck moves from network round-trips
    to TTB's per-image server-side render time, which is what we want.

    A single polite_sleep is paid BEFORE the burst (caller-controlled);
    no inter-panel sleeps inside the burst.
    """
    def _one(idx_panel):
        i, panel = idx_panel
        safe = f"panel_{i:02d}_{_panel_rank(panel['image_type'])}.jpg"
        dest = dest_dir / safe
        ok, _ = download_image(session, panel["url"], dest)
        return (i, panel["image_type"], dest if ok else None)

    polite_sleep()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(_one, list(enumerate(panels))))
    # Re-sort by panel index to preserve front→back→neck ordering for stitch
    results.sort(key=lambda t: t[0])
    paths = [r[2] for r in results if r[2] is not None]
    types = [r[1] for r in results if r[2] is not None]
    return paths, types


# Panel-type priority — used both for picking the "primary" image and for
# ordering panels in the stitched composite (front on top, then back, etc).
_PANEL_PRIORITY = {
    "brand (front)": 0, "brand": 0, "front": 0, "keg collar": 0,
    "back": 1, "neck": 2, "strip": 3, "other": 4,
}


def _panel_rank(image_type: str) -> int:
    t = (image_type or "").lower()
    # First word match wins
    for key, rank in _PANEL_PRIORITY.items():
        if key in t:
            return rank
    return 5


def stitch_panels(panel_paths: list[Path], dest: Path) -> tuple[bool, str]:
    """Stack the panel images vertically into a single composite.

    Order: front, back, neck, strip, other (mirrors how a printed COLA
    submission lays out, and what the agent would scan). Preserves the
    front panel's DPI metadata so downstream type-size checks work.

    Returns (success, dpi_str).
    """
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return False, ""
    if not panel_paths:
        return False, ""

    images: list[Image.Image] = []
    dpi_tuple: tuple[int, int] | None = None
    for p in panel_paths:
        try:
            img = Image.open(p)
            img.load()
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)
            if dpi_tuple is None and img.info.get("dpi"):
                dt = img.info["dpi"]
                dpi_tuple = (int(dt[0]), int(dt[1]))
        except Exception as e:
            print(f"  stitch: skipping panel {p.name}: {e}", flush=True)
            continue
    if not images:
        return False, ""

    SEP = 24  # white separator between panels
    max_w = max(i.width for i in images)
    total_h = sum(i.height for i in images) + SEP * (len(images) - 1)
    composite = Image.new("RGB", (max_w, total_h), "white")
    y = 0
    for img in images:
        # Center horizontally
        x = (max_w - img.width) // 2
        composite.paste(img, (x, y))
        y += img.height + SEP

    save_kwargs: dict = {"quality": 90}
    if dpi_tuple:
        save_kwargs["dpi"] = dpi_tuple
    composite.save(dest, "JPEG", **save_kwargs)
    return True, (f"{dpi_tuple[0]},{dpi_tuple[1]}" if dpi_tuple else "")


# ── Main scrape loop ────────────────────────────────────────────────────────

def load_existing() -> set[str]:
    if not CSV_PATH.exists():
        return set()
    done: set[str] = set()
    with open(CSV_PATH) as f:
        for r in csv.DictReader(f):
            if r.get("ttb_id"):
                done.add(r["ttb_id"])
    return done


def append_csv(rows: list[dict]) -> None:
    """Append rows, writing the header only if the file is new."""
    new_file = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def scrape(
    count: int,
    date_from: date,
    date_to: date,
    class_codes: list[str] | None = None,
    per_window: int = 5,
) -> int:
    session = make_session()
    print(f"[init] session established", flush=True)

    existing = load_existing()
    print(f"[init] {len(existing)} ttb_ids already scraped, will skip them", flush=True)

    # Walk back through dates if we need more results than one window
    # provides. Use 1-day windows so successive runs sample DIFFERENT
    # applicants — TTB tends to batch-approve from one brewery, so a
    # 7-day window often returns 20 from the same producer.
    #
    # per_window caps how many we pull from each day-search:
    #   - default 5 (original behavior, keeps variety high when scraping
    #     undifferentiated)
    #   - 20 (the TTB cap) when stratifying by class — class filter
    #     already enforces variety, so take everything the search gives.
    cursor_to = date_to
    cursor_from = cursor_to
    collected: list[str] = []
    while len(collected) < count and cursor_from >= date_from:
        try:
            ids = search_ttb_ids(session, cursor_from, cursor_to, class_codes=class_codes)
        except Exception as e:
            print(f"[search] failed: {e}", flush=True)
            break
        added = 0
        for tid in ids:
            if tid in existing or tid in collected:
                continue
            collected.append(tid)
            added += 1
            if added >= per_window or len(collected) >= count:
                break
        # Slide window backward by one day
        cursor_to = cursor_from - timedelta(days=1)
        cursor_from = cursor_to

    target = collected[:count]
    print(f"[init] will scrape {len(target)} new COLAs", flush=True)

    successes = 0
    failures = 0
    pending: list[dict] = []
    for idx, tid in enumerate(target, 1):
        print(f"\n[{idx}/{len(target)}] ttb_id={tid}", flush=True)
        try:
            polite_sleep()
            basic = session.get(
                f"{BASE}/viewColaDetails.do?action=publicDisplaySearchBasic&ttbid={tid}",
                timeout=20,
            )
            basic.raise_for_status()
            basic_fields = parse_basic_detail(basic.text)

            polite_sleep()
            form = session.get(
                f"{BASE}/viewColaDetails.do?action=publicFormDisplay&ttbid={tid}",
                timeout=20,
            )
            form.raise_for_status()
            form_fields = parse_form(form.text)
        except Exception as e:
            print(f"  fetch failed: {e}", flush=True)
            failures += 1
            continue

        row: dict = {**basic_fields, **form_fields, "ttb_id": tid}
        row["scraped_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        # Use the form's origin if present, fall back to basic detail
        if not row.get("origin_code") and row.get("origin_code_basic"):
            row["origin_code"] = row["origin_code_basic"]

        # Images: download every panel, stitch into one composite for the
        # engine. Save individual panels in a per-COLA subdir for debugging.
        # Panels download in parallel (3 concurrent) — the bottleneck is
        # TTB's per-image render time, not our request rate.
        panels = form_fields.get("_panels") or []
        if panels:
            # Sort panels in priority order (front, back, neck, strip, other)
            panels.sort(key=lambda p: _panel_rank(p["image_type"]))
            per_cola_dir = IMG_DIR / "panels" / tid
            per_cola_dir.mkdir(parents=True, exist_ok=True)
            downloaded_paths, panel_types = download_panels_parallel(
                session, panels, per_cola_dir, max_workers=3,
            )

            # Composite — what the engine actually verifies
            composite_dest = IMG_DIR / f"{tid}.jpg"
            ok, dpi = stitch_panels(downloaded_paths, composite_dest)
            if ok:
                row["image_filename"] = composite_dest.name
                row["image_dpi"] = dpi
                row["image_type"] = " + ".join(panel_types)
                row["image_count"] = len(downloaded_paths)
            else:
                row["image_filename"] = ""

        row.pop("_panels", None)
        row.pop("origin_code_basic", None)
        row.pop("image_filename_remote", None)

        print(
            f"  brand={row.get('brand_name', '?')[:30]!r}  "
            f"class={row.get('class_type_description', row.get('class_type_code', '?'))[:25]!r}  "
            f"bottler={(row.get('name_address_applicant') or '')[:40]!r}  "
            f"dpi={row.get('image_dpi') or '-'}",
            flush=True,
        )
        pending.append(row)
        successes += 1

        # Flush every 5 rows so an interruption doesn't lose progress
        if len(pending) >= 5:
            append_csv(pending)
            pending = []

    if pending:
        append_csv(pending)

    print(f"\n[done] {successes} scraped, {failures} failed", flush=True)
    return successes


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=50, help="Number of COLAs to scrape")
    p.add_argument(
        "--from", dest="date_from", default=None,
        help="Earliest approval date to search (YYYY-MM-DD); "
             "default = 6 months ago (basic) or 5 years ago (stratified)",
    )
    p.add_argument(
        "--to", dest="date_to", default=None,
        help="Latest approval date (YYYY-MM-DD); default = today",
    )
    p.add_argument(
        "--category", choices=["spirits", "wine", "beer_malt"], default=None,
        help="Restrict search to one beverage category (uses TTB advanced "
             "search with classTypeCodeArrayByCode filter). Without this "
             "flag, scrapes any class type via basic search.",
    )
    args = p.parse_args()

    today = date.today()
    date_to = (
        date.fromisoformat(args.date_to) if args.date_to else today
    )
    # Stratified runs need more date depth because each day-window yields
    # ~20 results AT MOST (TTB caps per-query) and we may want thousands
    # per category. 5 years × 365 days × 20/day ≈ 36K possible per category.
    default_days = 1825 if args.category else 180
    date_from = (
        date.fromisoformat(args.date_from) if args.date_from
        else date_to - timedelta(days=default_days)
    )

    class_codes: list[str] | None = None
    per_window = 5
    if args.category:
        from ttb_class_codes import CATEGORIES
        class_codes = CATEGORIES[args.category]
        per_window = 20  # take all 20 the TTB cap allows
        print(f"[init] category={args.category}  ({len(class_codes)} class codes)", flush=True)

    n = scrape(args.count, date_from, date_to, class_codes=class_codes, per_window=per_window)
    return 0 if n > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
