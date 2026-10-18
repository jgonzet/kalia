"""Manual check: send a simple question to the configured real LLM and print its answer.

Run inside the container with `docker compose run --rm app python scripts/check_llm.py`.
Not part of the smoke test or CI: it needs a reachable LLM endpoint.
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.llm import LLMError, build_llm  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    if settings.llm_backend == "fake":
        print("LLM_BACKEND is 'fake'; nothing to check.")
        return 1
    print(f"Asking {settings.llm_model} at {settings.base_url} ...")
    try:
        answer = build_llm(settings).complete("Reply with the single word: OK")
    except LLMError as exc:
        print(f"CHECK FAILED: {exc}")
        return 1
    print(f"Answer: {answer}")
    if settings.llm_backend == "ollama" and not window_matches(settings):
        return 1
    return 0


def window_matches(settings: Settings) -> bool:
    """Ask Ollama which context window the loaded model runs with and say whether it is the one in the settings."""
    with urllib.request.urlopen(settings.base_url.rstrip("/") + "/api/ps", timeout=10) as response:
        loaded = json.load(response)["models"]
    windows = [m["context_length"] for m in loaded if m["name"] == settings.llm_model]
    if windows != [settings.context_tokens]:
        print(f"CHECK FAILED: the server runs {settings.llm_model} with a window of {windows}, expected {settings.context_tokens}")
        return False
    print(f"Context window: {windows[0]} tokens, as configured")
    return True


if __name__ == "__main__":
    sys.exit(main())
