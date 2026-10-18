# Progress

## Next

1. #27 — Stop the LLM from silently losing part of the prompt when the retrieval brings many commitments
2. #16 — Evaluate the chat answers against the acceptance questions
3. #21 — Report retrieval and answer metrics together in the chat evaluation
4. #13 — Add unit tests and selected integration tests for the first full iteration
5. #30 — Make "this week" end on Friday, as the working week does

Synced at: f96c79a

This file is filled in with each /close-feature.

Entries before the 2026-10-15 entry "Rule-based retrieval and the retrieval bank" are in [PROGRESS_ARCHIVE.md](PROGRESS_ARCHIVE.md); this file keeps the most recent ones.

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

## 2026-10-16 — Chat that answers from the retrieved commitments

**Purpose:** close the flow documents -> grounded answers: a question in a chat is answered by an LLM using only the commitments the retriever brings, and the quality of those answers can be measured.

**Input:** a question of 1 to 1000 characters sent to `POST /chat`; a database with the catalog, the extracted commitments and the reference date of the dataset; `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` and, optionally, `REFERENCE_DATE`.

**Output:** a page at `GET /`; `POST /chat` answers `{answer, degraded, commitments}` (the commitments with names, not ids); the table `dataset_meta`; and `scripts/evaluate_chat.py`, which measures the answers.

**Logic:**
1. The rule retriever (see "Retrieval is one replaceable function...") brings the candidate commitments. `ordering.py` groups them by project, orders them and labels each one atrasado, pendiente or sin fecha ("The code orders and labels the commitments...").
2. `prompt.py` fills `app/prompts/answer_question.md`, written in Spanish ("The model is spoken to in Spanish..."), with the user's name, "today", the grouped list and the question; each line has only who -> to whom, what, the date and the state. The prompt says what a commitment is, who the user is, that the list may have extras and extraction mistakes, to keep what answers the question, and has one worked example. The catalog is read once per question and handed to the retriever.
3. `LLMAnswerer` sends it to the LLM. If the call fails or comes back empty, the response is marked `degraded` and carries the retrieved commitments ("`Answerer.answer` returns an `Answer`...").
4. "Today" is taken on every question from `REFERENCE_DATE`, the date stored by the loader, or the system date ("Today is `REFERENCE_DATE`, else...").
5. `evaluate_chat.py` runs the acceptance questions through all this on a copy of a database, pairs the needed commitments by content (not by id) and counts how many appear in each answer.
Also, the SQLite store now closes its connection after every operation (it only committed before).

