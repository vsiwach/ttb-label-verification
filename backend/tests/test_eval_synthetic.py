"""Integration gate: drive the synthetic eval through the FastAPI backend
in mock mode and assert 100%.

This is the deterministic seam between the rules engine and the API surface.
It boots a real uvicorn process, runs test/eval/run_eval.py --synthetic, and
verifies every case (group + per-field + warning) is correct.

Skipped if `requests` isn't installed. Requires no API keys.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
RUN_EVAL = REPO_DIR / "test" / "eval" / "run_eval.py"
SYNTHETIC_DIR = REPO_DIR / "test" / "synthetic"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 15.0) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def live_backend():
    """Boot the FastAPI backend in mock mode and yield its base URL."""
    pytest.importorskip("requests")
    if not RUN_EVAL.exists():
        pytest.skip(f"missing {RUN_EVAL}")

    port = _free_port()
    env = {
        **os.environ,
        "INFERENCE_MODE": "mock",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        "GOOGLE_API_KEY": "",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(BACKEND_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        if not _wait_for_health(f"{base}/health"):
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=5)
            pytest.fail(
                "backend did not become ready.\n"
                f"stdout: {stdout.decode()[-2000:]}\n"
                f"stderr: {stderr.decode()[-2000:]}"
            )
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_synthetic_eval_passes_100_percent(live_backend, tmp_path):
    """The synthetic eval is the integration gate. Every case (group + per-field
    + warning) must be correct against the mock backend."""
    out_dir = tmp_path / "eval"
    result = subprocess.run(
        [sys.executable, str(RUN_EVAL),
         "--api", f"{live_backend}/api",
         "--synthetic", str(SYNTHETIC_DIR),
         "--out", str(out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"run_eval failed:\n{result.stderr}\n{result.stdout}"

    report = json.loads((out_dir / "report.json").read_text())
    assert report["mode"] == "synthetic"
    n = report["n"]
    assert n > 0, "expected at least one synthetic case"
    assert report["cases_passed"] == n, (
        f"expected {n}/{n} cases passing; got {report['cases_passed']}.\n"
        f"Failing: {[c for c in report['cases'] if not c.get('passed')]}"
    )
    assert report["group_accuracy"] == 1.0, "group bucket regression"
    assert report["field_status_accuracy"] == 1.0, "per-field status regression"
    assert report["warning_flag_accuracy"] == 1.0, "warning-flag regression"
