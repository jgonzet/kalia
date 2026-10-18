from datetime import date
from pathlib import Path

import pytest

import app.config as config
from app.config import Settings

ENV_VARS = ("LLM_BACKEND", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "REFERENCE_DATE", "DB_PATH")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ENV_FILES", ())
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_when_nothing_is_set() -> None:
    assert Settings.from_env() == Settings()


def test_empty_variable_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("REFERENCE_DATE", "")
    settings = Settings.from_env()
    assert settings.llm_model == Settings().llm_model
    assert settings.reference_date is None


def test_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("LLM_MODEL", "llama3.1")
    monkeypatch.setenv("REFERENCE_DATE", "2026-03-12")
    settings = Settings.from_env()
    assert settings.llm_backend == "fake"
    assert settings.llm_model == "llama3.1"
    assert settings.reference_date == date(2026, 3, 12)
    assert settings.today == date(2026, 3, 12)


def test_invalid_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "openai")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_invalid_reference_date_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REFERENCE_DATE", "12/03/2026")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_today_is_the_system_date_without_a_reference_date(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDate(date):
        @classmethod
        def today(cls) -> "FakeDate":
            return cls(2030, 5, 6)

    monkeypatch.setattr(config, "date", FakeDate)
    assert Settings().today == date(2030, 5, 6)


def test_env_files_are_loaded_and_the_environment_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nLLM_MODEL=from-file\nREFERENCE_DATE=2026-10-12\n")
    monkeypatch.setattr(config, "ENV_FILES", (env_file, tmp_path / "missing"))
    monkeypatch.setenv("LLM_MODEL", "from-environment")
    settings = Settings.from_env()
    assert settings.llm_model == "from-environment"
    assert settings.reference_date == date(2026, 10, 12)
