"""Manual check: send a simple question to the configured real LLM and print its answer.

Run inside the container with `docker compose run --rm app python scripts/check_llm.py`.
Not part of the smoke test or CI: it needs a reachable LLM endpoint.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.llm import LLMError, build_llm  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    if settings.llm_backend != "real":
        print("LLM_BACKEND is not 'real'; nothing to check.")
        return 1
    print(f"Asking {settings.llm_model} at {settings.llm_base_url} ...")
    try:
        answer = build_llm(settings).complete("Reply with the single word: OK")
    except LLMError as exc:
        print(f"CHECK FAILED: {exc}")
        return 1
    print(f"Answer: {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
