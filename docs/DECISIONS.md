# Decisions

Real choices between alternatives, newest at the top. This file is also filled in with each /close-feature.

## One story file per company, pasted whole into every generation batch
Date: 2026-10-07
Chose: `data/<company>/story.md` lists, per project, a situation and dated facts that no document may contradict. Every batch prompt includes it whole, and new documents add their facts to it before their `expected` files are designed.
Rejected: one story file per project (every batch would need a selection of parts); facts with ids referenced from each `expected` file (ids to maintain and prompts to assemble by hand).
Why: about 60 lines are cheap to paste, and a single file is the one place where consistency between documents is kept.
Source: issue #5, commit 8adbaa5; the rule goes into `data/generation/base.md` in #6.

## Acceptance questions as a versioned JSONL with fixed answer rules
Date: 2026-10-07
Chose: `data/<company>/questions.jsonl`, one line per concrete question with a `version` (`v1`; published questions are never edited, new ones get `v2`), the expected answer as commitment ids, and fixed rules: "this week" is the reference date plus 6 days, without overdue or undated commitments; every commitment counts as open; "my boss" is the user's boss in the catalog.
Rejected: a hand-written table from question to documents (cannot be checked against the data and drifts); one file per version (adding questions stops being adding a line).
Source: issue #5, commit 66925d0; format in `docs/PLAN.md` section 12.
Refined 2026-10-07: the format now lives in `docs/DATASET.md`.

## Expected files carry commitment ids, raw deadline text and negative cases
Date: 2026-10-07
Chose: each commitment in `expected/<document id>.json` has an id (`<document id>-cN`) and both `due` (absolute) and `due_text` (the phrase as written); `mentions` lists commitments of other documents that the text names without promising again; `not_commitments` lists phrases the text must contain that are not commitments.
Rejected: no ids (questions could not cite their answers); only `due` (a failed extraction could not be traced to date arithmetic); leaving out mentions and conditionals (duplicates and false positives would go unmeasured).
Source: issue #5, commit 8adbaa5; format in `docs/PLAN.md` section 12.
Refined 2026-10-07: the format now lives in `docs/DATASET.md`.

## The dataset defines the reference date
Date: 2026-10-07
Chose: `company.json` holds `reference_date` (2026-10-12) and `held_out` (documents left out of the initial load, for question 5); questions do not repeat the date.
Rejected: a date per question (two sources that drift); defining it only in the app configuration (the SPEC says the default comes from the dataset).
Source: issue #5, commit 8adbaa5.

## Synthetic catalog as per-company JSONL files
Date: 2026-10-07
Chose: `data/<company>/` holds `company.json` plus one JSONL file per entity type (`people.jsonl`, `projects.jsonl`); every record has a stable id `<company>-pNN` / `<company>-jNN` and a `company` field. The files are the test fixture; the app stores everything in SQLite.
Rejected: a single JSON file (noisy diffs, any new field touches the whole object); loading the catalog into a database now (the storage module does not exist yet, and the dataset must be readable and reviewable as text).
Why: adding a person, a project or a whole new entity type or company is adding a line or a file.
Source: issue #2, commit eae6c79; layout in `docs/PLAN.md`.

## LLM failures are raised as `LLMError`
Date: 2026-10-05
Chose: every LLM client raises `LLMError` for failed requests, timeouts and empty answers; callers are expected to catch it and degrade instead of failing the whole request.
Rejected: letting provider exceptions (`openai.OpenAIError`) reach callers (every module would depend on the provider library); returning an empty string on failure (hides the failure).
Source: issue #1, commit 598a918.

## Module contracts are `Protocol` interfaces and frozen dataclasses
Date: 2026-10-05
Chose: each module (ingestion, extraction, storage, answering, llm) exposes a `typing.Protocol`; the shapes passed between them (`Document`, `Commitment`, `Catalog`) are frozen dataclasses in `app/models.py`.
Rejected: abstract base classes (implementations would have to inherit from them); `TypedDict` for the shapes (plain mutable dicts, no attribute access).
Why: any class with the right methods fits, so swapping SQLite or the LLM client needs no change elsewhere.
Source: issue #1, commit 598a918.

