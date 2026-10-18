# KALIA

A contextual assistant for managers, PMs and tech leads. It reads unstructured work documents (emails, meeting transcripts, chats), extracts the commitments people made (who, to whom, what, by when), stores them, and answers questions about them in a chat.

## Status

V0, a first slice that runs locally for a single user on a synthetic dataset. It validates the pipeline documents -> structured commitments -> grounded answers. It has no proactive behavior and is not a task manager or a generic chatbot.

## How it works

1. A catalog (people, projects) and documents are ingested one at a time.
2. An LLM extracts commitments from each document and links them to the catalog.
3. Commitments are stored persistently.
4. A question in the chat retrieves the relevant commitments, and an LLM answers using only those.

The LLM is replaceable: Ollama through its native API (the default) or any OpenAI-compatible endpoint, local or API-based (`LLM_BACKEND`).

## Run

Requires Docker and [Ollama](https://ollama.com) running on the host with the model pulled (default `qwen2.5:14b`). Ollama must listen on an address the container can reach, not only on `127.0.0.1` (for example, set `OLLAMA_HOST=0.0.0.0`).

```bash
docker compose up --build
```

Defaults need no setup. To override any setting, copy `.env.example` to `.env` and uncomment the lines you want to change.

The app listens on <http://localhost:8000> (`/health` answers when it is up). The SQLite file lives in a Docker volume.

The chat page is at <http://localhost:8000/> and talks to `POST /chat` (`{"question": "..."}`; 1 to 1000 characters). The answer has the text, the commitments it was built from (with names) and `degraded`: true when the LLM failed and only those commitments came back. "Today" for questions such as "this week" is `REFERENCE_DATE` if set, otherwise the system date. To ask as of the dataset's day, set it to the `reference_date` in `data/<company>/company.json`. Scripts run with `uv run` read `.env` and `.env.secrets` from the project root (variables already set in the shell win); Docker Compose reads `.env`.

## Checks

- Smoke test (fake LLM, needs no Ollama, also what CI runs): `uv run scripts/smoke_test.py`
- Unit tests: `uv run pytest`
- Dataset and retrieval checks (the CI runs both): `uv run scripts/check_dataset.py` and `uv run scripts/evaluate_retrieval.py lamanija --strict --no-log`
- Manual check against the real LLM: `docker compose run --rm app python scripts/check_llm.py`

## Configuration

Environment variables are listed in `.env.example`, which is the only source.

## Load the synthetic dataset

`uv run scripts/load_dataset.py lamanija` stores the catalog and every document except the held-out one in the SQLite file (`DB_PATH`). A further document is added with `POST /documents`.

## Extract commitments with an external Claude session

There is no paid API setup yet, so the commitments of the stored documents can be extracted by a Claude session opened outside the repo:

1. Load the dataset (see above).
2. `uv run scripts/manual_extraction.py export` writes `requests/batch-NN.md` (git-ignored).
3. Copy a batch to an empty folder outside the repo, open Claude there and ask it to read the file and save its JSON answer.
4. Save the answer as `responses/batch-NN.json` and run `uv run scripts/manual_extraction.py import responses/batch-*.json`.

`import` validates the answers, reports problems and stores the valid commitments (importing again replaces them). `uv run scripts/manual_extraction.py status` says where the process stands and which command comes next.

## Evaluate the extraction

`scripts/evaluate_extraction.py` compares the commitments stored in a database with the answer key of a synthetic dataset (`data/<company>/expected/`). It is a development tool, not part of the app: documents of real users have no answer key. To measure a model or a prompt:

1. Use a database of its own, so runs do not overwrite each other: `mkdir -p runs` and `export DB_PATH=runs/<name>.db` (`runs/` is git-ignored).
2. Load the dataset: `uv run scripts/load_dataset.py lamanija`.
3. Fill in the commitments, either with the manual steps above or with a local model: `uv run scripts/extract_dataset.py lamanija --db runs/<name>.db --model <model>` creates the database (steps 1 and 2 are included, it refuses to write into one that exists) and extracts the 24 documents one by one through the same code as `POST /documents` (the app's prompt, `LLMExtractor`, `extract_and_store`), so it measures what the app would do. For a database that already has its documents (for example one filled with `scripts/load_dataset.py`), use `uv run scripts/extract_dataset.py --db <file> --existing`: it extracts every stored document and replaces its commitments, so work on a copy to keep the old ones. The backend, the endpoint and the key come from `LLM_BACKEND`, `LLM_BASE_URL` and `LLM_API_KEY`. It prints one line per document (commitments found, seconds) and lists the ones whose LLM call failed (exit code 1; their stored commitments stay as they were).
4. Evaluate: `DB_PATH=runs/<name>.db uv run scripts/evaluate_extraction.py lamanija --model <model> --out runs/<name>.json`.

The output has a table per document (worst first), the detail of each document with errors (missing, extra, wrong due date or project) and totals. The totals add up the counts of all the documents. `--doc <id>` shows one document in full. Each full evaluation is also appended to `runs/metrics.jsonl` (git-ignored) with the commit, the database file, the model you name with `--model` (the stored commitments do not say which model made them) and a hash of the prompt file as it is now, which is not the prompt that made them if the file changed since. `uv run scripts/run_log.py --stage extraction` lists the runs, so models and prompts can be compared over time; `--no-log` skips it. The JSON of `--out` is still available for a per-document comparison.

Within a document, an extracted commitment is paired with an expected one when they have the same people and due date, or the same people and another due date (counted as a wrong due date). Extracted commitments that are left over are "extra", expected ones that are left over are "missing". A "valid" extraction is not a "correct" one: validation (`import`) only checks the format. The evaluation does not detect `not_commitments` by itself: it counts the extra commitments of documents that have them and prints the phrases next to them to be read.

Reference numbers on `lamanija` (73 expected commitments, English prompt), to compare any new model or prompt against. The local models run at the server's default temperature, so repeat a run before drawing conclusions: two runs of `qwen2.5:14b` gave 37 and 39 matched, but precision 92% and 80%.

| Extraction | Matched | Recall | Precision | Due correct |
|---|---|---|---|---|
| Claude, manual flow | 70 | 96% | 97% | 68/70 |
| `qwen2.5:14b` (2 runs) | 37 / 39 | 51% / 53% | 92% / 80% | 21/37, 22/39 |
| `llama3.1` (8B) | 37 | 51% | 59% | 18/37 |
| `llama3.2` (3B) | 17 | 23% | 52% | 3/17 |

With the local models the chat starts from about half of the commitments (see "Known limitations").

## Evaluate the retrieval

`scripts/evaluate_retrieval.py` measures how well the retrieval picks the commitments a question needs. Like the extraction evaluation, it is a development tool, not part of the app. Run it with `uv run scripts/evaluate_retrieval.py lamanija`; `--suite bank` or `--suite acceptance` measures only one of the two sets of questions:
- the **retrieval bank** (`data/<company>/retrieval_bank.jsonl`): many questions grouped by the angle they probe (how a person is named, direction, the org chart, dates, projects, combinations, groups, topics, open questions). It is described in `docs/DATASET.md` ("Retrieval bank"), with how to add questions.
- the **acceptance questions** (`questions.jsonl`): the five questions of the V0 definition of done.

It works on a temporary database built from the `expected` files, so an extraction error cannot count against the retrieval. It prints counts only, per category and in total: expected, retrieved, missing and extra (recall and precision over summed counts), and then the questions that differ. A question that changes once the held-out document is ingested is measured before and after. "Missing" is what the LLM can no longer recover; "extra" is what it has to discard. The unit tests in `tests/test_retrieval.py` cover the rules themselves, with small made-up data. `uv run scripts/retrieval_bank.py lamanija --check` verifies that the bank still agrees with the `expected` files (`scripts/check_dataset.py` does it too).

### Check that the bank notices a broken rule

A bank is only useful if it fails when the retriever breaks. `uv run scripts/check_bank_sensitivity.py lamanija` breaks one behaviour of `RuleRetriever` at a time, in memory and never on disk (ignoring names, "jefe", "jefe de X", "esta semana", "la semana que viene", the dates, "involucr" or more than one person; reading any "semana" as this week; counting "van" in "Van Houten" as a name; a week one day longer or shorter; no accent folding; the words that tell the question is about the user, "me prometió" and similar, or any "me" at all; "con" before a person, or any "con" at all; a retriever that returns everything or nothing), measures both sets of questions again and counts how many results changed. A mutation that changes none is `NOT DETECTED`: nothing in the bank would notice if that behaviour broke by accident.

- Run it after adding questions to the bank and after adding or changing a rule of the retriever.
- Exit code 1 means a behaviour is not covered and is not listed as a known blind spot. The fix is a new bank question for it (`docs/DATASET.md`, "Adding questions"), not an edit of the script.
- One blind spot is known and listed in the script with its reason: the dataset has no weekend deadlines, so a week one day shorter changes no answer. The script reports it if it starts being detected, so its note can be removed.
- When a rule is added to `app/answering/retrieval.py`, add to `MUTATIONS` the mutation that breaks it. The script patches names of that module, so a refactor that renames them makes it fail with an `AttributeError` until it is updated. It only applies to `RuleRetriever`; a retriever that works differently needs mutations of its own.

Each run is appended to `runs/metrics.jsonl` (git-ignored) with the commit (`*` if the tree had uncommitted changes), the retriever, the dataset, the suite and the questions version. `uv run scripts/run_log.py` lists the runs, so a change can be compared with the ones before it. Use `--no-log` to measure without logging. `--strict` makes the exit code 1 if a question loses commitments without declaring a `known_gap`; it is the line that must hold on every change, and `docs/DATASET.md` ("When a question fails") says what to do with a question that does not pass.

## Evaluate the chat

`scripts/evaluate_chat.py` measures what the chat puts in its answers, with a real LLM, against the five acceptance questions of a synthetic dataset (`questions.jsonl`). It is a development tool, not part of the app, and it is how a model or a prompt of the chat is compared: the answering prompt is `app/prompts/answer_question.md`, the model is `LLM_MODEL`. Its own bank of questions is issue #16; the retrieval and the chat together, issue #21.

1. Have a database with the extracted commitments (see "Evaluate the extraction"), for example `export DB_PATH=runs/<name>.db`. The script copies it and never writes it.
2. Have Ollama (or the endpoint in `LLM_BASE_URL`, with `LLM_BACKEND=openai_compatible`) running with the model.
3. `uv run scripts/evaluate_chat.py lamanija --db runs/<name>.db`. Useful options: `--model` and `--extraction-model` (the second one extracts the held-out document of question 5), `--prompt <file>` to try instructions that are not the app's, `--question <id>` for one question, `--show` to read each answer with what it omitted or added, `--out <file>` for the full results in JSON, `--no-log`.

Per question it prints counts only: how many commitments the question needs (`expected`), how many of those are not in the database because the extraction missed them (`lost`: not the chat's fault), how many the retriever brought (`needed`), how many of those the answer contains (`in answer`), and how many commitments that were not needed it contains (`extra`). Question 5 is measured before and after the held-out document is ingested and extracted into the copy. The commitments are compared by content (people and due date) because the ids of a real extraction do not match those of the `expected` files.

Read the numbers with these limits in mind:
- "The answer contains a commitment" is a heuristic (half of the words of its `what` appear in the text). It does not notice a changed person or date; read the answers with `--show` before trusting a small difference.
- The LLM runs with the server's default temperature, so the same prompt gives different numbers each time: about five of the 140 needed commitments in total between runs, more on a single question. Compare prompts with repeated runs, and do not read a smaller difference as a finding.
- The baseline of 2026-10-16, `qwen2.5:14b` with Ollama's default settings and the prompt as it stands (in Spanish, with the states `atrasado`, `pendiente` and `sin fecha`, and without the ids on the lines): the answers contain 91 and 84 of about 140 needed commitments in two runs (about 62%), and add one to four that were not needed. The retriever brought almost exactly what each question needed, so the rest is the model leaving commitments out. The history of the same measurement, with the same questions: the first prompt in English 72 to 81; in Spanish with the state called `vencido` 71 and 67 (the model read "¿qué vence esta semana?" as a question about what is already overdue); in Spanish with `atrasado` 82 and 85; temperature 0 did not change anything. The same early prompt pasted by hand into Claude (claude.ai) gave 15 of 15 on "my boss" with both directions, and 7 of 14 on "due this week" because of a flaw in that day's wording, corrected since. So with a stronger model the design works; what limits the answers today is the local model. `llama3.1` (8B) gave 46 of 140 with the English prompt.
- Each run is appended to `runs/metrics.jsonl` (stage `chat`) with the commit, the models, a hash of the prompt file and the database; `uv run scripts/run_log.py --stage chat` lists them.

## Known limitations

- `POST /documents` extracts commitments only with the real LLM backend (Ollama by default). With the fake one, or if the call fails, the document is stored and the response says `extracted: false`.
- The dataset in `data/` is not part of the Docker image, so the loader runs on the host, not inside the container.
- Scripts read both `.env` and `.env.secrets`, but Docker Compose passes only `.env` to the container, so an API key in `.env.secrets` does not reach the app in Docker. Ollama, the default, needs no key.
- Single user, no authentication.
- Content is synthetic and in Spanish.
- Commitments have no status: all extracted commitments are treated as open. The chat marks each one as `atrasado` (its due date is before "today"), `pendiente` or `sin fecha`, computed by the code; `atrasado` only says the date passed, not that nothing was done.
- Extraction with a local model finds about half of the commitments (see "Evaluate the extraction"): it skips some documents altogether, writes a short name ("Burns") where the catalog has the full one, so that commitment is discarded, and gets the relative dates wrong more than half of the time. What the chat can answer starts from there (#26).
- The chat answer is only as good as the model: with `qwen2.5:14b` it leaves out about 40% of the commitments the question needs, scattered through the list, and it sometimes changes a person in a line (see "Evaluate the chat"). The page shows the text as it comes, so the Markdown a model writes (`###`, `**`) appears raw, and it lists the commitments only when the LLM failed. The answering prompt is in Spanish, like the data; the extraction prompt is still in English.
- With Ollama the app asks for a context window of `LLM_CONTEXT_TOKENS` (default 10240, what `qwen2.5:14b` needs to run entirely on a 12 GB GPU) and does not send the LLM a prompt that is estimated not to fit: it answers like when the LLM fails (`degraded`) with a text that says the question brings too many commitments, and the list. The estimate is the length in characters divided by 3 with a 5% margin, not a count with the model's tokenizer, and the room the answer itself needs is not reserved. With `openai_compatible` there is no check unless `LLM_CONTEXT_TOKENS` is set, as the app cannot make that server use a window. A question that brings every commitment ("¿Qué prometí?" with 72) is about 3900 tokens today (#27).
- The text of every commitment, which comes from the documents, is put in the prompt as it is. With sources that are not your own, a document could carry instructions for the model (#28).
- Each commitment points to a single source document. The same commitment mentioned in later documents is stored again as a new one, so near-duplicates can appear.
- Retrieval works with rules over the question text: a person (full name, first name or a surname no one else shares; a name that is also an ordinary word, like a person called "Rosa", would be read as that person), "jefe"/"jefa" (the user's boss, or the boss of someone, "el jefe de Edna"), and the phrases "esta semana", "en la semana" and "la semana que viene". A rule narrows only when it understands the phrase; anything else leaves the result wider, so the LLM that answers can discard what is not needed. A question with none of the rules gets every commitment, and so does one that mentions a week in any other way ("la semana pasada", "la semana del 19", "dentro de una semana"). A person named without a word about the user ("tengo", "prometí", "debo", "me prometió"/"me deben" and similar, or "con" right before the person, as in "con Frink") brings all of their commitments, not only those shared with the user ("mi", "yo" and a request like "¿me podés decir…?" do not count as such a word). A surname shared by two people (such as "Bouvier") picks no one, silently. The user is found in the catalog by name. Today it does not understand days ("hoy", "mañana", "el viernes", exact dates), months, overdue or undated commitments, projects, areas, roles, topics or typos: it returns every commitment and the chat has to discard the rest. The retrieval bank measures all of this (`docs/DATASET.md`).
- Every document must come with its type, date and participants as metadata. Sources that do not carry them (meetings, group chats) are not supported yet.

## Documentation

`docs/SPEC.md` defines the V0 scope, `docs/VISION.md` the product direction, `docs/DATASET.md` the format of the synthetic dataset, `docs/PROGRESS.md` logs closed work and `docs/DECISIONS.md` logs technical decisions. Pending work is tracked as GitHub Issues.
