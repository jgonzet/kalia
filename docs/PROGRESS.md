# Progress

## Next

1. #17 — Retrieve the commitments relevant to a question
2. #18 — Answer questions in a chat using the retrieved commitments
3. #16 — Evaluate the chat answers against the acceptance questions
4. #13 — Add unit tests and selected integration tests for the first full iteration

Synced at: d4d4a47

This file is filled in with each /close-feature.

Entries before the 2026-10-09 entry "Dataset loaded into SQLite" are in [PROGRESS_ARCHIVE.md](PROGRESS_ARCHIVE.md); this file keeps the most recent ones.

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

**Issues:** closed #8 (extraction half; its chat half moved to #16). Opened #15, #16, #17, #18.
