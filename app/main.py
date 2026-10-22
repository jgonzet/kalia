"""Web app entry point. Run with `uvicorn app.main:create_app --factory`."""

import datetime as dt
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, StringConstraints

from app.answering import Answerer
from app.answering.llm_answerer import LLMAnswerer
from app.answering.retrieval import RuleRetriever
from app.config import LLM_TASKS, Settings
from app.extraction import CommitmentExtractor
from app.extraction.llm_extractor import LLMExtractor
from app.extraction.run import extract_and_store
from app.ingestion import ingest_document
from app.ingestion.sample import SampleInfo, prepare_sample
from app.llm import LLMClient, build_llm
from app.models import Document, DocumentType
from app.storage import Store
from app.storage.sqlite import SqliteStore

_CHAT_PAGE = Path(__file__).resolve().parent / "static" / "chat.html"
MAX_QUESTION_CHARS = 1000


class HealthResponse(BaseModel):
    status: str
    llm_backends: dict[str, str]  # the backend of each task that calls an LLM, by task name


class SampleResponse(BaseModel):
    """What the chat page says about the loaded data; `loaded` is false when the app has no sample company."""

    loaded: bool
    company: str | None = None
    commitments_source: str | None = None
    llm_model: str | None = None  # only when the commitments were extracted by the LLM
    failed_documents: int = 0  # documents whose extraction failed when the sample was loaded


class DocumentIn(BaseModel):
    """A normalized document as sent to `POST /documents`."""

    id: str
    type: DocumentType
    date: dt.date
    participants: list[str]
    text: str


class ChatIn(BaseModel):
    """A chat question: not empty (it would bring every commitment) and not longer than a question can reasonably be."""

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS)]


class CommitmentOut(BaseModel):
    """A commitment as shown in the chat, with names instead of catalog ids."""

    id: str
    who: str
    to_whom: str
    what: str
    due: dt.date | None
    document_id: str


class ChatResponse(BaseModel):
    answer: str
    degraded: bool
    commitments: list[CommitmentOut]


class IngestResponse(BaseModel):
    id: str
    stored: bool
    extracted: bool


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    store: Store | None = None,
    extractor: CommitmentExtractor | None = None,
    answerer: Answerer | None = None,
) -> FastAPI:
    """Build the app; settings come from the environment, the LLMs and the store from settings unless given.

    Each task that calls an LLM (`LLM_TASKS`) gets the client of its own settings; a given `llm` is used for all of them.
    Without an `extractor`, a real backend (not `fake`) gets an `LLMExtractor`; the fake one extracts nothing.
    Without an `answerer`, the chat uses the rule retriever and the LLM.
    """
    settings = settings or Settings.from_env()
    llms = {task: llm or build_llm(settings.llm_for(task)) for task in LLM_TASKS}
    store = store or SqliteStore(settings.db_path, settings.owner_id)
    if extractor is None and settings.llm_for("extractor").backend != "fake":
        extractor = LLMExtractor(llms["extractor"], settings.owner_id)
    sample: SampleInfo | None = None
    if settings.sample_company:
        settings, sample = prepare_sample(settings, store, extractor)

    def current_answerer() -> Answerer:
        """The injected answerer, or one built with "today" as of this request, so it does not freeze at startup."""
        today = settings.today
        return answerer or LLMAnswerer(
            llms["answerer"], RuleRetriever(store, today), store, today, context_tokens=settings.llm_for("answerer").context_tokens
        )

    app = FastAPI(title="KALIA")
    app.state.settings = settings
    app.state.llms = llms
    app.state.store = store

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_backends={task: settings.llm_for(task).backend for task in LLM_TASKS})

    @app.get("/sample")
    def sample_info() -> SampleResponse:
        """Tell the chat page whether the data is a sample and where its commitments came from."""
        if sample is None:
            return SampleResponse(loaded=False)
        model = settings.llm_for("extractor").model if sample.commitments_source == "extraction" else None
        return SampleResponse(
            loaded=True,
            company=sample.company,
            commitments_source=sample.commitments_source,
            llm_model=model,
            failed_documents=sample.failed_documents,
        )

    @app.post("/documents")
    def post_document(body: DocumentIn) -> IngestResponse:
        """Ingest one document and try to extract its commitments; `extracted` says whether that worked."""
        document = Document(body.id, body.type, body.date, tuple(body.participants), body.text)
        ingest_document(document, store)
        extracted = extractor is not None and extract_and_store(document, extractor, store)
        return IngestResponse(id=body.id, stored=True, extracted=extracted)

    @app.get("/", response_class=HTMLResponse)
    def chat_page() -> str:
        return _CHAT_PAGE.read_text(encoding="utf-8")

    @app.post("/chat")
    def chat(body: ChatIn) -> ChatResponse:
        """Answer a question from the stored commitments; `degraded` means the LLM failed and only the commitments came back."""
        answer = current_answerer().answer(body.question)
        commitments = [
            CommitmentOut(
                id=c.id,
                who=answer.people.get(c.who_id, c.who_id),
                to_whom=answer.people.get(c.to_whom_id, c.to_whom_id),
                what=c.what,
                due=c.due,
                document_id=c.document_id,
            )
            for c in answer.commitments
        ]
        return ChatResponse(answer=answer.text, degraded=answer.degraded, commitments=commitments)

    return app
