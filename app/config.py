"""Application settings read from environment variables (names and defaults: `.env.example`)."""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

LLMBackend = Literal["real", "fake"]

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
    llm_backend: LLMBackend = "real"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str = "ollama"
    reference_date: date | None = None
    db_path: str = "kalia.db"
    owner_id: str = "local"

    # property: use it like a field, `settings.today`, without parentheses.
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
            owner_id=os.environ.get("OWNER_ID") or defaults.owner_id,
        )
