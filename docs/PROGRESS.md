# Progress

## Next

1. #38 — Let the app use the Claude API as an LLM backend, with the key reaching the container, and keep Ollama as an option
2. #37 — Run the acceptance questions by hand in the browser with the real extractor, and fix what blocks using the page
3. #35 — Check that an answer reflects a document ingested after the initial load (acceptance question 5)
4. #34 — Check that the app runs on another PC following only the README
5. #32 — Reorganize scripts/ by topic (after the functional ones above, before the final README pass)

Synced at: db9ce14

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

## 2026-10-17 — Context window of the LLM: set by the app, and the chat degrades when the prompt does not fit

**Purpose:** work on #27: with Ollama's default window (4096 tokens) a question that brings many commitments built a prompt Ollama cut without telling anyone, and the answer looked normal. Now the app sets the window and does not send a prompt that would not fit.

**Input:** `LLM_BACKEND` (`ollama` by default, `openai_compatible`, `fake`), `LLM_BASE_URL` (optional) and `LLM_CONTEXT_TOKENS` (optional), from the shell, `.env` or `.env.secrets`.

**Output:** `OllamaLLM` (`app/llm/ollama.py`), a client of Ollama's native `/api/chat` that sends `options.num_ctx`. `Settings.base_url` and `Settings.context_tokens` resolve the defaults per backend. `LLMAnswerer` takes `context_tokens` and, when the prompt is estimated not to fit, answers with `degraded=True`, the new `TOO_LONG_TEXT` and the retrieved commitments, without calling the LLM. `LLM_BACKEND=real` no longer exists (it fails at startup with the list of valid values).

**Logic:**
1. `Settings.context_tokens` is `LLM_CONTEXT_TOKENS` if set; otherwise 10240 for `ollama` and `None` for the other backends.
2. `build_llm` builds `OllamaLLM(base_url, model, context_tokens)` for `ollama`, which sends it as `num_ctx` on every request, or the previous `/v1` client for `openai_compatible`. The same value goes to `LLMAnswerer` (`create_app` and `evaluate_chat.py`), so the window the server runs with and the limit the app checks cannot differ.
3. `LLMAnswerer.answer` builds the prompt and asks `fits_context` (`app/llm/tokens.py`): estimated tokens (characters / 3) against the window minus 5%. No window means it fits. If it does not fit, the chat returns the commitments with the "too many commitments" text.
4. Why the second client and not `/v1`, and what was rejected: "Ollama gets its own client, and the context window is set by the app".

**Important assumptions:**
- 10240 is the largest window at which `qwen2.5:14b` ran entirely on the 12 GB GPU of the development machine (11.4 GB; 12288 sent 5% to the CPU; measured with `/api/ps`). Another GPU or model needs another value.
- 3 characters per token comes from 3.07 to 3.19 measured on `qwen2.5:14b` with the answering prompt; another model may tokenize Spanish differently.
- The window is shared by the prompt and the answer, and the answer's room is not reserved: only the prompt is checked.
- The default URL depends on the backend: `http://localhost:11434` for `ollama` (the Dockerfile no longer ends it in `/v1`) and `http://localhost:11434/v1` for `openai_compatible`. A `.env` with `LLM_BASE_URL` ending in `/v1` needs `LLM_BACKEND=openai_compatible`.
- With `openai_compatible` the app cannot make the server use a window, so it checks only if `LLM_CONTEXT_TOKENS` is set.
- `OllamaLLM` uses `urllib` from the standard library: no new dependency.
- `scripts/check_llm.py` asks `/api/ps` for the window of the loaded model and fails if it is not the configured one.
- `scripts/extract_dataset.py` now builds its client with `build_llm`, so it follows `LLM_BACKEND`; with `fake` it no longer calls a real model.
- The id and the source document were already out of each prompt line (commit `974c3eb`); that alone left "¿Qué prometí?" at about 3900 tokens.

**Location:** `app/llm/ollama.py`, `app/llm/tokens.py`, `app/llm/__init__.py`, `app/config.py`, `app/answering/llm_answerer.py`, `app/main.py`, `scripts/check_llm.py`, `scripts/extract_dataset.py`, `scripts/evaluate_chat.py`, `scripts/smoke_test.py`, `Dockerfile`, `.env.example`, `README.md`. Commit `0fd3ebd`.

