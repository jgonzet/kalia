"""Manual check: send a simple question to the real LLM of each task and print its answer.

A task whose LLM is the same as one already checked is not asked again.
Run inside the container with `docker compose run --rm app python scripts/operate/check_llm.py`.
Not part of the smoke test or CI: it needs a reachable LLM endpoint.
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # make `app` importable

from app.config import LLM_TASKS, LLMSettings, Settings  # noqa: E402
from app.llm import LLMError, build_llm  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    checked: dict[LLMSettings, str] = {}
    failed = False
    for task in LLM_TASKS:
        llm = settings.llm_for(task)
        if llm.backend == "fake":
            print(f"{task}: the backend is 'fake'; nothing to check.")
        elif llm in checked:
            print(f"{task}: same LLM as {checked[llm]}, already checked.")
        else:
            checked[llm] = task
            failed = not check(task, llm) or failed
    if not checked:
        print("No real LLM is configured.")
        return 1
    return 1 if failed else 0


def check(task: str, llm: LLMSettings) -> bool:
    """Ask the LLM of a task a simple question and, with Ollama, check its context window; say whether it all went well."""
    where = f" at {llm.base_url}" if llm.base_url else ""
    print(f"{task}: asking {llm.model} ({llm.backend}){where} ...")
    try:
        answer = build_llm(llm).complete("Reply with the single word: OK")
    except LLMError as exc:
        print(f"CHECK FAILED: {exc}")
        return False
    print(f"Answer: {answer}")
    return llm.backend != "ollama" or window_matches(llm)


def window_matches(llm: LLMSettings) -> bool:
    """Ask Ollama which context window the loaded model runs with and say whether it is the one in the settings."""
    with urllib.request.urlopen(llm.base_url.rstrip("/") + "/api/ps", timeout=10) as response:
        loaded = json.load(response)["models"]
    windows = [m["context_length"] for m in loaded if m["name"] == llm.model]
    if windows != [llm.context_tokens]:
        print(f"CHECK FAILED: the server runs {llm.model} with a window of {windows}, expected {llm.context_tokens}")
        return False
    print(f"Context window: {windows[0]} tokens, as configured")
    return True


if __name__ == "__main__":
    sys.exit(main())
