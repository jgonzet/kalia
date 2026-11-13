import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.extraction.saved import find_saved_extraction
from app.ingestion import ingest_document
from app.ingestion.dataset import MAX_CONSECUTIVE_FAILURES, DatasetSource, load_dataset
from app.ingestion.sample import prepare_sample
from app.llm import LLMError
from app.main import create_app
from app.models import Catalog, Commitment, Document
from app.storage.sqlite import SqliteStore

COMPANY = ROOT / "data" / "lamanija"
OWNER = "local"


class FailingExtractor:
    """Fails like an unreachable LLM, for every document or only for the ones named; counts its calls."""

    def __init__(self, only: set[str] | None = None) -> None:
        self.only = only
        self.calls = 0

    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        self.calls += 1
        if self.only is None or document.id in self.only:
            raise LLMError("stub failure")
        return []


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    return SqliteStore(str(tmp_path / "s.db"), OWNER)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(llm_backend="fake", db_path=str(tmp_path / "app.db"), sample_company="lamanija")


def sample_documents() -> int:
    return len(list(DatasetSource(COMPANY).documents()))


SAVED = json.loads(find_saved_extraction(COMPANY).read_text(encoding="utf-8"))


def saved_commitments() -> int:
    """How many commitments the shipped saved extraction holds for the documents that are loaded."""
    loaded = {d.id for d in DatasetSource(COMPANY).documents()}
    return sum(len(items) for doc_id, items in SAVED["documents"].items() if doc_id in loaded)


def test_load_dataset_without_extractor_stores_no_commitments(store: SqliteStore) -> None:
    result = load_dataset(COMPANY, store)
    assert result.documents == sample_documents() and result.failed == ()
    assert len(store.list_documents()) == sample_documents() and store.list_commitments() == []


def test_load_dataset_lists_the_documents_whose_extraction_failed(store: SqliteStore) -> None:
    result = load_dataset(COMPANY, store, FailingExtractor(only={"lamanija-0003"}))
    assert result.failed == ("lamanija-0003",)
    assert len(store.list_documents()) == sample_documents()  # the document is kept without commitments


def test_load_dataset_stops_trying_after_consecutive_failures(store: SqliteStore) -> None:
    extractor = FailingExtractor()
    result = load_dataset(COMPANY, store, extractor)
    assert extractor.calls == MAX_CONSECUTIVE_FAILURES
    assert len(result.failed) == sample_documents() and len(store.list_documents()) == sample_documents()


def test_a_success_resets_the_count_of_failures(store: SqliteStore) -> None:
    ids = [d.id for d in DatasetSource(COMPANY).documents()]
    scattered = set(ids[0:MAX_CONSECUTIVE_FAILURES - 1] + ids[MAX_CONSECUTIVE_FAILURES:2 * MAX_CONSECUTIVE_FAILURES - 1])
    extractor = FailingExtractor(only=scattered)
    result = load_dataset(COMPANY, store, extractor)
    assert extractor.calls == sample_documents() and set(result.failed) == scattered


def test_prepare_sample_loads_the_sample_with_its_commitments(settings: Settings, store: SqliteStore) -> None:
    _, info = prepare_sample(settings, store, None)
    assert len(store.list_documents()) == sample_documents()
    assert len(store.list_commitments()) == saved_commitments() > 0
    assert (info.company, info.commitments_source, info.failed_documents) == ("La Manija Games", "saved", 0)
    assert info.saved_extraction is not None and info.saved_extraction.id == SAVED["id"]


def test_prepare_sample_does_not_load_again_a_complete_store(settings: Settings, store: SqliteStore) -> None:
    prepare_sample(settings, store, None)
    store.save_document_commitments("lamanija-0001", [])
    prepare_sample(settings, store, None)
    assert not any(c.document_id == "lamanija-0001" for c in store.list_commitments())


def test_prepare_sample_completes_an_interrupted_load(settings: Settings, store: SqliteStore) -> None:
    source = DatasetSource(COMPANY)
    store.save_catalog(source.catalog())
    for document in list(source.documents())[:10]:
        ingest_document(document, store)
    prepare_sample(settings, store, None)
    assert len(store.list_documents()) == sample_documents()
    assert len(store.list_commitments()) == saved_commitments()


def test_today_is_the_samples_date_unless_the_reference_date_is_set(settings: Settings, store: SqliteStore) -> None:
    assert prepare_sample(settings, store, None)[0].today == date(2026, 10, 12)
    explicit = replace(settings, reference_date=date(2030, 1, 1))
    assert prepare_sample(explicit, store, None)[0].today == date(2030, 1, 1)


def test_prepare_sample_rejects_an_unknown_company(settings: Settings, store: SqliteStore) -> None:
    with pytest.raises(ValueError, match="no dataset"):
        prepare_sample(replace(settings, sample_company="nowhere"), store, None)


def test_prepare_sample_reports_the_failed_extractions(settings: Settings, store: SqliteStore) -> None:
    _, info = prepare_sample(replace(settings, commitments_source="extraction"), store, FailingExtractor())
    assert (info.commitments_source, info.failed_documents) == ("extraction", sample_documents())
    assert store.list_commitments() == []


def test_sample_endpoint_says_where_the_commitments_came_from(settings: Settings, tmp_path: Path) -> None:
    saved = TestClient(create_app(settings)).get("/sample").json()
    assert saved == {
        "loaded": True,
        "company": "La Manija Games",
        "commitments_source": "saved",
        "llm_model": None,
        "failed_documents": 0,
        "saved_extraction": {"id": SAVED["id"], "model": SAVED["model"], "date": SAVED["date"]},
    }
    extracted = replace(settings, db_path=str(tmp_path / "x.db"), commitments_source="extraction", llm_model="a-model")
    body = TestClient(create_app(extracted)).get("/sample").json()
    assert body["commitments_source"] == "extraction" and body["llm_model"] == "a-model" and body["saved_extraction"] is None


def test_sample_endpoint_says_so_when_there_is_no_sample(tmp_path: Path) -> None:
    plain = Settings(llm_backend="fake", db_path=str(tmp_path / "p.db"))
    assert TestClient(create_app(plain)).get("/sample").json()["loaded"] is False
