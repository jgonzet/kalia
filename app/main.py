"""Web app entry point. Run with `uvicorn app.main:create_app --factory`."""

import datetime as dt

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import Settings
from app.extraction import CommitmentExtractor
from app.extraction.llm_extractor import LLMExtractor
from app.extraction.run import extract_and_store
from app.ingestion import ingest_document
from app.llm import LLMClient, build_llm
from app.models import Document, DocumentType
from app.storage import Store
from app.storage.sqlite import SqliteStore


class HealthResponse(BaseModel):
    status: str
    llm_backend: str


class DocumentIn(BaseModel):
    """A normalized document as sent to `POST /documents`."""

    id: str
    type: DocumentType
    date: dt.date
    participants: list[str]
    text: str


class IngestResponse(BaseModel):
    id: str
    stored: bool
    extracted: bool


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    store: Store | None = None,
    extractor: CommitmentExtractor | None = None,
) -> FastAPI:
    """Build the app; settings come from the environment, the LLM and the store from settings unless given.

    Without an `extractor`, the real backend gets an `LLMExtractor`; the fake one extracts nothing.
    """
    settings = settings or Settings.from_env()
    llm = llm or build_llm(settings)
    store = store or SqliteStore(settings.db_path, settings.owner_id)
    if extractor is None and settings.llm_backend == "real":
        extractor = LLMExtractor(llm, settings.owner_id)

    app = FastAPI(title="KALIA")
    app.state.settings = settings
    app.state.llm = llm
    app.state.store = store

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_backend=settings.llm_backend)

    @app.post("/documents")
    def post_document(body: DocumentIn) -> IngestResponse:
        """Ingest one document and try to extract its commitments; `extracted` says whether that worked."""
        document = Document(body.id, body.type, body.date, tuple(body.participants), body.text)
        ingest_document(document, store)
        extracted = extractor is not None and extract_and_store(document, extractor, store)
        return IngestResponse(id=body.id, stored=True, extracted=extracted)

    return app
