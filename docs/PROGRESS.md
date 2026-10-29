# Progress

## Next

1. #34 — Check that the app runs on another PC following only the README
2. #32 — Reorganize scripts/ by topic (after the functional ones above, before the final README pass)

Synced at: a23ef56

This file is filled in with each /close-feature.

Older entries are in [PROGRESS_ARCHIVE.md](PROGRESS_ARCHIVE.md); both files are ordered by date.

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

— Resolved 2026-10-21: the first CI run on GitHub passed, with the container smoke test (the version of Compose on `ubuntu-latest` accepts `!override` and `!reset`).

— Refined 2026-10-21: the timeout of each LLM call is 60 seconds (it was 120) in both clients, and `load_dataset` stops trying after `MAX_CONSECUTIVE_FAILURES` (3) extractions in a row fail, counting the rest as failed: with an unreachable LLM that does not answer, the start waited a timeout per document (24 times). With `openai_compatible` the SDK still retries each call twice, so a call that times out can wait up to three timeouts. A slow machine can need more than 60 seconds for one call (a cold model, a long answer); there is no setting for it yet. `tests/test_sample.py` adds 14 tests (234 pass): the reader of precomputed commitments, `load_dataset` with failures, `prepare_sample` (complete, interrupted and failed loads; "today") and `GET /sample`; broken on purpose (the old check of an empty database, no stop after failures, `who` and `to_whom` swapped), three of them fail.

— Resolved 2026-10-21: `LLM_TIMEOUT_SECONDS` sets it now, per LLM or per task, and the default is 120 s again, from the measurements in `docs/MEASUREMENTS.md`.

## 2026-10-21 — The Claude API as an LLM backend, one LLM per task, and a log of measurements

