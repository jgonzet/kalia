"""Application settings read from environment variables (names and defaults: `.env.example`)."""

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal, TypedDict

LLMBackend = Literal["ollama", "openai_compatible", "anthropic", "fake"]
LLM_BACKENDS = ("ollama", "openai_compatible", "anthropic", "fake")

# The tasks of the app that call an LLM. Each one can have its own LLM through `<TASK>_LLM_*` variables (`EXTRACTOR_LLM_MODEL`,
# ...); a task without them uses the default `LLM_*`. A new task that calls an LLM is added here.
LLM_TASKS = ("extractor", "answerer")
# The variables that describe an LLM, after the `LLM_` or `<TASK>_LLM_` prefix.
LLM_VARIABLES = ("BACKEND", "MODEL", "BASE_URL", "API_KEY", "CONTEXT_TOKENS", "TIMEOUT_SECONDS")

# Backends that cannot guess a model or that need a key: the app refuses to start without them instead of trying a default.
BACKENDS_REQUIRING_MODEL = ("openai_compatible", "anthropic")
BACKENDS_REQUIRING_KEY = ("openai_compatible", "anthropic")
# The model of the Ollama backend when none is set.
DEFAULT_LLM_MODEL = "qwen2.5:14b"
# Placeholder key for the backends that do not need one.
DEFAULT_LLM_API_KEY = "ollama"
# How long one attempt at an LLM call waits for the answer. Measured on 2026-10-21 with `qwen2.5:14b` on a GPU: the longest
# answer took 72 seconds (README, "Known limitations"); a slower machine, or one without a GPU, needs more.
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0

# Where the commitments of the sample company come from: its saved extraction, or the configured LLM.
CommitmentsSource = Literal["saved", "extraction"]
COMMITMENTS_SOURCES = ("saved", "extraction")

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


@dataclass(frozen=True)
class LLMSettings:
    """Everything needed to build one LLM client, with the defaults of its backend already applied."""

    backend: LLMBackend
    model: str
    base_url: str
    api_key: str = field(repr=False)
    context_tokens: int | None
    timeout_seconds: float

    @classmethod
    def resolve(
        cls,
        backend: LLMBackend,
        model: str,
        base_url: str | None,
        api_key: str,
        context_tokens: int | None,
        timeout_seconds: float | None,
    ) -> "LLMSettings":
        """Build the settings of an LLM, filling the endpoint, the context window and the timeout when they are unset.

        The context window is also what the Ollama client asks the server to run with, so it is never an assumption.
        The Claude client takes no address (see `AnthropicLLM`), so the settings of "anthropic" carry none.
        """
        return cls(
            backend=backend,
            model=model,
            base_url="" if backend == "anthropic" else base_url or DEFAULT_BASE_URLS.get(backend, ""),
            api_key=api_key,
            context_tokens=context_tokens or (DEFAULT_OLLAMA_CONTEXT_TOKENS if backend == "ollama" else None),
            timeout_seconds=timeout_seconds or DEFAULT_LLM_TIMEOUT_SECONDS,
        )


class _LLMValues(TypedDict):
    """The values read from the variables of one LLM, validated and still without the defaults of the backend."""

    backend: LLMBackend
    model: str
    base_url: str | None
    api_key: str
    context_tokens: int | None
    timeout_seconds: float | None


def _read_llm(prefix: str, task: str | None) -> _LLMValues | None:
    """Read and validate the LLM variables that start with `prefix`; None if none of them is set.

    The default LLM (`task` is None) falls back to Ollama for what is missing. A task that sets any of its variables
    takes everything from them and inherits nothing from the default, so what it lacks raises an error saying what to set.
    """
    raw = {name: os.environ.get(prefix + name) or None for name in LLM_VARIABLES}
    if not any(raw.values()):
        return None

    def missing(name: str) -> ValueError:
        if task is None:
            return ValueError(f"{prefix}{name} is required with {prefix}BACKEND={backend}")
        return ValueError(f"{prefix}{name} is missing: set it, or remove the {prefix}* variables to use the default LLM_*")

    backend = raw["BACKEND"] or ("ollama" if task is None else "")
    if not backend:
        raise missing("BACKEND")
    if backend not in LLM_BACKENDS:
        raise ValueError(f"{prefix}BACKEND must be one of {', '.join(LLM_BACKENDS)}, got {backend!r}")
    if backend in BACKENDS_REQUIRING_MODEL and not raw["MODEL"]:
        raise missing("MODEL")
    if backend in BACKENDS_REQUIRING_KEY and not raw["API_KEY"]:
        raise missing("API_KEY")
    try:
        context_tokens = int(raw["CONTEXT_TOKENS"]) if raw["CONTEXT_TOKENS"] else None
    except ValueError:
        raise ValueError(f"{prefix}CONTEXT_TOKENS must be a whole number, got {raw['CONTEXT_TOKENS']!r}") from None
    try:
        timeout_seconds = float(raw["TIMEOUT_SECONDS"]) if raw["TIMEOUT_SECONDS"] else None
    except ValueError:
        raise ValueError(f"{prefix}TIMEOUT_SECONDS must be a number of seconds, got {raw['TIMEOUT_SECONDS']!r}") from None
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(f"{prefix}TIMEOUT_SECONDS must be more than 0, got {raw['TIMEOUT_SECONDS']!r}")
    return _LLMValues(
        backend=backend,
        model=raw["MODEL"] or DEFAULT_LLM_MODEL,
        base_url=raw["BASE_URL"],
        api_key=raw["API_KEY"] or DEFAULT_LLM_API_KEY,
        context_tokens=context_tokens,
        timeout_seconds=timeout_seconds,
    )


