"""LLM client for Ollama's native API, which lets each request set the context window (`/v1` ignores it)."""

import json
import urllib.error
import urllib.request
from typing import TypedDict

from app.llm import LLMError


class OllamaStats(TypedDict):
    """What Ollama reports about the last call; `scripts/quality/evals/measure_latency.py` reads it."""

    prompt_tokens: int
    answer_tokens: int
    answer_seconds: float  # time the server spent writing the answer
    done_reason: str  # "stop" when the model finished, "length" when it was cut off


class OllamaLLM:
    def __init__(self, base_url: str, model: str, context_tokens: int, timeout_seconds: float) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._context_tokens = context_tokens
        self._timeout_seconds = timeout_seconds
        self.last_stats: OllamaStats | None = None  # of the last call that worked; None before it and after a failure

    def complete(self, prompt: str) -> str:
        self.last_stats = None
        body = {
            "model": self._model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"num_ctx": self._context_tokens},
        }
        request = urllib.request.Request(self._url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                data = json.load(response)
                content = data["message"]["content"]
        except (OSError, ValueError, KeyError, TypeError) as exc:  # urllib errors are OSError; bad JSON is ValueError
            raise LLMError(f"LLM request failed: {exc}") from exc
        if not content:
            raise LLMError("LLM returned an empty answer")
        self.last_stats = OllamaStats(
            prompt_tokens=data.get("prompt_eval_count", 0),
            answer_tokens=data.get("eval_count", 0),
            answer_seconds=data.get("eval_duration", 0) / 1e9,
            done_reason=data.get("done_reason", ""),
        )
        return content
