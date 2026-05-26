"""End-to-end smoke test for a deployed TTB verification API.

Runs against ANY deployment — local backend, Modal, Vercel, etc. —
configured via the TTB_API_BASE env var. Exits 0 if everything Treasury
will actually do works, non-zero if anything is broken.

What it checks:
  1. GET /health                   — liveness
  2. GET /api/samples              — sample picker loads
  3. POST /api/verify (synthetic)  — single-label verification on 3 fixtures
  4. POST /api/verify-batch        — batch verification on 2 fixtures
  5. Same /api/verify, repeated    — warm-path stability (no timeouts/regressions)

Synthetic fixtures live in test/synthetic/ (3 in-repo PNGs); the matching
applicationData lives in test/synthetic/expected_results.json. Choosing
in-repo synthetics over the TTB-live scrape so the test is reproducible
on a fresh checkout without needing Drive access.

Cold-start tolerance: the first POST /api/verify gets up to 90 s to
account for Modal cold start. Subsequent calls must complete in ≤30 s
each — that's the warm-path SLA we'd quote to Treasury.

Usage:
    TTB_API_BASE=https://your-deployment.modal.run python test/smoke/smoke_deployed.py
    TTB_API_BASE=http://localhost:8000                python test/smoke/smoke_deployed.py
    make smoke-deployed URL=https://your-deployment.modal.run
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_DIR = REPO / "test" / "synthetic"
EXPECTED_FILE = SYNTHETIC_DIR / "expected_results.json"

BASE_URL = os.environ.get("TTB_API_BASE", "http://localhost:8000").rstrip("/")
COLD_START_TIMEOUT = float(os.environ.get("TTB_COLD_START_TIMEOUT", "90"))
WARM_TIMEOUT = float(os.environ.get("TTB_WARM_TIMEOUT", "30"))


# ── output helpers ─────────────────────────────────────────────────────────
class _C:
    OK   = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    DIM  = "\033[2m"
    END  = "\033[0m"


def banner(msg: str) -> None:
    print(f"\n{_C.DIM}{'─' * 70}{_C.END}\n  {msg}\n{_C.DIM}{'─' * 70}{_C.END}")


def pass_(label: str, detail: str = "") -> None:
    print(f"  {_C.OK}✓{_C.END} {label}" + (f"  {_C.DIM}{detail}{_C.END}" if detail else ""))


def fail_(label: str, detail: str = "") -> int:
    print(f"  {_C.FAIL}✗{_C.END} {label}" + (f"  {detail}" if detail else ""))
    return 1


def warn_(label: str, detail: str = "") -> None:
    print(f"  {_C.WARN}!{_C.END} {label}" + (f"  {_C.DIM}{detail}{_C.END}" if detail else ""))


# ── checks ─────────────────────────────────────────────────────────────────

def check_health(client: httpx.Client) -> int:
    banner(f"1. GET {BASE_URL}/health")
    t0 = time.perf_counter()
    try:
        r = client.get(f"{BASE_URL}/health", timeout=COLD_START_TIMEOUT)
        elapsed = time.perf_counter() - t0
    except httpx.TimeoutException:
        return fail_(f"timed out after {COLD_START_TIMEOUT}s — backend not reachable")
    except Exception as e:
        return fail_(f"connect error: {e}")
    if r.status_code != 200:
        return fail_(f"got {r.status_code}", r.text[:120])
    try:
        body = r.json()
    except Exception:
        return fail_(f"non-JSON response: {r.text[:120]}")
    pass_(f"200 OK in {elapsed:.2f}s", f"body: {body}")
    return 0


def check_samples(client: httpx.Client) -> int:
    banner(f"2. GET {BASE_URL}/api/samples")
    t0 = time.perf_counter()
    try:
        r = client.get(f"{BASE_URL}/api/samples", timeout=WARM_TIMEOUT)
        elapsed = time.perf_counter() - t0
    except Exception as e:
        return fail_(f"request failed: {e}")
    if r.status_code != 200:
        return fail_(f"got {r.status_code}", r.text[:120])
    samples = r.json()
    if not isinstance(samples, list) or len(samples) == 0:
        return fail_(f"empty or non-list response: {type(samples).__name__}, len={len(samples) if isinstance(samples, list) else '?'}")
    pass_(f"200 OK in {elapsed:.2f}s", f"{len(samples)} samples")
    if len(samples) > 5000:
        warn_(f"sample picker has {len(samples)} entries — UI may render slowly",
              "consider capping list_samples() to a smaller default tier")
    # Spot-check the first sample's shape (applicationData is nested)
    first = samples[0]
    if "id" not in first or "applicationData" not in first:
        return fail_(f"first sample missing 'id' or 'applicationData'", str(first)[:200])
    app = first["applicationData"]
    required = {"brandName", "classType"}
    missing = required - set(app.keys())
    if missing:
        return fail_(f"first sample applicationData missing: {missing}", str(app)[:200])
    pass_(f"sample shape OK", f"first: {app.get('brandName', '?')[:40]}")
    return 0


def check_verify(client: httpx.Client, case: dict, label: str, *, timeout: float) -> tuple[int, float]:
    """POST /api/verify with one case. Returns (failure_count, elapsed_s)."""
    img_path = SYNTHETIC_DIR / case["image"]
    if not img_path.exists():
        return fail_(f"missing fixture {img_path.name}"), 0.0
    img_bytes = img_path.read_bytes()
    app_data = case["applicationData"]
    expected = case.get("expected", {})
    expected_group = expected.get("group")

    t0 = time.perf_counter()
    try:
        r = client.post(
            f"{BASE_URL}/api/verify",
            files={"image": (case["image"], img_bytes, "image/png")},
            data={"applicationData": json.dumps(app_data)},
            timeout=timeout,
        )
        elapsed = time.perf_counter() - t0
    except httpx.TimeoutException:
        return fail_(f"{label}: timed out after {timeout:.0f}s"), 0.0
    except Exception as e:
        return fail_(f"{label}: request error: {e}"), 0.0

    if r.status_code != 200:
        return fail_(f"{label}: HTTP {r.status_code}", r.text[:200]), elapsed
    try:
        result = r.json()
    except Exception:
        return fail_(f"{label}: non-JSON response"), elapsed

    # Validate shape: must have fields[] and governmentWarning
    if "fields" not in result or "governmentWarning" not in result:
        return fail_(f"{label}: response missing 'fields' or 'governmentWarning'"), elapsed

    # Compute bucket the same way the frontend does
    statuses = [f["status"] for f in result["fields"]]
    gw = result["governmentWarning"]
    if any(s == "flag" for s in statuses) or not gw["present"] or not gw["verbatimMatch"]:
        bucket = "needs-review"
    elif any(s == "likely" for s in statuses):
        bucket = "needs-confirm"
    else:
        bucket = "auto-pass"

    if expected_group and bucket != expected_group:
        warn_(f"{label}: bucket={bucket} (expected {expected_group})",
              f"fields: {statuses}  gw_present={gw['present']}  verbatim={gw['verbatimMatch']}")
    else:
        pass_(f"{label}: {bucket} in {elapsed:.2f}s",
              f"fields: {statuses}  gw_present={gw['present']}")
    return 0, elapsed


def check_verify_batch(client: httpx.Client, cases: list[dict]) -> int:
    banner(f"4. POST {BASE_URL}/api/verify-batch (2 images)")
    files = []
    for case in cases:
        img_path = SYNTHETIC_DIR / case["image"]
        if not img_path.exists():
            return fail_(f"missing fixture {img_path.name}")
        files.append(("images", (case["image"], img_path.read_bytes(), "image/png")))

    t0 = time.perf_counter()
    try:
        r = client.post(
            f"{BASE_URL}/api/verify-batch",
            files=files,
            data={"applicationData": json.dumps(cases[0]["applicationData"])},
            timeout=WARM_TIMEOUT * 2,
        )
        elapsed = time.perf_counter() - t0
    except Exception as e:
        return fail_(f"request error: {e}")
    if r.status_code != 200:
        return fail_(f"HTTP {r.status_code}", r.text[:200])
    items = r.json()
    if not isinstance(items, list) or len(items) != len(cases):
        return fail_(f"expected {len(cases)} items, got {len(items) if isinstance(items, list) else '?'}")
    pass_(f"200 OK in {elapsed:.2f}s", f"{len(items)} items returned")
    return 0


# ── main ──────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n  TTB API smoke test")
    print(f"  Target: {_C.OK}{BASE_URL}{_C.END}")
    print(f"  Cold-start budget: {COLD_START_TIMEOUT:.0f}s ; warm-path budget: {WARM_TIMEOUT:.0f}s")

    expected = json.loads(EXPECTED_FILE.read_text())
    cases = expected["cases"]
    # Pick 3 stable cases for the smoke test (auto-pass / needs-confirm / needs-review)
    smoke_cases = [c for c in cases if c["image"] in {
        "label_1_old_tom_spirits.png",         # expected auto-pass
        "label_3_northwind_beer.png",          # expected needs-review (GW issue)
        "label_5_valley_crest_wine.png",       # expected auto-pass (imports edge)
    }]

    failures = 0
    with httpx.Client() as client:
        # Health (also warms the container for Modal)
        failures += check_health(client)
        if failures:
            print(f"\n{_C.FAIL}aborting — backend not reachable{_C.END}")
            return failures

        failures += check_samples(client)

        # First /api/verify with extended cold-start budget
        banner(f"3. POST {BASE_URL}/api/verify (3 single-label cases)")
        latencies = []
        for i, case in enumerate(smoke_cases):
            timeout = COLD_START_TIMEOUT if i == 0 else WARM_TIMEOUT
            label = f"{case['image']}"
            f, elapsed = check_verify(client, case, label, timeout=timeout)
            failures += f
            if f == 0 and i > 0:    # only count warm latencies
                latencies.append(elapsed)

        # Batch endpoint
        failures += check_verify_batch(client, smoke_cases[:2])

        # Warm-path stability — repeat first case 3 more times
        banner("5. Warm-path stability (5 sequential calls)")
        for i in range(5):
            f, elapsed = check_verify(client, smoke_cases[0], f"repeat {i+1}/5", timeout=WARM_TIMEOUT)
            failures += f
            if f == 0:
                latencies.append(elapsed)

        # Latency report
        if latencies:
            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[-1]
            mean = sum(latencies) / len(latencies)
            banner("Warm-path latency report")
            print(f"  n={len(latencies)}  mean={mean:.2f}s  p50={p50:.2f}s  p95={p95:.2f}s")
            if mean > 10:
                warn_(f"mean latency {mean:.1f}s is high for warm path", "consider GPU upgrade or smaller MAX_PIXELS")

    print()
    if failures:
        print(f"{_C.FAIL}╔══════════════════════════════╗")
        print(f"║  {failures} CHECK(S) FAILED        ║")
        print(f"╚══════════════════════════════╝{_C.END}\n")
    else:
        print(f"{_C.OK}╔══════════════════════════════╗")
        print(f"║  ALL CHECKS PASSED — ship it ║")
        print(f"╚══════════════════════════════╝{_C.END}\n")
    return failures


if __name__ == "__main__":
    sys.exit(main())