def _check_llm_variable_names() -> None:
    """Fail if an environment variable looks like an LLM variable but the app does not read it (a typo would be ignored).

    Two shapes are caught: the name of an LLM variable with a task that does not exist (`EXTRATOR_LLM_BACKEND`), and a
    variable of the default LLM or of a real task whose last part is not an LLM variable (`EXTRACTOR_LLM_MODLE`).
    """
    for name in os.environ:
        match = re.fullmatch(r"(?:([A-Z][A-Z0-9]*)_)?LLM_([A-Z0-9_]+)", name)
        if not match:
            continue
        prefix, variable = match.groups()
        if prefix and prefix.lower() not in LLM_TASKS:
            if variable in LLM_VARIABLES:
                raise ValueError(f"{name}: {prefix.lower()!r} is not a task that calls an LLM, expected one of {', '.join(LLM_TASKS)}")
        elif variable not in LLM_VARIABLES:
            raise ValueError(f"{name} is not an LLM variable, expected {prefix + '_' if prefix else ''}LLM_ plus one of {', '.join(LLM_VARIABLES)}")


# dataclass: Python writes the boilerplate that builds the class from its fields.
# frozen=True: values can't be changed after a Settings object is created.
@dataclass(frozen=True)
class Settings:
    llm_backend: LLMBackend = "ollama"
    llm_base_url: str | None = None
    llm_model: str = DEFAULT_LLM_MODEL
    llm_api_key: str = field(default=DEFAULT_LLM_API_KEY, repr=False)
    llm_context_tokens: int | None = None
    llm_timeout_seconds: float | None = None
    # The LLM of the tasks that have their own `<TASK>_LLM_*` variables, by task name.
    task_llms: dict[str, LLMSettings] = field(default_factory=dict)
    reference_date: date | None = None
    db_path: str = "kalia.db"
    owner_id: str = "local"
    sample_company: str | None = None
    commitments_source: CommitmentsSource = "saved"

    def default_llm(self) -> LLMSettings:
        """The LLM of the tasks that have none of their own: the one described by `LLM_*`."""
        return LLMSettings.resolve(
            self.llm_backend, self.llm_model, self.llm_base_url, self.llm_api_key, self.llm_context_tokens, self.llm_timeout_seconds
        )

    def llm_for(self, task: str) -> LLMSettings:
        """The LLM a task uses: its own if it has `<TASK>_LLM_*` variables, else the default one."""
        if task not in LLM_TASKS:
            raise ValueError(f"unknown LLM task {task!r}, expected one of {', '.join(LLM_TASKS)}")
        return self.task_llms.get(task) or self.default_llm()

    # property: use it like a field, `settings.today`, without parentheses.
    @property
    def today(self) -> date:
        """The date the app treats as "today": the reference date if set, else the system date."""
        return self.reference_date or date.today()

    # classmethod: called on the class itself, `Settings.from_env()`, to create a new Settings.
    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the environment (after loading the env files); empty or missing variables fall back to defaults.

        Raises ValueError if an LLM is set up incompletely (the message names the variable to set).
        """
        load_env_files()
        _check_llm_variable_names()
        defaults = cls()
        llm = _read_llm("LLM_", None)
        task_llms = {}
        for task in LLM_TASKS:
            values = _read_llm(f"{task.upper()}_LLM_", task)
            if values:
                task_llms[task] = LLMSettings.resolve(**values)
        reference_date = os.environ.get("REFERENCE_DATE")
        source = os.environ.get("COMMITMENTS_SOURCE") or defaults.commitments_source
        if source not in COMMITMENTS_SOURCES:
            raise ValueError(f"COMMITMENTS_SOURCE must be one of {', '.join(COMMITMENTS_SOURCES)}, got {source!r}")
        return cls(
            llm_backend=llm["backend"] if llm else defaults.llm_backend,
            llm_base_url=llm["base_url"] if llm else defaults.llm_base_url,
            llm_model=llm["model"] if llm else defaults.llm_model,
            llm_api_key=llm["api_key"] if llm else defaults.llm_api_key,
            llm_context_tokens=llm["context_tokens"] if llm else defaults.llm_context_tokens,
            llm_timeout_seconds=llm["timeout_seconds"] if llm else defaults.llm_timeout_seconds,
            task_llms=task_llms,
            reference_date=date.fromisoformat(reference_date) if reference_date else None,
            db_path=os.environ.get("DB_PATH") or defaults.db_path,
            owner_id=os.environ.get("OWNER_ID") or defaults.owner_id,
            sample_company=os.environ.get("SAMPLE_COMPANY") or defaults.sample_company,
            commitments_source=source,
        )
