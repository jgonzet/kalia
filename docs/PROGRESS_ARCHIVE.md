# Progress archive

Entries moved out of [PROGRESS.md](PROGRESS.md), oldest first, unchanged.

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

## 2026-10-09 — Generator prompts and dataset check script

**Purpose:** have, before any document exists, the instructions the generator follows and a check that keeps each document tied to its `expected` file, so the 25 documents (#7) can be written and validated in one pass.

**Input:** the files of `data/lamanija/` from the previous entries; the documents, once they exist.

**Output:** `data/generation/` (`base.md`, `types/{email,meeting,chat}.md`, `fields/commitments.md`), `scripts/check_dataset.py`, and in `docs/DATASET.md` the header syntax of the documents and the sections "Generating documents" and "Checking the dataset". No documents yet, no app code.

**Logic:**
1. The documents are written by Claude Code inside the repo (not by an external chatbot, which `docs/PLAN.md` sections 1, 2 and 8 still describe as the original design; section 13 replaces it). It reads `base.md`, the file of the document's type, `fields/`, the catalog, `story.md` and the `expected` files, and writes `documents/<id>.md`. The steps are in `docs/DATASET.md`.
2. `base.md` holds the rules for every document and points to `types/` and `fields/`; a new source type or a new extracted field is a new file in those folders. The rules for commitments, `mentions` and `not_commitments` live in `fields/commitments.md` only.
3. `check_dataset.py` (standard library only) compares each document with its `expected` file and the catalog: matching ids, type, date and participants, names in the catalog, commitment ids and mentions, and the text hash. What it checks is listed in `docs/DATASET.md`.
4. `--stamp` writes the text hash into the `expected` file and is the only case where the script changes files. `--allow-pending` lets `expected` files without a document pass while the batches are being written.
5. Decision recorded: "The synthetic documents are committed to the repo". The header syntax is a refinement of "Documents: free-text body plus a metadata header".

**Important assumptions:**
- The hash is the SHA-256 of the text after the header, stripped at both ends; the header is compared field by field instead.
- A `due_text` missing from its text is a warning, not an error, because wording may differ in case or spacing.
- An `expected` file without a document is an error unless `--allow-pending` is given.
- `data/generation/` is written in Spanish, like `story.md` and the documents it produces.
- No rules to vary the structure of the documents: the 25 texts may look alike. Known limitation of the dataset.
- The same model designed the `expected` files and writes the texts, so the texts may be easier to extract than real ones.
- The script is not in CI and nobody runs it automatically; `CLAUDE.md` tells whoever works on the dataset to run it.

**Location:** `data/generation/`, `scripts/check_dataset.py`, `docs/DATASET.md`, `docs/PLAN.md` section 13.

**Tests:** `uv run scripts/check_dataset.py --allow-pending` gives `ok` on the 25 `expected` files. The checks on documents (header, hash, `due_text`) have not run because no document exists yet; the first batch of #7 is their first real test. No unit tests.

**Issues:** closed #6. Opened #9.

## 2026-10-09 — The 25 synthetic documents of La Manija Games

**Purpose:** have the input for testing extraction, storage, retrieval and chat: 25 texts whose commitments are known in advance and checked.

**Input:** the files of `data/lamanija/` (`story.md`, catalog, `expected/`), `data/generation/` and `data/generation/session_prompt.md` (prompt v0, given to the generating session with the ids of the batch).

**Output:** `data/lamanija/documents/lamanija-0001.md` to `lamanija-0025.md` (9 emails, 8 meetings, 8 chats; `lamanija-0025` is the held-out one) and the `text_sha256` filled in all 25 `expected` files. `check_dataset.py` gives `ok` without `--allow-pending`. No app code.

**Logic:**
1. A generating Claude Code session wrote each batch following "Generating documents" in `docs/DATASET.md`, ran `check_dataset.py --allow-pending` and reported anything odd per document. It did not stamp or commit. Decision recorded: "One Claude Code session generates the documents, another reviews and accepts them".
2. This session read all 25 texts against their `expected` files: commitments present with the `due_text` wording and not as a list, `mentions` named without a new promise, `not_commitments` present, weekdays and relative deadlines matching the calendar, nothing contradicting `story.md` or earlier texts. Decision recorded: "Review checks the answer key against the text, not the text against a clean ideal".
3. After each batch passed, `--stamp` filled in the hashes. No text needed changes after review.
4. The prompt is kept as a versioned file. Decision recorded: "The generator prompt is a versioned file; new versions go above the old ones".

**Important assumptions:**
- Batches were 5 (0001–0005), 11 (0006–0016) and 9 (0017–0025), not five of five.
- Prompt v0 was edited once, before the last batch, to add "re-read the existing documents before writing"; batches 1 and 2 ran without that step, so "v0" is not the same text in all three.
- Facts that appear in the texts but not in `story.md`, and that no document contradicts: the festival confirms participation after receiving the status report, its PC is unknown, Choripixels has no enemies yet, a temporary animator may join Turrokiller.
- The two long meetings (0012, 0023) have about 700 and 630 words, below the "up to about 1200" of `docs/SPEC.md`.
- Phrases an extractor could read as extra commitments were left in on purpose (e.g. "Tranqui, va a estar" in 0021, "eso lo anoto" in 0023).
- Known limitations carried over from the previous entry: texts may look alike in structure, and may be easier to extract than real ones (same model designed the `expected` files and wrote the texts). In this batch the commitments often repeat the `what` of the `expected` file almost word for word.

**Location:** `data/lamanija/documents/`, `data/lamanija/expected/`, `data/generation/session_prompt.md`. Commit `b45145c`.

**Tests:** `uv run scripts/check_dataset.py` gives `ok` on the 25 documents. Every text was read by hand. The semantic check (does an extractor find these commitments) is #8.

**Issues:** closed #7. Opened #10.

## 2026-10-09 — Dataset loaded into SQLite

**Purpose:** get the 25 documents and the catalog into the app's storage, through the same path a real incoming document will use, so extraction (#8) has something to read.

**Input:** `data/lamanija/` (`company.json`, `people.jsonl`, `projects.jsonl`, `documents/*.md`); `DB_PATH` and the new `OWNER_ID` (default `local`) from the environment; a document body for `POST /documents`.

**Output:** a SQLite file with the tables `documents`, `people`, `projects` and `catalog_meta`; `uv run scripts/load_dataset.py lamanija` loads the catalog and 24 documents; `POST /documents` ingests one more. No commitments table and no extraction yet.

**Logic:**
1. `DatasetSource` reads the company directory, parses each document header and text into a `Document`, and skips the ids in `held_out`.
2. `load_dataset` saves the catalog and sends every document through `ingest_document`, the single entry point to storage.
3. `SqliteStore` saves by id with replace, so loading twice or posting the same document twice leaves one row.
4. `POST /documents` takes a normalized document and calls the same `ingest_document`; it is how `lamanija-0025` is added after the initial load.
Decisions recorded: "One ingestion path for every source; the dataset is an adapter" and "Storage settings live in `compose.yaml`, not in the Dockerfile".

**Important assumptions:**
- `Person` and `Project` now carry the catalog `id` (the dataset links people by id).
- `OWNER_ID` comes from the environment, not from the dataset's `user_id`.
- The schema is created when the store is opened; there are no migrations.
- `participants` is stored as JSON in one column.
- `save_catalog` deletes and rewrites the whole catalog of the owner, so a second company loaded with the same `OWNER_ID` would replace the first.
- `POST /documents` has no authentication (V0 is single-user and local).
- `data/` is excluded from the Docker image (`.dockerignore`), so the loader does not find the dataset inside the container until #9.

**Location:** `app/storage/` (`__init__.py`, `sqlite.py`), `app/ingestion/` (`__init__.py`, `dataset.py`), `app/main.py`, `app/models.py`, `app/config.py`, `scripts/load_dataset.py`, `scripts/smoke_test.py`, `Dockerfile`, `compose.yaml`. Commit `8c43f03`.

**Tests:** `uv run scripts/smoke_test.py` loads 24 documents, reloads without duplicating, posts `lamanija-0025` twice and expects 25. The Docker image builds and the database file is writable inside the container. No unit tests.

**Issues:** closed #10. Opened #11, #12, #13.

## 2026-10-09 — Extraction pipeline and manual Claude Code backend

**Purpose:** have an extractor whose model is interchangeable, and a way to run it with Claude Code from an external session, since there is no paid API and local models are not part of the final solution.

**Input:** a stored `Document` and the `Catalog`; for the manual flow, the stored documents (after `scripts/load_dataset.py`) and an answer file.

**Output:** `build_prompt`, `parse_response`/`parse_items` and `LLMExtractor` in `app/extraction/`; the prompt `app/prompts/extract_commitments.md`; `scripts/manual_extraction.py` with `export` (writes `requests/batch-NN.md`) and `import` (validates an answer file and prints a report). The commitments are not stored yet.

**Logic:**
1. `build_prompt` fills the prompt file with the catalog (names, roles, projects), the document and its date. The file holds the response contract.
2. `LLMExtractor` sends it with `LLMClient.complete` and passes the answer to `parse_response`; invalid items are logged and left out.
3. `export` builds one prompt per stored document, in batches of 8 by default; the owner gives a batch to an external session opened outside the repo and saves its answer as `responses/batch-NN.json`.
4. `import` checks every item against the contract and builds `Commitment` objects with ids `<document id>-cN`; it reports problems, documents missing from the answer and ids that are not stored documents.
Decisions recorded: "Extraction is three pieces: build the prompt, call the model, parse the answer", "The response contract is a list of five fields; ids are assigned by the app" and "The manual Claude Code backend works on self-contained request files, outside the repo".

**Important assumptions:**
- The reference date is not in the prompt: relative deadlines are resolved against the document date.
- `who` and `to_whom` are checked against the catalog, not against the document's participants.
- An extra key in an item is ignored and reported; a missing key leaves the item out.
- The default batch size is 8 and is a parameter of `export`.
- `import` validates but does not store: `CommitmentStore` has no SQLite implementation until #11.
- The three real batches were run once (72 commitments valid, 0 problems). That only says the answers follow the contract, not that they are the right commitments; that is #8. If the prompt or the contract changes, the batches have to be run again.
- `LLMExtractor` has no caller in the app yet.

**Location:** `app/extraction/` (`prompt.py`, `parse.py`, `llm_extractor.py`, `manual.py`), `app/prompts/extract_commitments.md`, `scripts/manual_extraction.py`. Commit `3495401`.

**Tests:** manual: export on the 24 stored documents, an import with one valid and one invalid item, and the three real batches imported with 0 problems. No unit tests.

**Issues:** closed #12. Opened #14.

## 2026-10-09 — Commitments table in SQLite

**Purpose:** give extracted commitments somewhere to be stored, so extraction (#14, #8) and retrieval can persist them.

**Input:** a document id and the list of `Commitment` extracted from it.

**Output:** rows in a new `commitments` table of the same SQLite file as documents and catalog; `list_commitments()` returns them as `Commitment`. Nothing calls these methods yet: `scripts/manual_extraction.py import` still only validates.

**Logic:**
1. `SqliteStore` creates the `commitments` table (and an index on owner + document) on open, like the other tables; every row carries `owner_id`.
2. `save_document_commitments(document_id, commitments)` deletes that owner's rows for the document and inserts the new list, in one transaction.
3. `list_commitments()` returns all of the owner's commitments ordered by id; dates are stored as ISO text, `due` and `project` may be null.
4. `scripts/smoke_test.py` gained `check_commitments`: re-saving does not duplicate, `due` round-trips, saving an empty list clears the document.

**Important assumptions:**
- Replace-per-document semantics: see "Saving a document's commitments replaces everything stored for that document" in `docs/DECISIONS.md`.
- The `Store` protocol does not include `CommitmentStore`; whoever first needs both (#14) decides.
- No foreign key to `documents`: commitments can be saved for a document id that is not stored.

**Location:** `app/storage/sqlite.py`, `scripts/smoke_test.py`.

**Tests:** smoke check only; no unit tests yet (#13).

**Issues:** closed #11.

## 2026-10-09 — Extraction on ingestion and commitments stored by catalog id

**Purpose:** connect extraction to storage, so commitments reach the `commitments` table both for new documents and for the answers already obtained with Claude.

**Input:** `POST /documents` (same body as before); `responses/batch-NN.json` files through `scripts/manual_extraction.py import`.

**Output:** `POST /documents` now answers `{"id", "stored", "extracted"}`. Commitments are stored with catalog ids (`who_id`, `to_whom_id`, `project_id`). Importing the three real batches gives 72 commitments.

**Logic:**
1. `POST /documents` stores the document (`ingest_document`), then `extract_and_store` loads the catalog, calls the extractor and saves the result with `save_document_commitments`.
2. If the LLM call fails or there is no catalog, it logs and returns False: the document stays, stored commitments are untouched, the response says `extracted: false`.
3. `create_app` gets an `extractor`; by default only the real backend builds one. See "Extraction runs after the document is stored; if it fails, the document stays" and "Only the real backend extracts on ingestion; `create_app` takes an optional extractor" in `docs/DECISIONS.md`.
4. `parse` validates the model's names against the catalog and translates them to ids. See "Commitments store catalog ids, not names".
5. `manual_extraction.py import` validates an answer file and saves each processed document's valid commitments; re-importing replaces them.

**Important assumptions:**
- The manual import saves directly and does not go through `extract_and_store`: the answer already exists.
- `Store` now includes `CommitmentStore`.
- If the catalog repeated a name, it would resolve to the last id; names are unique in the dataset.
- An import with problems still stores the valid commitments of each document and replaces what it had; the problems are printed.
- The initial load (`load_dataset.py`) does not extract: the real dataset's commitments come from `import`.

**Location:** `app/extraction/run.py`, `app/extraction/parse.py`, `app/main.py`, `app/storage/`, `scripts/manual_extraction.py`, `scripts/smoke_test.py`.

**Tests:** smoke checks with a stub extractor (stores, and keeps the document when it fails); a real import of the three batches into a temporary database (72 commitments, same count after re-importing). Correctness of the extracted commitments is not checked (#8). No unit tests yet (#13).

**Issues:** closed #14.

## 2026-10-09 — Extraction evaluation against the expected files and an ordered manual flow

**Purpose:** know whether the commitments extracted (not just validated) match the answer key of the dataset, and make the manual extraction path a sequence that says its own next step.

**Input:** the SQLite database (`DB_PATH`, `OWNER_ID`) and `data/<company>/expected/*.json`; for the manual flow, `requests/` and `responses/`.

**Output:** `evaluate_extraction.py` prints a table per document (worst first), the detail of documents with errors and totals, and can save everything as JSON (`--out`). On the real 24 documents with the three Claude batches: 70 of 73 expected matched (recall 96%), 2 extra of 72 (precision 97%), due correct 68/70, project correct 69/70. `manual_extraction.py status` prints where the manual flow stands and the next command; `import` accepts several files.

**Logic:**
1. Each `expected` file is read with names translated to catalog ids.
2. Per document, extracted and expected commitments are paired in two passes: same people and due date, then same people with another due date (a match with a wrong due date). Ties go to the most similar `what`.
3. Unpaired expected ones are MISSING and unpaired extracted ones are EXTRA.
4. Totals add up the counts of all documents, so a document with few commitments does not weigh like one with many and documents with none do not divide by zero.
5. Procedure to repeat it (one database per model, JSON per run): README, "Evaluate the extraction". See "The extraction evaluation is a standalone script, not part of the app" in `docs/DECISIONS.md`.

**Important assumptions:**
- Only documents that are stored and annotated are evaluated; the held-out one is skipped until it is ingested.
- `not_commitments` are free prose and are not matched automatically; the report counts the extra commitments of documents that have them and prints the phrases.
- The three errors found (0023, 0015, 0007) were not yet checked against the texts: they can be the model's or an ambiguous `expected`.
- `due_text` is not used.
- No command extracts the whole dataset with the real backend, and runs are compared by hand from the JSON files.

**Location:** `scripts/evaluate_extraction.py`, `scripts/manual_extraction.py`, `README.md` ("Evaluate the extraction").

**Tests:** run by hand on the real database and on a temporary one (`--doc`, `--out`, unknown document, `status` in each state); smoke test still passes. No unit tests (#13).

**Issues:** closed #8 (its chat half moved to #16).
Opened #15 (extract a whole dataset with the real backend), #16 (evaluate chat answers), #17 (retrieval), #18 (chat).

## 2026-10-15 — Rule-based retrieval and the retrieval bank

**Purpose:** pick, from the stored commitments, the ones a question needs, and know how well that is done, apart from the chat (which does not exist yet) and from the extraction.

**Input:** a question as text; the stored commitments and the catalog. For the measurement: `data/<company>/expected/`, `retrieval_bank.jsonl` and `questions.jsonl`.

**Output:** `RuleRetriever.retrieve(question) -> list[Commitment]`; a bank of 58 questions in 9 categories for `lamanija`; `scripts/evaluate_retrieval.py` (counts per category and total, a log of each run in `runs/metrics.jsonl`); `scripts/evaluate_extraction.py` now writes its runs to the same log (`--model` names the model); `scripts/check_bank_sensitivity.py`. On the 13 acceptance questions the retrieval gets everything and nothing else. On the bank (75 measurements, some taken after the held-out document) it loses no commitment, with precision 27%, against 16% for the baseline that returns everything. Nothing in the app calls `retrieve` yet (#18).

**Logic:**
1. `find_filters` reads the question text: it recognises a person (full name, or a name part no one else shares), turns "jefe de X" and "jefe de mi jefe" into that person's manager, "mi jefe" into the user's, and "esta semana" or "la semana que viene" into a date range. Any other week gets no date filter.
2. A person means "the commitments shared with the user" only if the question speaks of the user ("con", "tengo", "mi", "me", "yo", "prometí", "debo"); otherwise it means any commitment of theirs. "Involucr..." always means any.
3. The filters are applied in Python over `list_commitments()`: people joined with OR, people and dates with AND. Without any filter, or without a catalog, every commitment is returned. See "The rule-based retrieval narrows only when it understands the phrase; otherwise it widens" and "Retrieval is one replaceable function; the first version is rules over the question text".
4. The bank (`scripts/retrieval_bank.py` and `scripts/retrieval_bank_<company>.py`) defines each question as a condition over one commitment and computes its correct answer from the `expected` files, before and after the held-out document, without importing `app/`. `check_dataset.py` recomputes it and fails if a published answer changes. See "The answers of the retrieval bank are computed from conditions..." and "The retrieval has its own bank of questions...".
5. `evaluate_retrieval.py` builds a temporary database from the `expected` files, runs the retriever on every question and counts missing and extra commitments ("The retrieval is measured on a database built from the `expected` files..."). `--retriever all` measures the baseline and `--strict` fails if a question loses commitments without declaring a `known_gap`.
6. `check_bank_sensitivity.py` breaks one rule of the retriever at a time, in memory, and checks that some question notices; 15 of 16 mutations are noticed, the other one (a week one day shorter) cannot be with this dataset, which has no weekend deadlines.

**Important assumptions:**
- The first version of the rules, measured on the bank, lost 35 commitments; the three changes that brought it to 0 were made after seeing which questions failed, so the bank is now a development set, not a fair exam of the rules. Questions written without looking at the rules are still needed to measure them fairly.
- The meaning of every term the dataset did not define ("hoy", "mañana", "este mes", "con X", "mis pares", an ambiguous surname = both people, and so on) was chosen while writing the bank; they are in `docs/DATASET.md`.
- The user is found in the catalog by name (`Catalog.user` holds the name, not the id). A surname shared by two people picks no one, silently, and the result gets wider.
- The list of words that refer to the user is short. A phrase without them gives a wider result, never a narrower one.
- The retrieval loads every commitment into memory and filters in Python.
- The bank supports one held-out document, like `questions.jsonl`; the latest version of each question id is the one measured.
- The retrieval and the baseline are measured on the `expected` commitments, so extraction errors are out of this measurement.
- `check_bank_sensitivity.py` patches names inside `app/answering/retrieval.py`; a refactor that renames them breaks it until it is updated.
- The four reference runs at commit `17fdd83` are in `runs/metrics.jsonl`; the earlier ones, marked `*`, were made on uncommitted code during development.
- A logged extraction run names its model by hand (`--model`), and its prompt hash is that of the prompt file at evaluation time, not necessarily the one that made the commitments.
- The CI does not run `check_dataset.py` or `evaluate_retrieval.py --strict` yet; that is the owner's call.

**Location:** `app/answering/` (`__init__.py`, `retrieval.py`), `scripts/` (`evaluate_retrieval.py`, `evaluate_extraction.py`, `run_log.py`, `retrieval_bank.py`, `retrieval_bank_lamanija.py`, `check_bank_sensitivity.py`, `check_dataset.py`), `data/lamanija/retrieval_bank.jsonl`, `tests/` (`test_retrieval.py`, `test_retrieval_bank.py`, `test_evaluate_retrieval.py`, `test_evaluate_extraction.py`), `pyproject.toml`, `README.md`, `docs/DATASET.md`, `docs/DECISIONS.md`. Commits `5f61efe`, `830de17`, `3d2fa3c`, `588f2e0`, `17fdd83` and `d7eabc1`.

**Tests:** 55 unit tests (`uv run pytest`): the rules of the retriever with made-up data, the engine that computes the bank's answers with a made-up company, and the measurement. `check_dataset.py`, the smoke test and `evaluate_retrieval.py --strict` pass. The `known_gap` path was exercised only with made-up results: no question of the bank uses it yet.

**Issues:** closed #17 and #20 (#20 was opened and closed within this work, its question absorbed by the bank).
Opened #19 (replace the JSONL run log with MLflow), #21 (report retrieval and answer metrics together), #22 (interpret the question with the LLM), #23 (questions written independently of the rules), #24 (store the user's id in the catalog).

— Updated 2026-10-15, after an audit of this work: three rules misread common phrases and now narrow only for what they understand ("¿Qué viene esta semana?" was read as next week, "van a vencer" as Milhouse Van Houten, and any "con" as being with the user: "¿Qué prometió Frink con el presupuesto?" lost 2 of Frink's 5 commitments). The bank has 61 questions (three were added for those cases), the sensitivity check 19 mutations of which 18 are noticed, and there are 92 unit tests. The scripts no longer crash outside a git repository, on a dataset whose catalog does not match its expected files, or on an unknown company, and `evaluate_extraction.py` does not log a run that evaluated nothing.

— Resolved 2026-10-15: the CI now runs `check_dataset.py` and `evaluate_retrieval.py --strict --no-log` after the unit tests.

— Updated 2026-10-15: #23 (questions written independently of the rules) was merged into #21, which will run them through the retrieval and the chat together.

— Updated 2026-10-15: the words that make a person mean "shared with the user" were narrowed after measuring them: "mi", "mis" and "yo" no longer count (no effect on the bank) and "me" counts only with a verb of promising or owing in the third person ("¿Me podés decir qué prometió Frink?" lost 2 of Frink's 5 commitments). The bank has 63 questions, the sensitivity check 21 mutations of which 20 are noticed, and there are 94 unit tests.

## 2026-10-15 — Audit of the retrieval work and its fixes

**Purpose:** look for inconsistencies, holes and conflicts in the retrieval work of the same day, fix them, and leave the checks running on their own.

**Input:** the seven commits from `5f61efe` to `1c45285`: the retriever, the bank, the evaluation scripts and the run log.

**Output:** a retriever that no longer narrows on phrases it misreads; evaluation scripts that report a problem instead of crashing; a bank of 63 questions (5 added); a sensitivity check of 21 mutations, 20 noticed; 94 unit tests; and a CI that runs `check_dataset.py` and `evaluate_retrieval.py --strict --no-log`. On the bank (82 measurements) the retrieval loses no commitment and has 29% precision, against 16% for the baseline that returns everything; the 13 acceptance questions are exact.

**Logic:**
1. The audit re-derived 29 of the first 58 answers of the bank from the raw `expected` files (no difference), tried about twenty phrases and junk text on the retriever, and forced the failure of each script by hand (no git, a catalog that does not match the `expected` files, an unknown company, an empty evaluation, a corrupt log line).
2. It found four things the rules misread, each now a question of the bank: a part of a name that is an ordinary word ("van" picked Milhouse Van Houten), "viene" in "¿Qué viene esta semana?" taken as next week (and "la semana del 19" as this week), any "con" taken as "with the user" ("¿Qué prometió Frink con el presupuesto?" lost 2 of 5), and "mi", "yo" and a request with "me" taken as words about the user ("¿Me podés decir qué prometió Frink?" lost 2 of 5). The fix follows "The rule-based retrieval narrows only when it understands the phrase; otherwise it widens", refined twice.
3. The scripts: the run log writes the commit as `unknown` outside git and skips a corrupt line; `check_dataset.py` and `retrieval_bank.py` answer with a message when the catalog does not match or the company does not exist; `evaluate_extraction.py` logs nothing when nothing was evaluated; the records of the bank and of the questions are TypedDicts and the `type: ignore` comments are gone.
4. The sensitivity check follows the new rules of the retriever and found, by itself, that nothing in the bank covered the "van" fix: that is how the questions were added.
5. The CI runs the two checks ("The CI runs the dataset check and the strict retrieval evaluation").

**Important assumptions:**
- A name that is also an ordinary word ("Rosa", "Pilar") cannot be told from the person with rules; the catalog has none. It stays open (#22).
- The bank was used again to adjust the rules, so it is still not a fair exam; the questions written independently of the rules are now part of #21 (they were #23).
- The bank cannot notice a week one day too short, because no commitment of the dataset is due on a weekend; a unit test covers it.
- The verbs that make "me" mean the user ("me prometió", "me deben", "me entregó", …) are a finite list; any other verb leaves the result wider.
- The CI workflow was not parsed by a tool; its steps were run one by one in a clean clone.
- A record written to `runs/metrics.jsonl` during the audit was removed; the older records marked `*` come from uncommitted code.

**Location:** `app/answering/retrieval.py`, `scripts/` (`check_bank_sensitivity.py`, `check_dataset.py`, `evaluate_extraction.py`, `evaluate_retrieval.py`, `retrieval_bank.py`, `retrieval_bank_lamanija.py`, `run_log.py`), `data/lamanija/retrieval_bank.jsonl`, `tests/` (`test_retrieval.py`, `test_retrieval_bank.py`, `test_evaluate_retrieval.py`, `test_run_log.py`), `.github/workflows/ci.yml`. Commits `8dee384`, `d6a5381`, `13f8f98`, `154d70a`, `659d70f`, `d37212d`.

**Tests:** 94 unit tests; `check_dataset.py`, the smoke test, the Docker build and `evaluate_retrieval.py --strict` pass, also in a clean clone; the sensitivity check notices 20 of 21 mutations. Sample of the bank re-derived by hand as said above.

**Issues:** closed #23 (opened earlier today; merged into #21, which now includes its questions).
Opened #25 (add commitments due on a weekend to the dataset).