## The app is built by a `create_app` factory
Date: 2026-10-05
Chose: `create_app(settings=None, llm=None)` in `app/main.py` builds the app on demand; uvicorn runs it with `--factory`. Without arguments it reads settings from the environment; tests and scripts can pass settings or an LLM directly.
Rejected: a module-level `app = FastAPI(...)` (settings are read when the module is imported, so swapping the LLM in a test needs environment tricks).
Why: the LLM must be replaceable (fake in CI, real locally) without touching the rest of the app.
Source: issue #1, commit 598a918.

## Configuration defaults live in the code only
Date: 2026-10-05
Chose: defaults are written in `app/config.py` (plus the Dockerfile for the two container-specific ones); `.env.example` lists variable names and comments, all commented out and without values.
Rejected: repeating the default values in `.env.example` (two sources that drift, and invites pasting real keys into a committed file).
Why: in Docker an empty variable overrides the default instead of leaving it, so the example lines stay commented.
Source: issue #1, commit 598a918.

## LLM selected by `LLM_BACKEND`, fake injected in code tests
Date: 2026-10-05
Chose: `LLM_BACKEND` (`real`/`fake`, default `real`) picks the client at startup; the smoke test and CI set `fake`. Code-level tests pass the fake directly, with no variable.
Rejected: building the app inside the smoke test with the fake injected (skips the real startup path the container uses); an `openai` backend name (reads as "uses OpenAI").
Source: issue #1, commit 598a918.

## The app runs in Docker from the start; Ollama stays on the host
Date: 2026-10-05
Chose: the app always runs in a container (compose, SQLite in a Docker volume); Ollama runs on the host and is reached as `host.docker.internal`.
Rejected: running the app natively with `uv run` and Docker only for other PCs (the user wants to use it the deployed way from day one); Ollama as a second container (not needed yet).
Source: issue #1, commit 598a918.

## Documents: free-text body plus a metadata header
Date: 2026-10-05
Chose: each document is plain informal text with a small header (id, type, date, participants); the loader only joins header and body, and the LLM extracts commitments only.
Rejected: raw text with the LLM also extracting date and participants (outside V0 scope, error-prone name matching); fully structured documents (unrealistic).
Source: initial approved plan; issue #3 covers sources without headers.

## CI from the first code
Date: 2026-10-05
Chose: GitHub Actions on push/PR to main (uv sync, smoke test, Docker build) with a fake LLM, from the first unit of code.
Rejected: adding CI later (the smoke test and the image would go unchecked for a while); mypy in CI (not needed for a light MVP).
Source: initial approved plan; issue #1.

## Prompts as separate files
Date: 2026-10-05
Chose: one file per prompt in `app/prompts/`.
Rejected: prompts inline in the code (harder to review and compare when they change).
Source: initial approved plan.

## LLM client: OpenAI-compatible endpoint
Date: 2026-10-05
Chose: one OpenAI-compatible client configured with `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`; Ollama local as the documented default.
Rejected: a native Anthropic adapter for now (deferred); one adapter per provider (more code for the same swap).
Source: initial approved plan.

## Web layer: FastAPI plus one minimal HTML page
Date: 2026-10-05
Chose: FastAPI serving one HTML page with no build step.
Rejected: CLI chat (less natural for the chat flow); Streamlit (extra dependency).
Source: initial approved plan.

## Storage: SQLite
Date: 2026-10-05
Chose: SQLite with `owner_id` on every table and storage behind an interface; the file lives in a Docker volume.
Rejected: Postgres (a second container and more setup for a single local user; revisit for multi-user or pgvector).
Source: initial approved plan.
