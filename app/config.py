"""Application settings read from environment variables (names and defaults: `.env.example`)."""

import os
from dataclasses import dataclass
from datetime import date
from typing import Literal

LLMBackend = Literal["real", "fake"]


@dataclass(frozen=True)
class Settings:
    llm_backend: LLMBackend = "real"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str = "ollama"
    reference_date: date | None = None
    db_path: str = "kalia.db"

    @property
    def today(self) -> date:
        """The date the app treats as "today": the reference date if set, else the system date."""
        return self.reference_date or date.today()

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the environment; empty or missing variables fall back to defaults."""
        defaults = cls()
        backend = os.environ.get("LLM_BACKEND") or defaults.llm_backend
        if backend not in ("real", "fake"):
            raise ValueError(f"LLM_BACKEND must be 'real' or 'fake', got {backend!r}")
        reference_date = os.environ.get("REFERENCE_DATE")
        return cls(
            llm_backend=backend,
            llm_base_url=os.environ.get("LLM_BASE_URL") or defaults.llm_base_url,
            llm_model=os.environ.get("LLM_MODEL") or defaults.llm_model,
            llm_api_key=os.environ.get("LLM_API_KEY") or defaults.llm_api_key,
            reference_date=date.fromisoformat(reference_date) if reference_date else None,
            db_path=os.environ.get("DB_PATH") or defaults.db_path,
        )
