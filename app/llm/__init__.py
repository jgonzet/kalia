"""LLM provider interface and the implementations selectable by configuration."""

from typing import Protocol

from app.config import DEFAULT_OLLAMA_CONTEXT_TOKENS, Settings


class LLMError(Exception):
    """The LLM call failed, timed out or returned something unusable."""


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Send a prompt and return the model's text answer; raises LLMError on failure."""
        ...


def build_llm(settings: Settings) -> LLMClient:
    """Return the LLM client selected by `settings.llm_backend`."""
    if settings.llm_backend == "fake":
        from app.llm.fake import FakeLLM

        return FakeLLM()

    if settings.llm_backend == "ollama":
        from app.llm.ollama import OllamaLLM

        return OllamaLLM(settings.base_url, settings.llm_model, settings.context_tokens or DEFAULT_OLLAMA_CONTEXT_TOKENS)

    from app.llm.openai_compatible import OpenAICompatibleLLM

    return OpenAICompatibleLLM(
        base_url=settings.base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
    )
