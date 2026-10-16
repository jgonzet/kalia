# KALIA

A contextual assistant for managers, PMs and tech leads. It reads unstructured work documents (emails, meeting transcripts, chats), extracts the commitments people made (who, to whom, what, by when), stores them, and answers questions about them in a chat.

## Status

V0, a first slice that runs locally for a single user on a synthetic dataset. It validates the pipeline documents -> structured commitments -> grounded answers. It has no proactive behavior and is not a task manager or a generic chatbot.

## How it works

1. A catalog (people, projects) and documents are ingested one at a time.
2. An LLM extracts commitments from each document and links them to the catalog.
3. Commitments are stored persistently.
4. A question in the chat retrieves the relevant commitments, and an LLM answers using only those.

The LLM is replaceable: any OpenAI-compatible endpoint works, local (Ollama by default) or API-based.

## Run

Requires Docker and [Ollama](https://ollama.com) running on the host with the model pulled (default `qwen2.5:14b`). Ollama must listen on an address the container can reach, not only on `127.0.0.1` (for example, set `OLLAMA_HOST=0.0.0.0`).

```bash
docker compose up --build
```

Defaults need no setup. To override any setting, copy `.env.example` to `.env` and uncomment the lines you want to change.

The app listens on <http://localhost:8000> (`/health` answers when it is up). The SQLite file lives in a Docker volume.

## Checks

- Smoke test (fake LLM, needs no Ollama, also what CI runs): `uv run scripts/smoke_test.py`
- Unit tests: `uv run pytest`
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
3. Fill in the commitments, with the manual steps above or through `POST /documents` with the real backend. There is no command yet that extracts the whole dataset with the real backend.
4. Evaluate: `uv run scripts/evaluate_extraction.py lamanija --out runs/<name>.json`.

The output has a table per document (worst first), the detail of each document with errors (missing, extra, wrong due date or project) and totals. The totals add up the counts of all the documents. `--doc <id>` shows one document in full. Each full evaluation is also appended to `runs/metrics.jsonl` (git-ignored) with the commit, the database file, the model you name with `--model` (the stored commitments do not say which model made them) and a hash of the prompt file as it is now, which is not the prompt that made them if the file changed since. `uv run scripts/run_log.py --stage extraction` lists the runs, so models and prompts can be compared over time; `--no-log` skips it. The JSON of `--out` is still available for a per-document comparison.

Within a document, an extracted commitment is paired with an expected one when they have the same people and due date, or the same people and another due date (counted as a wrong due date). Extracted commitments that are left over are "extra", expected ones that are left over are "missing". A "valid" extraction is not a "correct" one: validation (`import`) only checks the format. The evaluation does not detect `not_commitments` by itself: it counts the extra commitments of documents that have them and prints the phrases next to them to be read.

## Evaluate the retrieval

`scripts/evaluate_retrieval.py` measures how well the retrieval picks the commitments a question needs. Like the extraction evaluation, it is a development tool, not part of the app. Run it with `uv run scripts/evaluate_retrieval.py lamanija`; `--suite bank` or `--suite acceptance` measures only one of the two sets of questions:
- the **retrieval bank** (`data/<company>/retrieval_bank.jsonl`): many questions grouped by the angle they probe (how a person is named, direction, the org chart, dates, projects, combinations, groups, topics, open questions). It is described in `docs/DATASET.md` ("Retrieval bank"), with how to add questions.
- the **acceptance questions** (`questions.jsonl`): the five questions of the V0 definition of done.

It works on a temporary database built from the `expected` files, so an extraction error cannot count against the retrieval. It prints counts only, per category and in total: expected, retrieved, missing and extra (recall and precision over summed counts), and then the questions that differ. A question that changes once the held-out document is ingested is measured before and after. "Missing" is what the LLM can no longer recover; "extra" is what it has to discard. The unit tests in `tests/test_retrieval.py` cover the rules themselves, with small made-up data. `uv run scripts/retrieval_bank.py lamanija --check` verifies that the bank still agrees with the `expected` files (`scripts/check_dataset.py` does it too).

### Check that the bank notices a broken rule

A bank is only useful if it fails when the retriever breaks. `uv run scripts/check_bank_sensitivity.py lamanija` breaks one behaviour of `RuleRetriever` at a time, in memory and never on disk (ignoring names, "jefe", "jefe de X", "esta semana", "la semana que viene", the dates, "involucr" or more than one person; reading any "semana" as this week; counting "van" in "Van Houten" as a name; a week one day longer or shorter; no accent folding; the words that tell the question is about the user; "con" before a person, or any "con" at all; a retriever that returns everything or nothing), measures both sets of questions again and counts how many results changed. A mutation that changes none is `NOT DETECTED`: nothing in the bank would notice if that behaviour broke by accident.

- Run it after adding questions to the bank and after adding or changing a rule of the retriever.
- Exit code 1 means a behaviour is not covered and is not listed as a known blind spot. The fix is a new bank question for it (`docs/DATASET.md`, "Adding questions"), not an edit of the script.
- One blind spot is known and listed in the script with its reason: the dataset has no weekend deadlines, so a week one day shorter changes no answer. The script reports it if it starts being detected, so its note can be removed.
- When a rule is added to `app/answering/retrieval.py`, add to `MUTATIONS` the mutation that breaks it. The script patches names of that module, so a refactor that renames them makes it fail with an `AttributeError` until it is updated. It only applies to `RuleRetriever`; a retriever that works differently needs mutations of its own.

Each run is appended to `runs/metrics.jsonl` (git-ignored) with the commit (`*` if the tree had uncommitted changes), the retriever, the dataset, the suite and the questions version. `uv run scripts/run_log.py` lists the runs, so a change can be compared with the ones before it. Use `--no-log` to measure without logging. `--strict` makes the exit code 1 if a question loses commitments without declaring a `known_gap`; it is the line that must hold on every change, and `docs/DATASET.md` ("When a question fails") says what to do with a question that does not pass.

## Known limitations

- `POST /documents` extracts commitments only with the real LLM backend (Ollama by default). With the fake one, or if the call fails, the document is stored and the response says `extracted: false`.
- The dataset in `data/` is not part of the Docker image, so the loader runs on the host, not inside the container.
- Single user, no authentication.
- Content is synthetic and in Spanish.
- Commitments have no status: all extracted commitments are treated as open.
- Each commitment points to a single source document. The same commitment mentioned in later documents is stored again as a new one, so near-duplicates can appear.
- Retrieval works with rules over the question text: a person (full name, first name or a surname no one else shares; a name that is also an ordinary word, like a person called "Rosa", would be read as that person), "jefe"/"jefa" (the user's boss, or the boss of someone, "el jefe de Edna"), and the phrases "esta semana", "en la semana" and "la semana que viene". A rule narrows only when it understands the phrase; anything else leaves the result wider, so the LLM that answers can discard what is not needed. A question with none of the rules gets every commitment, and so does one that mentions a week in any other way ("la semana pasada", "la semana del 19", "dentro de una semana"). A person named without a word about the user ("tengo", "mi", "me", "yo", "prometí", "debo", or "con" right before the person, as in "con Frink") brings all of their commitments, not only those shared with the user. A surname shared by two people (such as "Bouvier") picks no one, silently. The user is found in the catalog by name. Today it does not understand days ("hoy", "mañana", "el viernes", exact dates), months, overdue or undated commitments, projects, areas, roles, topics or typos: it returns every commitment and the chat has to discard the rest. The retrieval bank measures all of this (`docs/DATASET.md`).
- Every document must come with its type, date and participants as metadata. Sources that do not carry them (meetings, group chats) are not supported yet.

## Documentation

`docs/SPEC.md` defines the V0 scope, `docs/VISION.md` the product direction, `docs/DATASET.md` the format of the synthetic dataset, `docs/PROGRESS.md` logs closed work and `docs/DECISIONS.md` logs technical decisions. Pending work is tracked as GitHub Issues.
