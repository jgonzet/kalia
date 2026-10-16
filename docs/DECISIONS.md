# Decisions

Real choices between alternatives, newest at the top. This file is also filled in with each /close-feature.

## The retrieval is measured on a database built from the `expected` files, not on the extracted commitments
Date: 2026-10-15
Chose: `scripts/evaluate_retrieval.py` loads the commitments of the `expected` files into a temporary database (with and without the held-out document) and runs the retriever on it, so the ids of the questions match and an extraction error cannot count against the retrieval.
Rejected: measuring on the commitments stored from a real extraction (their ids are numbered by the model and do not match the questions, and a missed commitment would be blamed on the retrieval); comparing by content on the real database (that is the end-to-end measurement, issue #21).
Why: the point of the bank is to attribute a failure to one stage.
Source: issue #17, commit 830de17.

## The rule-based retrieval narrows only when it understands the phrase; otherwise it widens
Date: 2026-10-15
Chose: a rule filters only for the phrases it handles ("esta semana", "la semana que viene", "mi jefe", "el jefe de X", a person); a phrase it does not handle ("la semana pasada", "el jefe de QA") applies no filter. A person named with no word about the user means all of their commitments, not only those shared with the user.
Rejected: reading "semana" or "jefe" as this week or my boss whatever surrounds them (the bank measured 35 commitments lost that way); one rule per phrase until every phrase is covered (it does not scale; an LLM reading the question can replace the rules later, see issue #22).
Why: the LLM that answers can discard extra commitments but cannot recover the ones the retrieval dropped.
Source: issue #17.
Refined 2026-10-15: only "esta semana", "en la semana", "durante la semana", "semana actual" and "la semana que viene" (and its variants) filter by date; any other mention of a week applies none. Parts of a name that are also ordinary words ("van") count only inside the full name, and "con" speaks of the user only right before a person.

## The retrieval has its own bank of questions, apart from the acceptance questions and from the chat bank
Date: 2026-10-15
Chose: `data/<company>/retrieval_bank.jsonl`, with questions grouped by category (the angle they probe) and measured by `scripts/evaluate_retrieval.py`. `questions.jsonl` stays as the V0 acceptance questions; the chat gets its own bank and script (issue #16), fed with controlled input so the LLM is measured apart from the retrieval.
Rejected: a `v2` of `questions.jsonl` (it mixes the "done" criterion with a stress test; the combined question of #20 is one question of the bank); one bank for retrieval and chat (a wrong answer could not be traced to a stage, and the chat needs inputs the retrieval would not produce).
Source: issues #17, #16 and #20.
Refined 2026-10-15: a question may declare a `known_gap` (an accepted loss, with its issue); it is a status and not part of the question, so it can change without a new version. `--strict` fails only on losses without one.

## The answers of the retrieval bank are computed from conditions, not written by hand or by the retriever
Date: 2026-10-15
Chose: each question is a condition over one commitment (`scripts/retrieval_bank_<company>.py`); `scripts/retrieval_bank.py` applies it to the `expected` files without importing `app/`, stores the condition's text as `rule`, and `check_dataset.py` fails if a published answer changes.
Rejected: answers copied from the retriever's output (circular: the test would approve whatever the code does); answers written by hand (73 commitments and 56 questions invite mistakes that cannot be re-checked when the dataset grows).
Why: the answers stay checkable (the rule is in the file) and a changed dataset cannot silently change a published question.
Source: issue #17.

## Evaluation metrics are logged to a JSONL file, not to MLflow yet
Date: 2026-10-15
Chose: each evaluation run appends one line to `runs/metrics.jsonl` (git-ignored) with the commit, flat `params` (retriever or model, prompt hash, dataset, questions version) and flat `metrics`, through `scripts/run_log.py`. The shape is the one MLflow logs, so the history can be moved there.
Rejected: MLflow now (a large dependency and a server for a history of one or two runs; replacing the file is issue #19); comparing runs by hand from separate JSON files (what `evaluate_extraction.py` did).
Source: issue #17.

## Retrieval is one replaceable function; the first version is rules over the question text
Date: 2026-10-15
Chose: `Retriever.retrieve(question) -> list[Commitment]` in `app/answering` is the only thing the chat will know. `RuleRetriever` finds a person, "jefe"/"jefa" (an alias of the person the user reports to) and "semana", and returns every commitment when it finds none. "Involucr..." in the question means all the commitments of a person, otherwise only those shared with the user.
Rejected: giving the LLM tools to query the database (small local models handle them badly, it is slower and the retrieved set cannot be checked; agents are out of V0); an LLM that reads the question to pick filters (one more call that can fail; it can replace the rules later without touching the chat).
Why: the rules cover the acceptance questions and are checked without an LLM; a surname shared by two people picks no one.
Source: issue #17.
Refined 2026-10-15: a person named with no word about the user means any commitment of theirs, not only those shared with the user (see the entry on rules that narrow only when they understand the phrase).

## The extraction evaluation is a standalone script, not part of the app
Date: 2026-10-09
Chose: `scripts/evaluate_extraction.py` holds the logic and reads the database and `data/<company>/expected/`. It pairs commitments inside each document by people and due date (then people only), and sums counts, not percentages, for the totals.
Rejected: a module in `app/` with a thin script (the answer key exists only for synthetic datasets, so the app has no use for it); an endpoint or a step of the pipeline (real documents have nothing to compare with); pairing by commitment id (the extraction numbers commitments in the order the model lists them).
Source: issue #8 (extraction half).

## Commitments store catalog ids, not names
Date: 2026-10-09
Chose: `Commitment` holds `who_id`, `to_whom_id` and `project_id`. The model still answers with catalog names; `parse` checks them and translates each to its id.
Rejected: storing names (renaming someone in the catalog would break every stored link); storing id and name (two sources of truth).
Why: decided before any real commitment was stored, so no data had to be migrated.
Source: issue #14, commit 80b86a7.

## Extraction runs after the document is stored; if it fails, the document stays
Date: 2026-10-09
Chose: `ingest_document` only stores; `extract_and_store` is a separate step that `POST /documents` runs afterwards. A failed LLM call or a missing catalog is logged, nothing is changed, and the response says `extracted: false`.
Rejected: one all-or-nothing step (an LLM outage would lose the document).
Source: issue #14, commit 3131d62.

## Only the real backend extracts on ingestion; `create_app` takes an optional extractor
Date: 2026-10-09
Chose: `create_app(..., extractor=None)`: without one, `LLM_BACKEND=real` builds an `LLMExtractor` and `fake` extracts nothing (`extracted: false`). Tests pass a stub extractor.
Rejected: extracting with the fake LLM (it returns fixed text, so the table would fill with noise or empty lists).
Source: issue #14, commit 3131d62.

## Saving a document's commitments replaces everything stored for that document
Date: 2026-10-09
Chose: `CommitmentStore.save_document_commitments(document_id, commitments)` deletes the owner's rows for that document and inserts the given list; an empty list clears the document. Re-extracting a document is therefore always safe.
Rejected: upsert by commitment id (a re-extraction that yields fewer commitments would leave stale rows, since ids are `<doc id>-cN`); append-only (duplicates on every re-run).
Source: issue #11, commit 943698d.

## The manual Claude Code backend works on self-contained request files, outside the repo
Date: 2026-10-09
Chose: `scripts/manual_extraction.py export` writes `requests/batch-NN.md` with one full prompt per document (instructions, contract, catalog, text); the owner has an external Claude session, opened in an empty folder, answer `{"<document id>": [...]}`; `import` validates that file. `requests/` and `responses/` are git-ignored.
Rejected: a session inside the repo with a short request (it could read the `expected` files); one file with all 24 prompts (too long to hand over at once).
Why: an LLM only sees what travels in the prompt, so a self-contained request is the same input a paid API would get.
Source: issue #12, commit 3495401.

## The response contract is a list of five fields; ids are assigned by the app
Date: 2026-10-09
Chose: for one document the model answers a JSON list of `{who, to_whom, what, due, project}`; names must be in the catalog. The app assigns the commitment ids. Items that break the contract are reported and left out, never dropped silently.
Rejected: also asking for `due_text` (diagnosis only, the app does not use it) and for ids (they could collide or copy the `expected` ones); failing the whole document on one bad item.
Source: issue #12, commit 3495401; the prompt is `app/prompts/extract_commitments.md`.

## Extraction is three pieces: build the prompt, call the model, parse the answer
Date: 2026-10-09
Chose: `build_prompt` and `parse_response` are shared functions; `LLMExtractor` chains them around `LLMClient.complete`. The manual backend uses only the first and the last, with the owner as the middle step.
Rejected: a fake `LLMClient` that writes the request and raises "answer pending" (an exception standing for something that is not a failure, which the extractor would have to understand).
Source: issue #12, commit 3495401.

## Storage settings live in `compose.yaml`, not in the Dockerfile
Date: 2026-10-09
Chose: `DB_PATH` and the volume mount are set in `compose.yaml`; the Dockerfile only creates a writable `/var/lib/kalia`. Changing the database engine touches compose, not the image.
Rejected: keeping `DB_PATH=/db/kalia.db` in the Dockerfile (the image would carry a SQLite-specific path and change with every storage swap).
Source: issue #10, commit 8c43f03.

## One ingestion path for every source; the dataset is an adapter
Date: 2026-10-09
Chose: `ingest_document` in `app/ingestion` is the only way a document enters storage; `POST /documents` calls it, and the dataset loader (`DatasetSource`, `DocumentSource` Protocol) feeds it. Held-out documents are ingested afterwards through the endpoint.
Rejected: a standalone loader script that writes to the database (a real incoming mail would need a second path, and the script logic would have to be refactored into the app later).
Source: issue #10, commit 8c43f03.

## The generator prompt is a versioned file; new versions go above the old ones
Date: 2026-10-09
Chose: `data/generation/session_prompt.md` holds the prompt given to the generating session, with its version in the header. A new version is added above the previous ones, which stay in the file.
Rejected: one file per version (comparing needs two files open); editing the prompt in place (the previous version is lost, which happened once with v0).
Source: issue #7, commit b45145c.

## Review checks the answer key against the text, not the text against a clean ideal
Date: 2026-10-09
Chose: reviewing a generated document means checking that its `expected` file is true of the text (each commitment present with its `due_text`, nothing else promised, no contradiction with `story.md`). Ambiguous phrases the generator leaves in ("lo miro", "va a estar") stay as material for the evaluation in #8.
Rejected: rewriting texts until they are free of ambiguity (it tunes the test to the extractor; real documents are never that clean).
Source: issue #7, commit b45145c.

## One Claude Code session generates the documents, another reviews and accepts them
Date: 2026-10-09
Chose: the generating session writes the texts, runs `check_dataset.py --allow-pending` and reports; it does not stamp or commit. The reviewing session reads every text against its `expected` file and runs `--stamp`.
Rejected: generating and reviewing in one session (nobody checks the writer's work); one subagent per batch (each starts cold and re-reads all the context, with less consistency between batches).
Source: issue #7, commit b45145c; replaces the external chatbot of `docs/PLAN.md` section 13.

## The synthetic documents are committed to the repo
Date: 2026-10-09
Chose: `data/<company>/documents/` is versioned like the rest of the dataset, so anyone who clones the repo can test the app with the same input.
Rejected: keeping the documents out of git (the `text_sha256` in each `expected` file would point to texts nobody else has, and `check_dataset.py` would have nothing to check outside this machine).
Why: the data is synthetic. This does not cover real or confidential data, which is not decided yet.
Source: issue #6.

## One story file per company, pasted whole into every generation batch
Date: 2026-10-07
Chose: `data/<company>/story.md` lists, per project, a situation and dated facts that no document may contradict. Every batch prompt includes it whole, and new documents add their facts to it before their `expected` files are designed.
Rejected: one story file per project (every batch would need a selection of parts); facts with ids referenced from each `expected` file (ids to maintain and prompts to assemble by hand).
Why: about 60 lines are cheap to paste, and a single file is the one place where consistency between documents is kept.
Source: issue #5, commit 8adbaa5; the rule goes into `data/generation/base.md` in #6.
Refined 2026-10-07: `story.md` has 43 lines today, not about 60.

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
Refined 2026-10-07: the layout is now described in `docs/DATASET.md`.

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
Refined 2026-10-09: the header syntax (a `---` block with `key: value` lines) is defined in `docs/DATASET.md`.

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
