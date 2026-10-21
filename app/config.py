"""Application settings read from environment variables (names and defaults: `.env.example`)."""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

LLMBackend = Literal["ollama", "openai_compatible", "fake"]
LLM_BACKENDS = ("ollama", "openai_compatible", "fake")

# Where the commitments of the sample company come from: its `expected` files, or the configured LLM.
CommitmentsSource = Literal["expected", "extraction"]
COMMITMENTS_SOURCES = ("expected", "extraction")

# Ollama's native API is at the server root; any OpenAI-compatible endpoint is at `/v1`.
DEFAULT_BASE_URLS = {"ollama": "http://localhost:11434", "openai_compatible": "http://localhost:11434/v1"}
# The context window the app asks Ollama for. Measured on 2026-10-17 with `qwen2.5:14b` on a 12 GB GPU: 10240 tokens
# run entirely on the GPU (11.4 GB), 12288 already send 5% of the model to the CPU.
DEFAULT_OLLAMA_CONTEXT_TOKENS = 10240

# `.env` holds plain settings and `.env.secrets` the API keys; both sit in the project root.
ROOT = Path(__file__).resolve().parent.parent
ENV_FILES = (ROOT / ".env", ROOT / ".env.secrets")


def load_env_files() -> None:
    """Put the `KEY=value` lines of the env files into `os.environ`; variables already set win, missing files are skipped."""
    for path in ENV_FILES:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


# dataclass: Python writes the boilerplate that builds the class from its fields.
# frozen=True: values can't be changed after a Settings object is created.
@dataclass(frozen=True)
class Settings:
    llm_backend: LLMBackend = "ollama"
    llm_base_url: str | None = None
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str = "ollama"
    llm_context_tokens: int | None = None
    reference_date: date | None = None
    db_path: str = "kalia.db"
    owner_id: str = "local"
    sample_company: str | None = None
    commitments_source: CommitmentsSource = "expected"

    # property: use it like a field, `settings.today`, without parentheses.
    @property
    def base_url(self) -> str:
        """The LLM endpoint: `LLM_BASE_URL` if set, else the default of the backend (the fake one has none)."""
        return self.llm_base_url or DEFAULT_BASE_URLS.get(self.llm_backend, "")

    @property
    def context_tokens(self) -> int | None:
        """The context window in tokens: `LLM_CONTEXT_TOKENS` if set, else the default for Ollama, else unknown (None).

        With Ollama it is also what the client asks the server to run with, so it is never an assumption.
        """
        if self.llm_context_tokens:
            return self.llm_context_tokens
        return DEFAULT_OLLAMA_CONTEXT_TOKENS if self.llm_backend == "ollama" else None

    @property
    def today(self) -> date:
        """The date the app treats as "today": the reference date if set, else the system date."""
        return self.reference_date or date.today()

    # classmethod: called on the class itself, `Settings.from_env()`, to create a new Settings.
    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the environment (after loading the env files); empty or missing variables fall back to defaults."""
        load_env_files()
        defaults = cls()
        backend = os.environ.get("LLM_BACKEND") or defaults.llm_backend
        if backend not in LLM_BACKENDS:
            raise ValueError(f"LLM_BACKEND must be one of {', '.join(LLM_BACKENDS)}, got {backend!r}")
        context_tokens = os.environ.get("LLM_CONTEXT_TOKENS")
        reference_date = os.environ.get("REFERENCE_DATE")
        source = os.environ.get("COMMITMENTS_SOURCE") or defaults.commitments_source
        if source not in COMMITMENTS_SOURCES:
            raise ValueError(f"COMMITMENTS_SOURCE must be one of {', '.join(COMMITMENTS_SOURCES)}, got {source!r}")
        return cls(
            llm_backend=backend,
            llm_base_url=os.environ.get("LLM_BASE_URL") or defaults.llm_base_url,
            llm_model=os.environ.get("LLM_MODEL") or defaults.llm_model,
            llm_api_key=os.environ.get("LLM_API_KEY") or defaults.llm_api_key,
            llm_context_tokens=int(context_tokens) if context_tokens else None,
            reference_date=date.fromisoformat(reference_date) if reference_date else None,
            db_path=os.environ.get("DB_PATH") or defaults.db_path,
            owner_id=os.environ.get("OWNER_ID") or defaults.owner_id,
            sample_company=os.environ.get("SAMPLE_COMPANY") or defaults.sample_company,
            commitments_source=source,
        )
