"""Web app entry point. Run with `uvicorn app.main:create_app --factory`."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import Settings
from app.llm import LLMClient, build_llm


class HealthResponse(BaseModel):
    status: str
    llm_backend: str


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    """Build the app; settings come from the environment and the LLM from settings unless given."""
    settings = settings or Settings.from_env()
    llm = llm or build_llm(settings)

    app = FastAPI(title="KALIA")
    app.state.settings = settings
    app.state.llm = llm

    @app.get("/health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_backend=settings.llm_backend)

    return app
