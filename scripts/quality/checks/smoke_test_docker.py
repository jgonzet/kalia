"""Docker smoke test: start the container the way `docker compose up` does, check the sample is loaded, remove it all.

Run with `uv run scripts/quality/checks/smoke_test_docker.py`. It needs Docker, no Ollama and no API keys: the container runs with the
fake LLM, on a free port and without the local `.env`, as a person who just cloned the repo would start it.
"""

import json
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROJECT = "kalia-smoke"
STARTUP_TIMEOUT_SECONDS = 60.0
SAMPLE = json.loads((ROOT / "data" / "lamanija" / "company.json").read_text(encoding="utf-8"))
SAMPLE_REFERENCE_DATE = date.fromisoformat(SAMPLE["reference_date"])

# Merged over compose.yaml: a free port, the fake LLM, and no `.env` so the machine's own settings do not leak in.
OVERRIDE = """\
services:
  app:
    ports: !override
      - "127.0.0.1:{port}:8000"
    env_file: !reset []
    environment:
      LLM_BACKEND: fake
"""


def free_port() -> int:
    """Return a TCP port that is currently free on localhost."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def compose(override: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run `docker compose` on compose.yaml plus the override, under the smoke test's own project name."""
    return subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "-f", str(override), "-p", PROJECT, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def wait_for_health(base_url: str) -> None:
    """Poll /health until it answers; fail when the timeout expires."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=2.0).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    raise RuntimeError("the container did not answer /health in time")


def check_sample(base_url: str) -> None:
    """Check that the sample was loaded by itself, says so, and that "today" is the sample's date, not the system's."""
    sample = httpx.get(f"{base_url}/sample", timeout=5.0).json()
    assert sample == {
        "loaded": True,
        "company": SAMPLE["name"],
        "commitments_source": "expected",
        "llm_model": None,
        "failed_documents": 0,
    }, sample
    answer = httpx.post(f"{base_url}/chat", json={"question": "¿Qué compromisos tengo?"}, timeout=10.0).json()
    assert answer["commitments"], "the chat has no commitments: the sample was not loaded"
    week = httpx.post(f"{base_url}/chat", json={"question": "¿Qué compromisos vencen esta semana?"}, timeout=10.0).json()
    monday = SAMPLE_REFERENCE_DATE - timedelta(days=SAMPLE_REFERENCE_DATE.weekday())
    dues = [date.fromisoformat(c["due"]) for c in week["commitments"] if c["due"]]
    assert dues and all(monday <= d <= monday + timedelta(days=6) for d in dues), (
        f"'this week' did not use the sample's reference date: {dues}"
    )


def main() -> int:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as tmp:
        override = Path(tmp) / "override.yaml"
        override.write_text(OVERRIDE.format(port=port), encoding="utf-8")
        try:
            up = compose(override, "up", "--build", "-d")
            assert up.returncode == 0, f"docker compose up failed:\n{up.stderr}"
            wait_for_health(base_url)
            check_sample(base_url)
            config = json.loads(compose(override, "config", "--format", "json").stdout)
            assert not config.get("volumes"), "compose.yaml declares a volume: the data would outlive `down`"
        except (AssertionError, RuntimeError) as exc:
            print(f"DOCKER SMOKE TEST FAILED: {exc}")
            print(compose(override, "logs", "--tail", "40").stdout)
            return 1
        finally:
            compose(override, "down", "--rmi", "local", "--volumes")
    print("docker smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
