# Progress

## Next

1. #6 — Write the generator prompts and the dataset check script
2. #7 — Generate and review the 25 synthetic documents

Synced at: 979e478

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

— Resolved 2026-10-07: the reference date is 2026-10-12 and lives in `company.json` (`reference_date`), set in #5.

## 2026-10-07 — Expected commitments, story and acceptance questions for La Manija Games

**Purpose:** fix, before any text exists, what each of the 25 documents must contain and what the chat must answer, so the generator prompts (#6) and the documents (#7) are written from a single reference.

**Input:** the catalog from the previous entry and the acceptance questions of `docs/SPEC.md`.

**Output:** in `data/lamanija/`: `story.md` (background facts), `expected/lamanija-0001..0025.json` (25 files, 75 commitments, 15 mentions, 3 non-commitments), `questions.jsonl` (11 concrete questions, version `v1`), and `reference_date` and `held_out` in `company.json`. No app code.

**Logic:**
1. `story.md` lists per project a situation and dated facts that no document may contradict. Its header states the rule.
2. Each `expected` file first got the document frame (type, date, participants, projects, author for emails, one-line `brief`) so coverage could be checked: Lalo in all 25, Smithers (his boss) in 13, Burns in 3 meetings, every project in at least 4 documents.
3. Then the commitments were filled in for all 25: who, to whom, what, absolute `due`, the original `due_text`, and project. Deadlines are spread around the reference date 2026-10-12: 25 overdue, 16 in the week 12–18/10, 20 later, 14 undated. A commitment is promised in one document only; other documents may name it (`mentions`) without promising it again.
4. `questions.jsonl` was computed from the `expected` files with the rules in the decision "Acceptance questions as a versioned JSONL". `lamanija-0025` is held out: question 5 has the answer before and after ingesting it.
5. Formats and coverage targets are in `docs/PLAN.md` section 12. Decisions: "One story file per company, pasted whole into every generation batch", "The dataset defines the reference date", "Expected files carry commitment ids, raw deadline text and negative cases" and "Acceptance questions as a versioned JSONL with fixed answer rules".

**Important assumptions:**
- 9 emails, 8 meetings, 8 chats; the meetings 0012 and 0023 are the long ones (up to about 1200 words, 7 and 8 commitments).
- Turrokiller has 34 commitments, Choripixels 12, Motocrotos 16, Jimboland 9: the studio's priority is the festival demo, so the dataset is not balanced between projects.
- The festival has costs (participation budget); the catalog says nothing about it, it was invented for the story.
- A commitment exists only if the text shows the person accepting it, so in emails with commitments from others the reply is inside the same document.
- A missing `extractions` key means "designed, not annotated"; an empty list means "annotated, nothing to extract".
- Four commitments have a `due_text` that cannot be resolved to a date ("todos los viernes", "apenas lo configure"); two depend on another dated fact ("dos semanas antes de la revisión del prototipo"). They are on purpose the hardest cases.
- Whether the local model resolves relative deadlines or tells a mention from a new promise is not verified; the data is what will measure it.

**Location:** `data/lamanija/` (`story.md`, `expected/`, `questions.jsonl`, `company.json`), `docs/PLAN.md` section 12.

**Tests:** none saved. One-off checks, not kept as a script: every due date is a weekday, every mention points to a commitment of an earlier document, names match the catalog, relative deadlines were checked by hand against each document's date. The questions were computed by a throwaway script. The permanent check is `check_dataset.py` (#6).

**Issues:** closed #5. Opened #8.

— Resolved 2026-10-07: the formats named in Logic step 5 and Location now live in `docs/DATASET.md` instead of `docs/PLAN.md` section 12; the rules for extending the dataset are in the "Synthetic dataset" section of `CLAUDE.md`.
