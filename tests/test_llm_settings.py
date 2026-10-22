"""Tests of the LLM settings per task (`Settings.from_env`, `Settings.llm_for`) and of the names of the LLM variables."""

import os
import re

import pytest

import app.config as config
from app.config import DEFAULT_LLM_MODEL, DEFAULT_LLM_TIMEOUT_SECONDS, DEFAULT_OLLAMA_CONTEXT_TOKENS, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ENV_FILES", ())
    for name in list(os.environ):
        if re.fullmatch(r"(?:[A-Z][A-Z0-9]*_)?LLM_[A-Z0-9_]+", name):
            monkeypatch.delenv(name)


def set_env(monkeypatch: pytest.MonkeyPatch, **variables: str) -> None:
    for name, value in variables.items():
        monkeypatch.setenv(name, value)


def test_without_variables_every_task_uses_the_defaults_of_ollama() -> None:
    settings = Settings.from_env()
    llm = settings.llm_for("answerer")
    assert llm == settings.llm_for("extractor") == settings.default_llm()
    assert (llm.backend, llm.model, llm.base_url) == ("ollama", DEFAULT_LLM_MODEL, "http://localhost:11434")
    assert (llm.context_tokens, llm.timeout_seconds) == (DEFAULT_OLLAMA_CONTEXT_TOKENS, DEFAULT_LLM_TIMEOUT_SECONDS)
    with pytest.raises(ValueError, match="unknown LLM task"):
        settings.llm_for("summarizer")


def test_a_task_with_any_variable_of_its_own_inherits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, LLM_BACKEND="openai_compatible", LLM_MODEL="m", LLM_API_KEY="key-a", LLM_BASE_URL="http://host/v1", LLM_TIMEOUT_SECONDS="7.5")
    set_env(monkeypatch, EXTRACTOR_LLM_BACKEND="ollama", EXTRACTOR_LLM_MODEL="small")
    settings = Settings.from_env()
    extractor = settings.llm_for("extractor")
    assert (extractor.backend, extractor.model, extractor.base_url) == ("ollama", "small", "http://localhost:11434")
    assert extractor.api_key != "key-a"  # the key of the default LLM never reaches another provider
    assert extractor.timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS  # not the default LLM's 7.5
    assert settings.llm_for("answerer") == settings.default_llm() and settings.default_llm().timeout_seconds == 7.5


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"LLM_BACKEND": "openai_compatible", "LLM_API_KEY": "k"}, "LLM_MODEL is required"),
        ({"LLM_BACKEND": "anthropic", "LLM_MODEL": "m"}, "LLM_API_KEY is required"),
        ({"LLM_BACKEND": "real"}, "LLM_BACKEND must be one of"),
        ({"EXTRACTOR_LLM_BACKEND": "anthropic", "EXTRACTOR_LLM_API_KEY": "k"}, "EXTRACTOR_LLM_MODEL is missing"),
        ({"EXTRACTOR_LLM_BACKEND": "openai_compatible", "EXTRACTOR_LLM_MODEL": "m"}, "EXTRACTOR_LLM_API_KEY is missing"),
        ({"ANSWERER_LLM_TIMEOUT_SECONDS": "30"}, "ANSWERER_LLM_BACKEND is missing"),
    ],
)
def test_an_incomplete_llm_names_the_variable_to_set(monkeypatch: pytest.MonkeyPatch, env: dict[str, str], message: str) -> None:
    set_env(monkeypatch, **env)
    with pytest.raises(ValueError, match=message):
        Settings.from_env()


@pytest.mark.parametrize(
    "env",
    [{"LLM_CONTEXT_TOKENS": "8192.5"}, {"LLM_TIMEOUT_SECONDS": "abc"}, {"LLM_TIMEOUT_SECONDS": "0"}, {"ANSWERER_LLM_BACKEND": "fake", "ANSWERER_LLM_TIMEOUT_SECONDS": "-5"}],
)
def test_an_invalid_number_raises(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    set_env(monkeypatch, **env)
    with pytest.raises(ValueError, match="_LLM_|LLM_"):
        Settings.from_env()


@pytest.mark.parametrize("name", ["EXTRATOR_LLM_BACKEND", "EXTRACTOR_LLM_MODLE", "LLM_MODLE"])
def test_a_misspelled_llm_variable_raises(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    set_env(monkeypatch, **{name: "x"})
    with pytest.raises(ValueError, match=name):
        Settings.from_env()


def test_the_anthropic_settings_carry_no_address_and_no_key_in_the_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Docker image always sets LLM_BASE_URL (the host's Ollama): Claude's key must not be sent there.
    set_env(monkeypatch, LLM_BACKEND="anthropic", LLM_MODEL="m", LLM_API_KEY="secret-key", LLM_BASE_URL="http://host.docker.internal:11434")
    settings = Settings.from_env()
    assert settings.default_llm().base_url == ""
    assert "secret-key" not in repr(settings) + repr(settings.default_llm())


def test_other_variables_are_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    set_env(monkeypatch, SOME_OTHER_VAR="x", MY_LLM="x", ANTHROPIC_API_KEY="x")
    Settings.from_env()