**Tests:** 173 tests pass (`tests/test_config.py` only changed its invalid-backend value). `scripts/smoke_test.py` has a new check: with `LLM_CONTEXT_TOKENS=50` the chat is `degraded` and the LLM is not called, with a large window it is called. By hand against `qwen2.5:14b`: `scripts/check_llm.py` answers and reports a window of 10240; a chat on a database of 49 commitments answers normally and degrades with a window of 1000. Not covered: `OllamaLLM` has no test of its own, and the estimate is not checked against another model.

**Issues:** closed #27.

## 2026-10-20 — Chat bank: measuring what the LLM does with a list that is already chosen

**Purpose:** work on #16. The chat was measured with the five acceptance questions through the real retriever, counting words, so a wrong answer could not be traced to a stage and a changed person or date went unseen. Now the LLM is measured alone, on a bank of its own, with a judge that checks people and dates.

**Input:** `data/<company>/chat_bank.jsonl` (generated, 64 questions for `lamanija`), the `expected` files, the answering prompt and a real LLM (`LLM_MODEL`, `--model`).

**Output:** `answer_from_commitments` (`app/answering/llm_answerer.py`); `scripts/chat_bank.py` and `scripts/chat_bank_lamanija.py` (the bank and its conditions); `scripts/chat_judge.py` (the judge) and `scripts/check_chat_judge.py` (checks it); `scripts/evaluate_chat.py` rewritten; `app/prompts/answer_question.history.md`; a warning in `check_dataset.py`; a new CI step. First baseline, `qwen2.5:14b` with the prompt as it stands, four runs: 365, 370, 383 and 384 of 564 needed commitments said (about 66%), 34 to 38 noise commitments said, 5 to 7 lines with a wrong person or direction, at most one wrong date; the three degradation checks pass.

**Logic:**
1. A question of the bank is a condition over one commitment (`rule`) and some kinds of noise, each also a condition. `chat_bank.py` applies them to the `expected` files and writes the ids of `needed` and `noise`; the noise is a fixed pick, evenly spaced, of at most 8. It reuses the conditions, the context and the questions of the retrieval bank (`retrieval_bank.py`), so a rule lives in one place. `check_dataset.py` recomputes the file and fails if a published list changed. See "The chat bank reuses the engine and the questions of the retrieval bank, and adds the noise".
2. `evaluate_chat.py` builds the commitments from the `expected` files, gives each question's list to `answer_from_commitments` (the code the chat runs after it retrieves: prompt, context check, failure handling) and judges the answer. See "The chat is measured by handing it a list, not by running the retriever".
3. `chat_judge.py` splits the answer into lines, matches each commitment given with the line that shares at least half of its four-letter words (people and date break ties), and then checks the two people, the direction when the line has an arrow, and the due date. A line that names a person and has an arrow or a date but matches nothing is `invented`. See "The answers to the chat are judged with rules, not with a second LLM".
4. Three checks run apart from the bank: the LLM raises, comes back empty, or the prompt does not fit; the chat must return `degraded` with the fixed text and the commitments. If every answer is degraded, the script says the LLM did not answer, exits 1 and logs nothing.
5. Each run is logged with the stage `chat_bank`, apart from the old `chat` runs, whose metrics are not comparable. The reason behind each measured change of the prompt goes in the history file next to it (`app/prompts/answer_question.history.md`).