**Important assumptions:**
- Measured on 2026-10-16 with `qwen2.5:14b`, the answers contain 84 and 91 of about 140 needed commitments in two runs (about 62%) with the final prompt, while the retriever brought almost exactly what each question needs. The way there, same questions: English prompt 72 to 81; Spanish with `vencido` 71 and 67; Spanish with `atrasado` 82 and 85; without the ids on the lines 91 and 84; temperature 0 changed nothing. Pasted by hand into Claude, an early prompt gave 15 of 15 on "my boss". So the limit today is the local model, not the design; the model is configuration (`LLM_MODEL`).
- "The answer contains a commitment" is a heuristic (half of the words of its `what`); it does not notice a changed person or date. The numbers move by about five of 140 between runs of the same prompt, because the LLM runs at the server's temperature.
- The question is trimmed and must have 1 to 1000 characters (`MAX_QUESTION_CHARS`): an empty question would bring every commitment.
- The worked example in the prompt uses the real user's name and an invented person ("Zeta"), so it does not contradict the question when the user changes.
- The lines of the prompt leave out the commitment id and the source document: the model must not show them and they took about 40% of the tokens. A question that brings all 72 commitments is now 3903 tokens, under Ollama's 4096 window with little room (#27 stays open).
- `atrasado` only says the date passed; V0 has no status.
- A database loaded before this has no stored reference date, so it uses the system date until `load_dataset.py` runs again. — Resolved 2026-10-17: the stored date was removed; "today" is `REFERENCE_DATE` or the system date ("Today is `REFERENCE_DATE`, else the system date").
- The page was not tried in a browser; only the server side is tested. It shows the text as the model writes it, so Markdown marks appear raw, and it lists the commitments only when the response is `degraded`.
- The extraction prompt is still in English and was not touched (see the decision on Spanish). The text of the commitments goes into the prompt as it is (#28).
- The answering prompt accepts another file (`--prompt` of the script) so versions can be compared without touching the app's.

**Location:** `app/answering/` (`__init__.py`, `ordering.py`, `prompt.py`, `llm_answerer.py`), `app/prompts/answer_question.md`, `app/static/chat.html`, `app/main.py`, `app/config.py` (`resolve_today`), `app/storage/` and `app/ingestion/dataset.py` (reference date), `scripts/evaluate_chat.py`, `scripts/evaluate_extraction.py` (`pair_expected`), `scripts/smoke_test.py`. Commits `ed4a8df`, `8f0dc45`, `94fc9e5`, `053a566`, `3976df3`, `fee57a4`, `974c3eb`.

**Tests:** 181 tests in the repo: `tests/test_answering.py` (ordering, state, prompt, answerer, endpoint, limits, "today"), `tests/test_evaluate_chat.py` (heuristic, pairing, a full evaluation with stub LLMs, the database is not written), `tests/test_reference_date.py`, `tests/test_sqlite_store.py` (connections are closed). Several of them were checked by breaking the code on purpose. The smoke test calls the running service for `/chat`. The numbers above come from `scripts/evaluate_chat.py` against the real model.

**Issues:** closed #18. Opened #26 (audit the extractor in depth), #27 (the silent cut of long prompts), #28 (instructions hidden in documents), #29 (the chat's "today" in databases loaded before the reference date was stored). #16 and #21 stay open: the script is a first, heuristic measurement.

## 2026-10-17 — Extraction of a whole dataset with the real LLM, and the first measurement of local models

**Purpose:** be able to measure a local model on the extraction without feeding the documents one by one to `POST /documents`, and know how far the local models are from the manual Claude flow.

**Input:** a company dataset (`data/<company>/`) or a database that already has its documents and catalog; `LLM_BASE_URL`, `LLM_API_KEY` and `--model` (default `LLM_MODEL`).

**Output:** `scripts/extract_dataset.py`, which fills in a database with the commitments of every document and prints one line per document (commitments, seconds) and the documents whose LLM call failed (exit code 1). `scripts/evaluate_extraction.py` then measures it as before.

**Logic:**
1. New database: loads the catalog and the documents of the dataset (held-out ones excluded), and refuses to write into a file that exists so runs do not mix. With `--existing` it takes the documents already in the database (it needs the catalog) and replaces their commitments.
2. For each stored document it calls `extract_and_store` with an `LLMExtractor`: the same code `POST /documents` runs. The script adds the loop and nothing else.

**Important assumptions:**
- Measured on 2026-10-17 on `lamanija` (73 expected commitments, English prompt, server temperature). Reference is the manual Claude flow: 70 matched, recall 96%, precision 97%, due 68/70. `qwen2.5:14b`, two runs: 37 and 39 matched (recall 51% and 53%), precision 92% and 80%, due 21/37 and 22/39. `llama3.1` 8B: 37 matched, precision 59%. `llama3.2` 3B: 17 matched, due 3/17. The three models failed in the same ways: whole documents with nothing extracted, short names ("Burns") that are not in the catalog and so are discarded, relative dates wrong more than half of the time. The causes were not investigated (the 4096-token cut of Ollama, #27, was not ruled out); that belongs to #26.
- The runs are in `runs/metrics.jsonl` under the model names `<model>-en`; the databases and JSON are in `runs/` (git-ignored).
- The English prompt was kept on purpose; translating it is noted in #26.
- Only Ollama was tried; another OpenAI-compatible endpoint should work by changing the variables.
- No tests: it is a development tool, by decision of the owner.

**Location:** `scripts/extract_dataset.py`, `README.md` ("Evaluate the extraction", "Known limitations"). Commit `23cb9e4`.

**Tests:** none for the script. Tried by hand in the three cases (new database, `--existing` on a loaded database, a dead endpoint, a missing database, a company with an existing file).

**Issues:** closed #15.

## 2026-10-17 — "Today" without a date stored in the database

**Purpose:** fix #29: a database loaded before the reference date was stored answered with the system date without any sign, and the stored date was a second place for "today" that could be missing. Now there is one: `REFERENCE_DATE`, else the system date.

**Input:** `REFERENCE_DATE` (`YYYY-MM-DD`, optional) from the shell, `.env` or `.env.secrets`; the project's `.env` was created with `REFERENCE_DATE=2026-10-12`, the `reference_date` of `data/lamanija/company.json`.

**Output:** `Settings.today` is `REFERENCE_DATE` or `date.today()`, read on every question in `POST /chat`. The table `dataset_meta`, `ReferenceDateStore` and `Settings.resolve_today` are gone, and `load_dataset` no longer saves a date. The Docker image carries `app/` and `scripts/check_llm.py` only.

**Logic:**
1. `Settings.from_env()` first calls `load_env_files()`, which puts the `KEY=value` lines of `.env` and `.env.secrets` (project root) into `os.environ` without replacing variables already set, so `uv run` scripts see the same file Docker Compose passes to the container.
2. `current_answerer()` in `app/main.py` asks `settings.today` on each question, so a server running past midnight does not keep the old day.
3. The evaluation scripts do not use this: they read `reference_date` from `company.json` to compute the expected answers, so the dataset's date and `REFERENCE_DATE` are two copies of the same value that nothing keeps equal (noted in `.env`/`.env.example`).
Decisions recorded: "Today is `REFERENCE_DATE`, else the system date" (replaces the 2026-10-16 one, now in `DECISIONS_ARCHIVE.md`), "Env files are loaded by the app's own code" and "The Docker image carries only `scripts/check_llm.py`".

**Important assumptions:**
- Variables already set in the shell win over the files; missing files are skipped; a value may be wrapped in single or double quotes and lines without `=` are ignored.
- The tests set `ENV_FILES` to `()` so they do not read a developer's real `.env`.
- Databases that had `dataset_meta` (four in `runs/`) had the table dropped by hand; `kalia.db` and the Docker volume never had it. A leftover table in another file is harmless: nothing reads it.
- `.env.secrets` is read by the scripts but not passed by `compose.yaml` to the container (listed in the README's known limitations; Ollama needs no key).
- "This week" is still seven days from today; Monday to Friday is #30.

**Location:** `app/config.py`, `app/main.py`, `app/ingestion/dataset.py`, `app/storage/__init__.py`, `app/storage/sqlite.py`, `Dockerfile`, `.env.example`, `README.md`, `docs/SPEC.md` (the line on the reference date). Commits `a6149b5` and `f96c79a`.

**Tests:** 173 tests pass. `tests/test_reference_date.py` was removed with the code it tested; `tests/test_config.py` covers the system-date fallback and the env files (the environment wins over the file); `tests/test_answering.py` checks the chat uses `REFERENCE_DATE`. By hand: the rebuilt image gives 2026-10-12 with the `.env` and the system date without it, and `docker compose run --rm app python scripts/check_llm.py` still answers.

**Issues:** closed #29. Opened #30 (make "this week" end on Friday).
