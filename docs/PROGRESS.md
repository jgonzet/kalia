# Progress

## Next

1. #1 — Project skeleton, fake LLM, smoke test and CI
2. #2 — Design the synthetic dataset and the prompts to generate it

Synced at: 598a918

This file is filled in with each /close-feature.

## 2026-10-05 — Project skeleton, fake LLM, smoke test and CI

**Purpose:** give the project a place to live and a check that runs from the first line of code: the app starts in Docker, the LLM is replaceable, and CI never depends on Ollama or API keys.

**Input:** environment variables (names in `.env.example`, defaults in `app/config.py`): `LLM_BACKEND` (`real`/`fake`), `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `REFERENCE_DATE`, `DB_PATH`.

**Output:** a FastAPI app with `GET /health` (`{"status": "ok", "llm_backend": ...}`); two LLM clients behind one interface; a smoke test; a Docker image and compose file; a CI workflow. No extraction, storage, retrieval or chat yet.

**Logic:**
1. `Settings.from_env()` reads the environment; unset or empty variables fall back to defaults. `REFERENCE_DATE` sets "today"; unset means the system date.
2. `build_llm(settings)` returns `FakeLLM` (fixed text, ignores the prompt) or `OpenAICompatibleLLM` (OpenAI-compatible endpoint, Ollama by default; failures and empty answers raise `LLMError`).
3. `create_app()` builds the app with the chosen LLM. Run with `uvicorn app.main:create_app --factory`.
4. `scripts/smoke_test.py` starts the service as a separate process with `LLM_BACKEND=fake`, checks `/health`, checks the fake LLM answers through `build_llm`, and shuts the service down.
5. The ingestion, extraction, storage and answering modules only define typed `Protocol` interfaces. `app/models.py` defines `Document`, `Catalog`, `Person`, `Project` and `Commitment`.

**Important assumptions:**
- The app runs in a container; Ollama runs on the host and is reached as `host.docker.internal` (set in the Dockerfile). Ollama must listen on an address the container can reach.
- The SQLite path points to a Docker volume (`kalia-db`); no SQLite code exists yet.
- The smoke test does not exercise the LLM through the app, because nothing in the app uses the LLM yet.
- The CI workflow has not run on GitHub yet; its action versions were taken from the latest releases and are unverified.

**Location:** `app/`, `scripts/smoke_test.py`, `scripts/check_llm.py`, `Dockerfile`, `compose.yaml`, `.github/workflows/ci.yml`, `.env.example`, `pyproject.toml`.

**Tests:** `uv run scripts/smoke_test.py` passes locally. `docker build` and `docker compose up` work, and `scripts/check_llm.py` got an answer from `qwen2.5:14b` inside the container. No unit tests.
