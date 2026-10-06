"""Smoke test: start the service with the fake LLM, check it, and shut it down.

Run with `uv run scripts/smoke_test.py`. It needs no Ollama and no API keys.
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # scripts/ is sys.path[0], so make `app` importable

from app.config import Settings  # noqa: E402
from app.llm import build_llm  # noqa: E402

STARTUP_TIMEOUT_SECONDS = 20.0


def free_port() -> int:
    """Return a TCP port that is currently free on localhost."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(base_url: str, process: subprocess.Popen[bytes]) -> httpx.Response:
    """Poll /health until it answers; fail if the process dies or the timeout expires."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"service exited early with code {process.returncode}")
        try:
            return httpx.get(f"{base_url}/health", timeout=2.0)
        except httpx.TransportError:
            time.sleep(0.2)
    raise RuntimeError("service did not answer /health in time")


def check_fake_llm() -> None:
    """Check the LLM interface answers when the fake backend is selected."""
    llm = build_llm(Settings(llm_backend="fake"))
    answer = llm.complete("ping")
    assert answer, "fake LLM returned an empty answer"


def main() -> int:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "LLM_BACKEND": "fake"}
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--port", str(port)],
        env=env,
        cwd=ROOT,
    )
    try:
        response = wait_for_health(base_url, process)
        assert response.status_code == 200, f"/health returned {response.status_code}"
        assert response.json() == {"status": "ok", "llm_backend": "fake"}, response.json()
        check_fake_llm()
    except (AssertionError, RuntimeError) as exc:
        print(f"SMOKE TEST FAILED: {exc}")
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
