"""Smoke test: start the service with the fake LLM, check it, and shut it down.

Run with `uv run scripts/smoke_test.py`. It needs no Ollama and no API keys.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # scripts/ is sys.path[0], so make `app` importable

from app.config import Settings  # noqa: E402
from app.ingestion.dataset import DatasetSource  # noqa: E402
from app.llm import build_llm  # noqa: E402
from app.llm import LLMError  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Catalog, Commitment, Document  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402

STARTUP_TIMEOUT_SECONDS = 20.0
DATASET = ROOT / "data" / "lamanija"
OWNER_ID = "smoke"


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


def run_loader(db_path: str) -> None:
    """Run the dataset loader script against the temporary database."""
    env = {**os.environ, "DB_PATH": db_path, "OWNER_ID": OWNER_ID}
    subprocess.run([sys.executable, "scripts/load_dataset.py", "lamanija"], env=env, cwd=ROOT, check=True)


def check_ingestion(base_url: str, db_path: str) -> None:
    """Check the initial load, its idempotence and the later ingestion of the held-out document."""
    source = DatasetSource(DATASET)
    expected_initial = len(list(source.documents()))
    held_out = source.company["held_out"]
    store = SqliteStore(db_path, OWNER_ID)

    run_loader(db_path)
    assert len(store.list_documents()) == expected_initial, "initial load stored the wrong number of documents"
    catalog = store.load_catalog()
    assert catalog is not None and catalog.user, "catalog was not stored"
    assert not any(store.get_document(doc_id) for doc_id in held_out), "held-out document was loaded"

    run_loader(db_path)
    assert len(store.list_documents()) == expected_initial, "reloading duplicated documents"

    for _ in range(2):  # the second post checks idempotence of the endpoint
        for doc_id in held_out:
            doc = source.document(doc_id)
            body = {
                "id": doc.id,
                "type": doc.type,
                "date": doc.date.isoformat(),
                "participants": list(doc.participants),
                "text": doc.text,
            }
            response = httpx.post(f"{base_url}/documents", json=body, timeout=5.0)
            assert response.status_code == 200, f"POST /documents returned {response.status_code}"
        assert len(store.list_documents()) == expected_initial + len(held_out), "held-out ingestion failed"


def check_commitments(db_path: str) -> None:
    """Check that saving a document's commitments is idempotent and replaces the previous ones."""
    store = SqliteStore(db_path, OWNER_ID)

    def commitment(number: int, document_id: str, due: date | None = None) -> Commitment:
        return Commitment(f"{document_id}-c{number}", OWNER_ID, "A", "B", "do it", due, None, document_id, date(2026, 1, 1))

    first = [commitment(1, "doc-a", date(2026, 2, 2)), commitment(2, "doc-a")]
    store.save_document_commitments("doc-a", first)
    store.save_document_commitments("doc-b", [commitment(1, "doc-b")])
    store.save_document_commitments("doc-a", first)
    stored = store.list_commitments()
    assert len(stored) == 3, "re-saving a document duplicated its commitments"
    assert stored[0].due == date(2026, 2, 2) and stored[1].due is None, "due date did not round-trip"
    store.save_document_commitments("doc-a", [])
    assert [c.id for c in store.list_commitments()] == ["doc-b-c1"], "re-saving did not replace the commitments"


class StubExtractor:
    """Returns one commitment per document, or fails like an unreachable LLM."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        if self.fail:
            raise LLMError("stub failure")
        return [Commitment(f"{document.id}-c1", OWNER_ID, "A", "B", "do it", None, None, document.id, document.date)]


def check_extraction_on_ingest(db_path: str) -> None:
    """Check that POST /documents extracts and stores, and that an LLM failure keeps the document."""
    store = SqliteStore(db_path, OWNER_ID)
    body = {"id": "doc-x", "type": "email", "date": "2026-01-01", "participants": ["A"], "text": "hi"}

    ok = TestClient(create_app(store=store, extractor=StubExtractor())).post("/documents", json=body)
    assert ok.json()["extracted"] is True, "extraction did not run on ingestion"
    assert [c.id for c in store.list_commitments() if c.document_id == "doc-x"] == ["doc-x-c1"]

    failed = TestClient(create_app(store=store, extractor=StubExtractor(fail=True))).post("/documents", json=body)
    assert failed.status_code == 200 and failed.json() == {"id": "doc-x", "stored": True, "extracted": False}
    assert store.get_document("doc-x") is not None, "document lost when extraction failed"
    assert any(c.document_id == "doc-x" for c in store.list_commitments()), "failed extraction wiped commitments"


def main() -> int:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    tmp_dir = tempfile.TemporaryDirectory()
    db_path = str(Path(tmp_dir.name) / "smoke.db")
    env = {**os.environ, "LLM_BACKEND": "fake", "DB_PATH": db_path, "OWNER_ID": OWNER_ID}
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
        check_ingestion(base_url, db_path)
        check_commitments(db_path)
        check_extraction_on_ingest(db_path)
    except (AssertionError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"SMOKE TEST FAILED: {exc}")
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        tmp_dir.cleanup()
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
