# Progress

## Next

1. #5 — Design the expected commitments for the 25 documents
2. #6 — Write the generator prompts and the dataset check script
3. #7 — Generate and review the 25 synthetic documents

Synced at: eae6c79

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

— Resolved 2026-10-05: unit tests for `Settings.from_env` added (`tests/test_config.py`) and run in CI.

— Resolved 2026-10-05: CI ran green on main after pinning setup-uv to v10.2.0. Closed #1.

## 2026-10-07 — Synthetic catalog for La Manija Games

**Purpose:** fix the fictional company that every later piece of the dataset (expected commitments, generator prompts, documents) refers to, and the layout those pieces will live in.

**Input:** none; the content was designed with the project owner. The layout and formats come from `docs/PLAN.md`.

**Output:** `data/lamanija/` with `company.json` (name, description, `user_id` of the protagonist), `people.jsonl` (12 people), `projects.jsonl` (4 projects) and `ORGCHART.md` (a table of the org chart). No code in the app reads these files yet.

**Logic:**
1. The company is an indie game studio, La Manija Games. People have role, area, `level` (1 = CEO, 2 = directors, 3 = everyone else) and `reports_to`. The protagonist is Lalo Landa, a Producer who reports to the Director of Production; his hierarchy and boss are derived from `reports_to`, as the SPEC requires.
2. Names are The Simpsons characters with their Latin American dubbing names, 6 women and 6 men, to keep the catalog fun without losing a realistic structure.
3. Projects (Choripixels, Motocrotos Adventures, Jimboland, Turrokiller) have status and a deadline each, between 2026-11-13 and 2027-02-26, so the acceptance question about "due this week" can have deadlines before, within and after the reference week.
4. `scripts/orgchart.py` regenerates `ORGCHART.md` from `people.jsonl`; the table is never edited by hand.
5. Catalog format and ids: see "Synthetic catalog as per-company JSONL files" in `docs/DECISIONS.md`.

**Important assumptions:**
- Catalog values (roles, statuses, descriptions) are in Spanish; keys are in English.
- The company slug `lamanija` is the prefix of every id and will be the prefix of the document ids (`lamanija-NNNN`).
- `level` is only an integer where 1 is the top; nothing consumes it yet.
- `ORGCHART.md` is a table because a Mermaid diagram rendered too small to read.
- The names are copyrighted characters; this is fine in a private repo and should be reviewed with `/prep-public` before making it public. The Latin American dubbing names were written from memory and not verified.
- The deadlines are chosen relative to a reference date that is not set yet (decided in #5).

**Location:** `data/lamanija/`, `scripts/orgchart.py`.

**Tests:** none. `company.json` and both JSONL files parse, every `reports_to` points to an existing person, and `user_id` points to an existing person (one-off check, not saved as a script; the permanent check is #6).

**Issues:** closed #2.