**Purpose:** let a person with an API key and no Ollama run the app, keep Ollama as the default, and let each task that calls an LLM (extracting commitments, answering the chat) use a different one (#38). Trying the chat with a local model also showed that nobody knew how long it takes, so the time and the tokens are now measured and kept.

**Input:** `LLM_BACKEND` also accepts `anthropic`. An LLM is described by `BACKEND`, `MODEL`, `BASE_URL`, `API_KEY`, `CONTEXT_TOKENS` and `TIMEOUT_SECONDS`, with the prefix `LLM_` (the default) or `EXTRACTOR_LLM_` / `ANSWERER_LLM_` (one task). Keys go in `.env.secrets`, the rest in `.env`.

**Output:** `AnthropicLLM` (`app/llm/anthropic.py`); `LLMSettings` and `Settings.llm_for(task)` (`app/config.py`); `build_llm` takes the settings of one task; `create_app` builds one client per task; `/health` answers `llm_backends` (a backend per task); a timeout per attempt that is configurable (120 s by default); `compose.yaml` passes `.env.secrets` to the container; `.env.example` and `.env.secrets.example` list every variable; a warning at startup when the sample is extracted through a backend that may be paid; `scripts/measure_latency.py` and `docs/MEASUREMENTS.md`; README sections "Use the Claude API instead of Ollama" and "What a paid API costs".

**Logic:**
1. `Settings.from_env` reads the default LLM (`LLM_*`) and, for each task in `LLM_TASKS`, its own block (`<TASK>_LLM_*`). A block with no variable set is not there. The default falls back to Ollama for what is missing; a task block with any variable takes everything from itself and the app refuses to start naming what it lacks (backend always; model and key for `anthropic` and `openai_compatible`). See "Each task that calls an LLM has its own LLM settings, and a task with any of its own inherits nothing".
2. `llm_for(task)` returns the task's `LLMSettings` or the default one, with the defaults of the backend applied (address, the Ollama window of 10240, the timeout).
3. `create_app` builds `{task: build_llm(settings.llm_for(task))}`: two clients even when both are the same. A `llm` passed in code serves both. The extractor exists unless its backend is `fake`; the chat takes the window of the answerer's settings; `/sample` names the extractor's model.
4. `build_llm` picks the client of the backend. `AnthropicLLM.complete` sends one message with `max_tokens` 8192, joins the text blocks and raises `LLMError` if the API fails, the answer was cut at the limit, Claude declined, or the text is empty. See "Claude has its own client with the Anthropic SDK, not the OpenAI-compatible one".
5. The keys: the scripts on the host read `.env.secrets` with `load_env_files`; Docker Compose passes it to the container as environment variables and `.dockerignore` keeps it out of the image.
6. `extract_dataset.py` uses the extractor's settings and `evaluate_chat.py` the answerer's; `--model` replaces only the model. `check_llm.py` asks each distinct LLM once.
7. `measure_latency.py` sends the questions through `POST /chat` with a wrapper that times the LLM, reads the tokens Ollama reports (`OllamaLLM.last_stats`), samples `nvidia-smi` and prints a report in the format of `docs/MEASUREMENTS.md`. See "The length of the chat's answer is not limited, in the prompt or in the client".

**Important assumptions:**
- The client of Claude takes no base URL: the image sets `LLM_BASE_URL` to the host's Ollama, so inside Docker the variable always has a value and using it would send the Claude key to that address. A proxy for Claude is not possible.
- `max_tokens` is 8192. It was not tried with a real Claude: the largest extraction of the sample is about 1000 tokens, but models that think before answering spend part of the limit on it.
- A variable named like an LLM variable that the app does not read (`EXTRATOR_LLM_BACKEND`, `EXTRACTOR_LLM_MODLE`) stops the start, so a typo is not ignored. A variable of another shape (`MY_LLM_THING`) is left alone. This was my choice alone.
- `/health` changed its answer from `llm_backend` to `llm_backends`; only the smoke test read it.
- The timeout is per attempt, and the clients of `openai_compatible` and `anthropic` retry a failed call twice, so one call can take about three times it. 120 s comes from the measurements (the longest answer took 72 s).
- In Docker, a task that uses Ollama needs its own `..._BASE_URL`, because it does not inherit the image's `LLM_BASE_URL` (written in `.env.example`).
- `openai_compatible` now needs `LLM_MODEL` and `LLM_API_KEY` (before, it took `qwen2.5:14b` and `ollama`); whoever used it against Ollama's `/v1` has to set them.
- `anthropic` and `openai_compatible` were not tried with a real key, which is what #38 asks as done. Only `anthropic` was tried with the real SDK against a local server that imitates the API. There is no counting of tokens or money (#42); the cost estimate of the README is rough and not measured.
- No check of the context window with `anthropic` and `openai_compatible` unless `LLM_CONTEXT_TOKENS` is set; a prompt the API rejects comes back as a failed call (`degraded`).
- The warning at startup covers any backend that is not `ollama` or `fake`, and says "if that is a paid API", because `openai_compatible` can be a local server.
- On 2026-10-21 seven chat requests to the local Ollama did not finish in 1 minute and another not in 2, with the laptop on battery. The cause is open and the hypothesis (a limit on the power given to the GPU) is not confirmed; the last entry of `docs/MEASUREMENTS.md` says how to test it.
- `app.state.llm` became `app.state.llms`; nothing read it.
- The Docker image was not rebuilt with the new dependency (`docker compose config` and `uv lock --check` pass).

**Location:** `app/llm/anthropic.py`, `app/llm/__init__.py`, `app/llm/ollama.py`, `app/llm/openai_compatible.py`, `app/config.py`, `app/main.py`, `app/ingestion/sample.py`, `compose.yaml`, `.dockerignore`, `.env.example`, `.env.secrets.example`, `scripts/measure_latency.py`, `scripts/check_llm.py`, `scripts/evaluate_chat.py`, `scripts/extract_dataset.py`, `scripts/smoke_test.py`, `pyproject.toml`, `uv.lock`, `docs/MEASUREMENTS.md`, `README.md`.

**Tests:** 234 tests pass, none new: the rules of `app/config.py`, `AnthropicLLM` and `measure_latency.py` have no unit test of their own. Tried by hand: 15 configurations (empty, only the Docker address, missing model or key, incomplete task, typos, invalid numbers); `AnthropicLLM` with the real SDK against a local server (a normal answer, cut, declined, empty, 401, 429, 500; the key never appears in a message; the SDK makes three requests for one failing call); the timeout reaches the client (a server that answers in 3 s, cut at 1 s with `LLM_TIMEOUT_SECONDS=1`, answered with 6); Compose passes a variable of a dummy `.env.secrets` to the container; with the real Ollama, `check_llm.py` passes (window 10240), a document was extracted and the chat answered; `scripts/smoke_test.py` passes. Not run: a real Claude or OpenAI key, `docker compose up` with the new dependency.

**Issues:** closed #38 (its check with a real key moved to #43). Opened while working on it: #41 (let the Docker container keep the stored commitments between runs), #42 (measure and show what the app spends on LLM calls), #43 (try the backends with a real API key) and #44 (unit tests for the configuration per task, the Claude client and the latency script).

— Resolved 2026-10-21: the rules of `app/config.py`, `AnthropicLLM` and `measure_latency.py` now have unit tests (#44).

## 2026-10-21 — Unit tests for the LLM settings per task, the Claude client and the latency script

**Purpose:** keep from breaking, without anything failing, three pieces added with #38 that had only been tried by hand with scripts that were not kept (#44). The rule that a task with a variable of its own inherits nothing is the one that protects a key from reaching another provider.

**Input:** none; the tests run without a real key, Ollama, a GPU or the network.

**Output:** 37 tests in three files, no change in `app/` or `scripts/`: `tests/test_llm_settings.py` (17), `tests/test_llm_clients.py` (5) and `tests/test_measure_latency.py` (10).

**Logic:**
1. `test_llm_settings.py` clears every LLM variable from the environment and checks `Settings.from_env` and `llm_for`: the defaults of Ollama, the task that inherits nothing from the default, one table of incomplete configurations (each must name the variable to set), the invalid numbers, the misspelled variable names and the settings of `anthropic` without an address and with the key out of the `repr`.
2. `test_llm_clients.py` starts an HTTP server in a thread that imitates `POST /v1/messages` and points the SDK at it with `ANTHROPIC_BASE_URL`. It checks a normal answer (and the request sent), one table of answers that must become `LLMError` (cut at `max_tokens`, declined, empty, 401, 429, 500, none showing the key), and that `timeout_seconds` reaches the three clients.
3. `test_measure_latency.py` imports the script and uses an LLM that reports tokens like Ollama does, with `nvidia-smi` and the machine description replaced. It checks the percentile, the fingerprint of the questions, where the questions come from, the timer around the LLM, `measure` (also with a failing LLM) and the report, which it reads for the numbers it must show.

**Important assumptions:**
- The fake server sends `x-should-retry: false`, so the SDK does not retry a 429 or a 500 after a pause. The suite takes about 10 s in all.
- The SDK installed here (2.1.0) sends the key as `Authorization: Bearer`, not `x-api-key`; the test checks that header and would need a change if the SDK changes it.
- The timeout test reads private attributes (`OllamaLLM._timeout_seconds`, `_client.timeout` of the other two): there is no public way to read it.
- First there were 57 tests; cases that checked the same thing were joined in tables to reach 37. The unreachable server and "the report lists only the slowest five" were left out.
- `main` of the latency script is tested with `--ask`, so it does not depend on the chat bank of a company; the bank questions are checked in `read_questions` with `data/lamanija`.
- Not covered: the real `nvidia-smi` reading and `machine_description`.

**Location:** `tests/test_llm_settings.py`, `tests/test_llm_clients.py`, `tests/test_measure_latency.py`. Commits `5998494`, `5b3c862`, `54a58d9`.

**Tests:** 271 tests pass (234 before). The code was broken on purpose in four places and at least one test failed each time: the check of "no variable set" in `_read_llm`, the timeout that `build_llm` hands to `AnthropicLLM`, the check of a refusal in `AnthropicLLM.complete` and the rank of `percentile`.

**Issues:** closed #44.

## 2026-10-22 — First manual run of the chat in a browser with the real extractor

**Purpose:** see the complete flow working by hand for the first time (documents, extraction by the real LLM, chat in a browser), write down what it does as the baseline of V0 and fix what got in the way of reading the page (#37).

**Input:** the app started with `docker compose up --build`, `COMMITMENTS_SOURCE=extraction` and `qwen2.5:14b` through Ollama; the acceptance questions 1 to 4 of `docs/SPEC.md`, asked by hand in the page.

**Output:** the headings (`## Project`) of an answer show as titles in `app/static/chat.html`; the baseline, written as the closing comment of #37.

**Logic:**
1. The sample's 24 documents were extracted at startup with no failed document; some items were left out for a person outside the catalog ("Smithers") or an empty or `'null'` `to_whom` (documents 0015, 0019, 0020, 0023).
2. The notice at the top of the page shows, reads well and says the data is a sample and that the commitments were extracted with `qwen2.5:14b`.
3. Questions 1 to 4 each got an answer built from commitments of the documents. The answer's `##` lines appeared raw; `renderAnswer` in `chat.html` now shows them as `<h3>` and every other line as a paragraph, setting only `textContent`.
4. A new format of the answer (due date first, with the weekday computed by the code) was tried and measured against the current prompt, three runs of `scripts/evaluate_chat.py` each, and was not adopted (see below).

**Important assumptions:**
- Only the headings are rendered, not the rest of Markdown (`**` still appears raw): the page shows one kind of mark that the prompt itself asks for, and no library was added. A full renderer, if wanted, is a separate step.
- The comparison of the new format (2026-10-22, `qwen2.5:14b`): needed commitments said, of 564, 368, 364 and 393 with the current prompt against 325, 336 and 330 with the new one; wrong person or direction 4, 8 and 7 against 1, 0 and 0; wrong due date 1, 0 and 0 against 7, 8 and 9. The code and prompt were put back; the numbers are in #45 and were not added to `answer_question.history.md`, as no prompt was replaced.
- What the run found in the answers: the extractor resolves relative dates wrongly (commented in #26: "el viernes de la semana que viene" gave 2026-10-13 where `expected` has 2026-10-16), and "¿quién es el jefe de mi jefe?" cannot be answered because the prompt has no org chart (#46).
- An evaluation run of about 8 minutes hung for an hour with the GPU at 0% while the laptop was on battery; it was killed and repeated. The cause is not known (see the entry of 2026-10-21 about the battery).

**Location:** `app/static/chat.html`, `README.md` ("Known limitations": what the page renders, the missing org chart), `.gitignore` (`/.vscode/`).

**Tests:** none new; 271 tests pass. The page was used by hand in a browser: notice, questions 1 to 4, and a second look at the answers after the change of headings.

**Issues:** closed #37. Opened #45 (date first in each line of the answer, with the weekday) and #46 (decide whether the chat prompt includes the org chart); the relative dates of the extractor went as a comment on #26.

## 2026-10-29 — Ingestion check: where a late document is lost or added, stage by stage

**Purpose:** work on #35. Acceptance question 5 (after a new document is ingested, does a related question return an answer that reflects it?) was measured nowhere: the chat bank hands the LLM a list, so "before" and "after" are two lists to it. Now the whole path is run and each stage is measured apart, so a loss or an addition can be placed.

**Input:** `data/<company>/questions.jsonl` (the `Q5` questions and their `after_held_out`), the `expected` files, an extractor LLM and an answerer LLM (`EXTRACTOR_LLM_*` / `ANSWERER_LLM_*`, else `LLM_*`, or `--extractor-model` / `--answerer-model`).

**Output:** `scripts/evaluate_ingestion.py` (run by hand; prints the four stages and logs a run with the stage `ingestion`), `tests/test_evaluate_ingestion.py` (15 tests, run by the CI) and the section "Evaluate the ingestion" of the README. First runs, `qwen2.5:14b` for both tasks: the extractor returned 1 of the 2 commitments of `lamanija-0025` (the other missing, and the one found with the due date 2026-10-14 where `expected` has 2026-10-16); nothing was lost in storage or retrieval; the answer said the retrieved commitment of `q5-semana` in one run and left it out in the other.

**Logic:**
1. The Q5 questions declare one document that arrives later; the base are the documents their `expected` lists need (14 of 24). The script builds the app (`create_app`) on a temporary database with a recording extractor and drives it with `POST /documents` and `POST /chat`, so the endpoint, the extraction and the chat are the real ones. See "The ingestion is measured in four stages on the documents the question needs, and a commitment is blamed on the first stage that lost it".
2. Base documents are loaded, each question is asked (before), the new document is ingested, and each question is asked again (after).
3. Stage 1 compares what the extractor returned for the new document with its `expected` file (`evaluate_document` of `evaluate_extraction.py`). Stage 2 compares the commitments of the other documents before and after, and what the extractor returned with what was stored.
4. Stage 3 asks, of the commitments the question expects from the new document that stages 1 and 2 delivered (`wanted`), how many the chat retrieved (lost) and how many others of the new document it retrieved (added); before the ingestion it must retrieve none. Stage 4 judges the answer with `chat_judge.py` over everything retrieved: how many `wanted` it says, the wrong people or due date, the invented lines and the commitments of other documents it leaves out, before and after.
5. The extractor numbers its commitments in the order it returns them, so `expected` ids cannot be used to match: the pairing of stage 1 gives the map from `expected` id to extracted id.
6. The CI test runs the same check with a scripted extractor (the `expected` commitments of each document, with the errors a test asks for: a missing one, an extra one, a wrong due date, a failed call) and a fake answerer; see "The ingestion check is a manual script with a real LLM, plus a CI test with a scripted extractor".

**Important assumptions:**
- A wrong due date that takes a commitment out of the question's range (the week) shows in stage 1 (`wrong due`) and in stage 3 (`lost`): a `lost` next to a `wrong due` points to the extraction, not to the retriever. A test fixes it.
- The errors in the extraction of the 14 base documents are not placed on a stage; they only change what the chat is given (`others_missing`). `evaluate_extraction.py` measures them.
- The script exits 1 only for faults of the pipeline (the ingestion changed commitments of other documents, or the chat retrieved the new document before it was ingested), not for the quality of a model. When every answer is degraded it says the LLM did not answer and logs nothing, like `evaluate_chat.py`.
- A failed extraction of the new document counts all its commitments as missing; one of a base document is listed and the run goes on.
- With only the documents the questions need, the retriever has less to choose from than in the full load; a pass here is a weaker proof of the retrieval than the retrieval bank. The full load is #21.
- The script imports from `evaluate_extraction.py`, `evaluate_retrieval.py` and `chat_judge.py`, as the other evaluation scripts do; #32 has to update those imports when it moves them. My choice, not discussed beforehand.
- It goes through `fastapi.testclient` (a dev dependency) and the app's endpoints instead of calling the functions of the app directly, so the handler of `POST /documents` is covered too. My choice, not discussed beforehand.
- The numbers move between runs: the LLMs run at the server's default temperature, and two runs gave different answer-stage results with the same extraction.
- The pairing of stage 1 is that of `evaluate_extraction.py`; with two commitments of the same people and due date in the new document it could pair them crosswise. `lamanija-0025` has them in opposite directions, so it does not happen here.

**Location:** `scripts/evaluate_ingestion.py`, `tests/test_evaluate_ingestion.py`, `README.md` ("Evaluate the ingestion"). Commit `a23ef56`.

**Tests:** 286 tests pass (15 new). Breaking two counts of the script on purpose made three of them fail, then the script was put back. Run twice by hand against `qwen2.5:14b`, about two minutes each. The CI checks were run too: `check_dataset.py`, `check_chat_judge.py`, `evaluate_retrieval.py --strict`, `smoke_test.py` and `smoke_test_docker.py` pass.

**Issues:** closed #35. Comments on #26 (what the extractor did with `lamanija-0025`) and #32 (the new script and its imports).
