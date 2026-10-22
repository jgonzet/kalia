"""Tests of `AnthropicLLM` against a local server that imitates the Claude API, and of the timeout reaching the clients."""

import json
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

import pytest

from app.config import LLMSettings
from app.llm import LLMError, build_llm
from app.llm.anthropic import MAX_OUTPUT_TOKENS, AnthropicLLM

API_KEY = "sk-ant-test-secret-key"


class FakeClaudeAPI(HTTPServer):
    """Answers every request with the next scripted (status, body); keeps the requests it received."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.replies: list[tuple[int, dict[str, Any]]] = []
        self.requests: list[dict[str, Any]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"


class _Handler(BaseHTTPRequestHandler):
    server: FakeClaudeAPI

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        status, payload = self.server.replies[0]
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("x-should-retry", "false")  # the SDK would otherwise retry a 429 or a 500 after a pause
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeClaudeAPI]:
    server = FakeClaudeAPI()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", server.url)  # read by the SDK; AnthropicLLM takes no address on purpose
    yield server
    server.shutdown()
    server.server_close()


def message(stop_reason: str, *texts: str) -> tuple[int, dict[str, Any]]:
    return 200, {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [{"type": "text", "text": text} for text in texts],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 3, "output_tokens": 4},
    }


def error(status: int, kind: str) -> tuple[int, dict[str, Any]]:
    return status, {"type": "error", "error": {"type": kind, "message": "something went wrong"}}


def test_a_normal_answer_is_returned_and_the_request_is_built_as_expected(api: FakeClaudeAPI) -> None:
    status, payload = message("end_turn", "Hola, ", "mundo")
    payload["content"].insert(0, {"type": "thinking", "thinking": "hmm", "signature": "sig"})  # blocks that are not text are left out
    api.replies = [(status, payload)]
    assert AnthropicLLM("claude-test", API_KEY, 5).complete("¿Qué hay?") == "Hola, mundo"
    (request,) = api.requests
    assert request["path"] == "/v1/messages" and request["auth"] == f"Bearer {API_KEY}"
    assert request["body"]["model"] == "claude-test"
    assert request["body"]["max_tokens"] == MAX_OUTPUT_TOKENS
    assert request["body"]["messages"] == [{"role": "user", "content": "¿Qué hay?"}]


@pytest.mark.parametrize(
    ("reply", "match"),
    [
        (message("max_tokens", "half an ans"), "cut off"),
        (message("refusal", "I can't"), "declined"),
        (message("end_turn"), "empty"),
        (error(401, "authentication_error"), "LLM request failed"),
        (error(429, "rate_limit_error"), "LLM request failed"),
        (error(500, "api_error"), "LLM request failed"),
    ],
)
def test_a_cut_refused_empty_or_failed_call_is_an_llm_error_without_the_key(api: FakeClaudeAPI, reply: tuple[int, dict[str, Any]], match: str) -> None:
    api.replies = [reply]
    with pytest.raises(LLMError, match=match) as caught:
        AnthropicLLM("claude-test", API_KEY, 5).complete("q")
    assert API_KEY not in str(caught.value) and API_KEY not in repr(caught.value.__cause__)


@pytest.mark.parametrize("backend", ["ollama", "openai_compatible", "anthropic"])
def test_the_timeout_reaches_the_client(backend: str) -> None:
    llm = build_llm(
        LLMSettings(backend=backend, model="m", base_url="http://localhost:1", api_key="k", context_tokens=4096, timeout_seconds=7.5)  # type: ignore[arg-type]
    )
    if backend == "ollama":
        assert llm._timeout_seconds == 7.5
    else:
        assert llm._client.timeout == 7.5
