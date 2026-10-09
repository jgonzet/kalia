"""Web app entry point. Run with `uvicorn app.main:create_app --factory`."""

import datetime as dt

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import Settings
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


def create_app(
    settings: Settings | None = None, llm: LLMClient | None = None, store: Store | None = None
) -> FastAPI:
    """Build the app; settings come from the environment, the LLM and the store from settings unless given."""
    settings = settings or Settings.from_env()
    llm = llm or build_llm(settings)
    store = store or SqliteStore(settings.db_path, settings.owner_id)

    app = FastAPI(title="KALIA")
    app.state.settings = settings
    app.state.llm = llm
    app.state.store = store

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_backend=settings.llm_backend)

    @app.post("/documents")
    def post_document(body: DocumentIn) -> IngestResponse:
        """Ingest one document; sending the same id again replaces it."""
        ingest_document(
            Document(body.id, body.type, body.date, tuple(body.participants), body.text), store
        )
        return IngestResponse(id=body.id, stored=True)

    return app