**Important assumptions:**
- Every list of the chat bank is that of the whole dataset, the held-out document included, and no question is run twice (`@before` and `@after`): 25 of the 64 questions would have run twice (101 runs instead of 64) and the LLM is handed a list either way. Whether an answer reflects a document ingested later depends on ingestion and retrieval, so it is for question 5 of the acceptance questions and #21. My choice, not discussed beforehand.
- The history of the answering prompt is a file next to it, with one row per measured change (date, commit, prompt hash, what changed and why, result), and the README points to it. A `--note` on each run was left out because `runs/` is not in git, and the README because its paragraph grew with every test and mixed history with instructions.
- The judge is a heuristic written for the answers seen so far. `invented` is an upper bound: of nine lines read, at least three were not inventions. A paraphrase with fewer than half of the words is counted as left out and as invented. The limits are in `docs/DATASET.md` ("What the bank does not cover" and "What the judge needs from the dataset"); #33 is about the count of invented.
- 64 questions: 44 from the retrieval bank (those the LLM can decide from its prompt) and 20 new. Questions that need the org chart, roles or areas are out, except "¿Qué compromisos tengo con mi jefe?", which has no noise and only measures that nothing is left out.
- The noise is up to 8 commitments split evenly between its kinds (`DEFAULT_NOISE_SIZE`); the volume questions use 0, 25 and all. For "este mes" the noise is only overdue commitments from earlier months, because "este mes" means from today to the end of the month (`docs/DATASET.md`).
- The numbers move between runs of the same prompt: 19 of 564 in four runs, most of it in a few long lists; 29 of the 64 questions gave the same count in three runs. The first run used the judge before the fix for two people who share a surname, and the noise of "este mes" was changed after the four runs.
- `check_chat_judge.py` uses a company made up inside the script, so it depends on no dataset and runs in the CI; `tests/test_chat_judge.py` covers the parts of the judge.
- The judge does not import `app/`, so what it measures does not depend on the code under test.
- `check_dataset.py` warns when the `what` of a commitment has fewer than 3 words of four letters or more. No commitment of `lamanija` does.
- The acceptance questions are no longer run by `evaluate_chat.py`; they belong to the end-to-end evaluation (#21). Question 5 (the answer after a new document) is measured nowhere today.
- A local run of the whole bank takes about 7.5 minutes on `qwen2.5:14b`. Its cost on an API is #31.

**Location:** `app/answering/llm_answerer.py`, `scripts/chat_bank.py`, `scripts/chat_bank_lamanija.py`, `scripts/chat_judge.py`, `scripts/check_chat_judge.py`, `scripts/evaluate_chat.py`, `scripts/check_dataset.py`, `data/lamanija/chat_bank.jsonl`, `app/prompts/answer_question.history.md`, `.github/workflows/ci.yml`, `README.md`, `docs/DATASET.md`. Commits `ecf2cbd`, `cd45fac`, `71a623a`, `7f17efd`.

**Tests:** 220 tests pass (173 before): `tests/test_chat_judge.py` (parts of the judge), `tests/test_chat_bank.py` (noise, records, comparison with the published file), `tests/test_answering.py` (`answer_from_commitments`), `tests/test_evaluate_chat.py` rewritten. `check_chat_judge.py` sees its 19 cases and the CI runs it; the code was broken on purpose to check that the tests and the cases notice. By hand: four runs against `qwen2.5:14b` and nine answers read against the judge's verdict, which found the fix for the shared surname.

**Issues:** closed #16. Opened while working on it, apart from this unit: #31 (tokens sent by the evaluations), #32 (reorganize `scripts/`) and #33 (the count of invented commitments).

## 2026-10-21 — The sample company loads itself when the container starts

**Purpose:** make `docker compose up` end with a chat that already has the documents and their commitments, and test it by starting the container (#36). Before, the loader ran on the host and the container's database stayed empty.

**Input:** the sample company `data/lamanija/` (inside the image: `company.json`, people, projects, `documents/` and `expected/`, not the banks or the story); the variables `SAMPLE_COMPANY` (the image sets `lamanija`; unset elsewhere), `COMMITMENTS_SOURCE` (`expected`, the default, or `extraction`) and `REFERENCE_DATE`.

**Output:** with an empty database the app loads the catalog, 24 documents and their 73 commitments; `GET /sample` and a notice at the top of the chat page that says the data is a sample and where its commitments came from; `ExpectedCommitmentsReader` (`app/extraction/expected.py`) and `prepare_sample` (`app/ingestion/sample.py`); `scripts/smoke_test_docker.py`, which the CI runs instead of a bare `docker build`; `compose.yaml` without a volume; README sections "The sample company", "Send a document of your own" and "Clean up".

**Logic:**
1. `create_app` calls `prepare_sample` when `SAMPLE_COMPANY` is set. It fails with a clear error if the folder does not exist, and loads only if the store has no catalog, so a second start on the same database loads nothing.
2. `load_dataset` takes an optional extractor. For each non-held-out document it stores the document and runs `extract_and_store` with that extractor. Without one it stores no commitments, as before, so the scripts that load first and extract later are unchanged.
3. The extractor is `ExpectedCommitmentsReader` (`expected`) or the app's `LLMExtractor` (`extraction`). The reader does not extract: it turns `expected/<id>.json` into `Commitment`s, names into catalog ids. Both sources reach the store through the same `extract_and_store`. See "The app loads a sample company at startup, with its commitments read from the `expected` files".
4. "Today" is `REFERENCE_DATE`, else the `reference_date` of the sample's `company.json`, else the system date. `prepare_sample` returns the settings with that date, so the answerer, which reads `settings.today` on every question, uses it.
5. `GET /sample` returns `{loaded, company, commitments_source, llm_model}` (the model only with `extraction`). `chat.html` asks for it on load and shows the notice; if `loaded` is false or the request fails the notice stays hidden.
6. The database lives inside the container and `docker compose down` deletes it. See "The database lives and dies with the container".
7. `smoke_test_docker.py` merges an override over `compose.yaml` (a free port, the fake LLM, no `.env`), runs `up --build -d`, checks `/sample`, that the chat has commitments, that "esta semana" falls in the week of 2026-10-12 and that compose declares no volume, and always ends with `down --rmi local --volumes`.

**Important assumptions:**
- `GET /sample` is its own endpoint and not a field of `/health`, so the page depends on it and `/health` keeps meaning "it is up". It answers 200 with `loaded: false` when there is no sample, not 404.
- The CI now starts the container instead of only building it. It has not run on GitHub yet; the script needs Compose 2.24 or later (`!override`, `!reset`), which `ubuntu-latest` should have.
- `ExpectedCommitmentsReader` implements `CommitmentExtractor` only so that `load_dataset` accepts it in place of an LLM extractor.
- A document whose extraction fails is logged and left without commitments, and the load goes on. With `extraction` and the fake backend (which extracts nothing) the 24 documents load without commitments and a warning is logged.
- `/sample` reports the `COMMITMENTS_SOURCE` configured now, not the one a database loaded by an earlier run was filled with. In Docker the two are the same because nothing is kept.
- The Docker smoke test uses the fake LLM, so it does not cover `extraction`. That path was tried by hand against Ollama (`qwen2.5:14b`, 24 documents, ready in 106 s, no failure warnings, the chat answered without degrading); the quality of what the model extracted was not measured.
- The README example of `POST /documents` says "el 16 de octubre" and not "el viernes": the model read "el viernes" of a document dated Monday 2026-10-12 as the 14th. With the date written out it gave 2026-10-16 three times out of three.
- A document sent to `POST /documents` is read against the sample's date (2026-10-12) unless `REFERENCE_DATE` is set; the README says so.
- The page notice has never been seen in a browser, only through the server (#37).
- `scripts/extract_dataset.py` was not changed: it keeps its own loop, with a line per document and its timing.
- Machines that ran the old compose keep an unused volume `kalia_kalia-db`; nothing removes it.
- `.env.secrets` was added to `.gitignore` (it was missing).
- `docs/SPEC.md` said "Persistent storage"; it now says that in V0 the database inside Docker is not kept between runs and that keeping it is for V1.

**Location:** `app/extraction/expected.py`, `app/ingestion/dataset.py`, `app/ingestion/sample.py`, `app/config.py`, `app/main.py`, `app/static/chat.html`, `Dockerfile`, `.dockerignore`, `compose.yaml`, `.env.example`, `scripts/smoke_test_docker.py`, `scripts/smoke_test.py`, `.github/workflows/ci.yml`, `README.md`.

**Tests:** 220 tests pass (no new unit tests; `tests/test_config.py` now also clears `SAMPLE_COMPANY` and `COMMITMENTS_SOURCE`). `scripts/smoke_test.py` checks that `/sample` says `loaded: false` without a sample. `scripts/smoke_test_docker.py` is new and passed locally (about 10 s with the image cached). Loading `expected` into a temporary database and measuring it with `evaluate_extraction.py` gave 73 of 73 commitments, with due date and project correct. `ExpectedCommitmentsReader`, `prepare_sample` and `GET /sample` have no unit test of their own.

**Issues:** closed #36. Opened while working on it, apart from this unit: #40 (let the chat page send a document to be extracted).

— Refined 2026-10-21 (final audit): `prepare_sample` loads when the catalog or any document of the sample is missing, not only on an empty database, because a load interrupted during a long extraction was taken as complete on the next start (`stop` and `up` reuse the container). `load_dataset` now returns `LoadResult(documents, failed)`, `GET /sample` adds `failed_documents`, and the page says how many extractions failed: with an unreachable LLM the notice used to say "extracted with your LLM" over a chat with no commitments.
