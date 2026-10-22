# KALIA

A contextual assistant for managers, PMs and tech leads. It reads unstructured work documents (emails, meeting transcripts, chats), extracts the commitments people made (who, to whom, what, by when), stores them, and answers questions about them in a chat.

## Status

V0, a first slice that runs locally for a single user on a synthetic dataset. It validates the pipeline documents -> structured commitments -> grounded answers. It has no proactive behavior and is not a task manager or a generic chatbot.

## How it works

1. A catalog (people, projects) and documents are ingested one at a time.
2. An LLM extracts commitments from each document and links them to the catalog.
3. Commitments are stored in a SQLite file. Inside Docker the file is deleted with the container, so nothing is kept between runs.
4. A question in the chat retrieves the relevant commitments, and an LLM answers using only those.

The LLM is replaceable: Ollama through its native API (the default), the Claude API or any OpenAI-compatible endpoint, local or API-based (`LLM_BACKEND`). Each task that calls an LLM (extracting commitments, answering the chat) can use a different one.

## Run

Requires Docker and an LLM: either [Ollama](https://ollama.com) running on the host with the model pulled (default `qwen2.5:14b`), or an API key (see "Use the Claude API instead of Ollama"). Ollama must listen on an address the container can reach, not only on `127.0.0.1` (for example, set `OLLAMA_HOST=0.0.0.0`).

```bash
docker compose up --build
```

Defaults need no setup. To override any setting, copy `.env.example` to `.env` and uncomment the lines you want to change.

The app listens on <http://localhost:8000> (`/health` answers when it is up). The SQLite file lives inside the container: `docker compose down` deletes it.

The chat page is at <http://localhost:8000/> and talks to `POST /chat` (`{"question": "..."}`; 1 to 1000 characters). The answer has the text, the commitments it was built from (with names) and `degraded`: true when the LLM failed and only those commitments came back. "Today" for questions such as "this week" is `REFERENCE_DATE` if set, otherwise the sample company's date when a sample is loaded (see "The sample company"), otherwise the system date. Outside the sample, to ask as of the dataset's day, set it to the `reference_date` in `data/<company>/company.json`. Scripts run with `uv run` read `.env` and `.env.secrets` from the project root (variables already set in the shell win); Docker Compose reads `.env`.

### The sample company

When the database does not hold the sample yet, the app loads a sample company by itself: La Manija Games, a fictional game studio, with its people and projects and 24 of its 25 documents (the 25th is kept out on purpose, for tests). Its commitments come already computed (from `data/lamanija/expected/`), so nothing is extracted at startup and no LLM is needed to load it. The chat page says so at the top. Asking questions does need Ollama or another LLM.

"Today" for the sample is `REFERENCE_DATE` if you set it, otherwise 2026-10-12 (the sample's own date), otherwise the system date. Documents you send are read against that same date.

To have your own LLM extract the sample's commitments instead, set `COMMITMENTS_SOURCE=extraction` in `.env` (see `.env.example`). The app then waits until the 24 documents are done before it answers (minutes with a local model), and it repeats this on every `docker compose up` because nothing is kept between runs; with a paid API that costs money each time. A document whose extraction fails is left without commitments and the rest goes on, unless three fail in a row: the LLM is then taken as unreachable and the others are not tried. The notice on the page says how many failed. Each attempt at a call to the LLM waits at most `LLM_TIMEOUT_SECONDS` (default 120); the clients of `openai_compatible` and `anthropic` retry a failed call twice more, so one call can take about three times that.

### Use the Claude API instead of Ollama

No Ollama needed. Copy `.env.secrets.example` to `.env.secrets` and `.env.example` to `.env`, then:

1. In `.env.secrets`, set `LLM_API_KEY` to your key. It is the only file that holds secrets; it is git-ignored and Docker Compose passes it to the container as an environment variable, it is never copied into the image.
2. In `.env`, set `LLM_BACKEND=anthropic` and `LLM_MODEL` to the Claude model you want (the app refuses to start without a model for this backend).
3. `docker compose up --build`.

Any other OpenAI-compatible endpoint is the same with `LLM_BACKEND=openai_compatible`, plus `LLM_BASE_URL` and `LLM_MODEL`. To give one task a different LLM from the other (the extractor with Claude and the chat with Ollama, say), use the `EXTRACTOR_LLM_*` and `ANSWERER_LLM_*` variables described in `.env.example`: a task that sets any of them takes all its settings from them, including its own key.

### What a paid API costs

The app only calls the LLM in two places: once per document it extracts and once per question in the chat. Nothing else is sent.

- **Extraction of the sample** (`COMMITMENTS_SOURCE=extraction`): 24 calls, one per document. The 24 documents have about 6,200 words in total, plus the instructions of the prompt in every call. By rough estimate (not measured) that is tens of thousands of tokens in all. With a paid backend the app writes a warning to the log at startup saying how many documents it is about to send.
- **Chat**: one call per question. The prompt carries the commitments the retrieval picked, so a broad question ("¿Qué prometí?", which brings every commitment) costs more than a specific one.
- **Repeats**: the database is destroyed with the container, so the extraction is paid again on every `docker compose up`.

The app does not count tokens or money yet; measuring it is issue #42.

### Send a document of your own

The page has no form for this yet. Send the document to `POST /documents`; it is stored and its commitments are extracted with the LLM you configured. The participants should be people of the sample catalog, written as in `data/lamanija/people.jsonl`: a commitment whose people the catalog does not know is discarded.

```bash
curl -X POST http://localhost:8000/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "my-document-1",
    "type": "email",
    "date": "2026-10-12",
    "participants": ["Lalo Landa", "Waylon Smithers"],
    "text": "Hola Lalo, te confirmo que el 16 de octubre te paso el presupuesto actualizado de Jimboland. Saludos, Waylon"
  }'
```

`type` is `email`, `meeting` or `chat`. The answer is `{"id": "my-document-1", "stored": true, "extracted": true}`; `extracted: false` means the document is stored but no commitments came out (the LLM failed, or the backend is the fake one). Sending the same `id` again replaces the document. Then ask the chat about it.

### Clean up

Nothing stays on your machine except the image. `docker compose down` removes the container and its database; `docker compose down --rmi local` also removes the image.

## Checks

- Smoke test (fake LLM, needs no Ollama, also what CI runs): `uv run scripts/smoke_test.py`
- Docker smoke test (starts the container with the fake LLM, checks the sample is loaded and removes everything; needs Docker, also what CI runs): `uv run scripts/smoke_test_docker.py`
- Unit tests: `uv run pytest`
- Dataset and retrieval checks (the CI runs both): `uv run scripts/check_dataset.py` and `uv run scripts/evaluate_retrieval.py lamanija --strict --no-log`
- Manual check against the real LLM: `docker compose run --rm app python scripts/check_llm.py`
- How long the chat takes with your LLM and your machine: `uv run scripts/measure_latency.py` (prints a report in the format of `docs/MEASUREMENTS.md`)

## Configuration

Environment variables are listed in `.env.example` (settings) and `.env.secrets.example` (API keys), which are the only source.

## Load the synthetic dataset

Inside Docker the app does this by itself (see "The sample company"). Outside Docker, `uv run scripts/load_dataset.py lamanija` stores the catalog and every document except the held-out one in the SQLite file (`DB_PATH`), without commitments. A further document is added with `POST /documents`.

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
3. Fill in the commitments, either with the manual steps above or with a local model: `uv run scripts/extract_dataset.py lamanija --db runs/<name>.db --model <model>` creates the database (steps 1 and 2 are included, it refuses to write into one that exists) and extracts the 24 documents one by one through the same code as `POST /documents` (the app's prompt, `LLMExtractor`, `extract_and_store`), so it measures what the app would do. For a database that already has its documents (for example one filled with `scripts/load_dataset.py`), use `uv run scripts/extract_dataset.py --db <file> --existing`: it extracts every stored document and replaces its commitments, so work on a copy to keep the old ones. The backend, the endpoint and the key are those of the extractor (`EXTRACTOR_LLM_*` if set, else `LLM_*`); `--model` picks the model. It prints one line per document (commitments found, seconds) and lists the ones whose LLM call failed (exit code 1; their stored commitments stay as they were).
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

`scripts/evaluate_chat.py` measures what the LLM of the chat does with a list of commitments that is already chosen, with a real LLM. It is a development tool, not part of the app, and it is how a model or a prompt of the chat is compared: the answering prompt is `app/prompts/answer_question.md`, the model is the answerer's (`ANSWERER_LLM_MODEL` if set, else `LLM_MODEL`). The retrieval has its own measurement ("Evaluate the retrieval") and the two together are issue #21.

1. Have the LLM of the answerer reachable (Ollama running with the model, or the key of an API set in `.env.secrets`). No database is needed: the commitments come from the `expected` files of the dataset.
2. `uv run scripts/evaluate_chat.py lamanija`. Useful options: `--model`, `--prompt <file>` to try instructions that are not the app's, `--category` and `--question <text>` to run part of the bank, `--show` to read each answer with what was wrong in it, `--out <file>` for the full results in JSON, `--no-log`.

The questions are those of `data/<company>/chat_bank.jsonl` (`docs/DATASET.md`, "Chat bank"). Each one hands the LLM the commitments of the whole dataset that it needs plus some it does not (the opposite direction, the same person with others, the next week, other projects), through the same code the chat runs after it retrieves. Per category and in total it prints counts only: how many commitments were needed, how many the answer says, how many it leaves out (`missing`), how many of the noise it says anyway (`extra`), how many it says with the wrong person or direction (`people`) or the wrong due date (`due`) or with no date, and how many lines look like a commitment nobody gave (`invented`, an upper bound: read them with `--show`). It then lists the questions with something wrong. Three more checks run apart from the bank: the answer when the LLM fails, comes back empty, or the prompt does not fit the context window; the script exits 1 if one fails.

Read the numbers with these limits in mind:
- The answers are judged with rules (`scripts/chat_judge.py`), not by a second LLM: a paraphrase that shares few words with a commitment is not found, and the direction is judged only on lines with an arrow. `uv run scripts/check_chat_judge.py` (no dataset needed; the CI runs it) shows what it tells apart; run it after changing the judge, and read some answers with `--show` before trusting a small difference.
- The LLM runs with the server's default temperature, so the same prompt gives different numbers each time. With `qwen2.5:14b` and the prompt of 2026-10-19, four runs said 365, 370, 383 and 384 of 564 needed commitments (a spread of about 3%); most of it comes from a few long lists ("¿Cómo viene todo?" gave 60, 60 and 28 of 75), and 29 of the 64 questions gave the same count in three runs. Compare prompts with repeated runs, and do not read a smaller difference as a finding.
- The bank is not an exam of the whole chat: what it leaves out is in `docs/DATASET.md` ("What the bank does not cover").
- Each run is appended to `runs/metrics.jsonl` (stage `chat_bank`) with the commit, the model, a hash of the prompt file and the bank version; `uv run scripts/run_log.py --stage chat_bank` lists them. Runs of the stage `chat` are from the previous evaluation and are not comparable.
- After measuring a change of the prompt, add a row to `app/prompts/answer_question.history.md`: what changed, why, and what it did to the numbers.

## Known limitations

- `POST /documents` extracts commitments only with a real LLM backend (not the fake one). With the fake one, or if the call fails, the document is stored and the response says `extracted: false`.
- The Docker image carries only the files needed to load the sample company (`data/lamanija/`: catalog, documents and answer keys), not the question banks or the scripts (except `scripts/check_llm.py`). The evaluation and loading scripts run on the host.
- The database inside Docker is deleted with the container (`docker compose down`): nothing you send is kept between runs. Outside Docker, `DB_PATH` is a file that stays.
- Only Ollama has been tried against a real model. The `anthropic` and `openai_compatible` backends have not been tried with a real API key.
- Single user, no authentication.
- Content is synthetic and in Spanish.
- Commitments have no status: all extracted commitments are treated as open. The chat marks each one as `atrasado` (its due date is before "today"), `pendiente` or `sin fecha`, computed by the code; `atrasado` only says the date passed, not that nothing was done.
- Extraction with a local model finds about half of the commitments (see "Evaluate the extraction"): it skips some documents altogether, writes a short name ("Burns") where the catalog has the full one, so that commitment is discarded, and gets the relative dates wrong more than half of the time. What the chat can answer starts from there (#26).
- The chat answer is only as good as the model: with `qwen2.5:14b` the answers say about two thirds of the commitments the question needs (365 to 384 of 564 in four runs of the chat bank, 2026-10-19), leave out the rest, mix in about 35 commitments that were noise, and sometimes invert the direction of a line or change a person. It does worst on the whole list ("¿Cómo viene todo?": 28 to 60 of 75, the same prompt in different runs), on "mi jefe" (8 or 9 of 18) and on a project named partly (11 to 16 of 29). The page shows the text as it comes, so the Markdown a model writes (`###`, `**`) appears raw, and it lists the commitments only when the LLM failed. The answering prompt is in Spanish, like the data; the extraction prompt is still in English.
- With a local model, the time to answer depends on how much the model writes. Measured on 2026-10-21 (RTX 4080 Laptop 12 GB, `qwen2.5:14b`, 10240-token window): about 40 tokens per second whatever the temperature of the GPU, a median answer of 4 seconds and 9 of 10 under 13 seconds. A question that brings every commitment ("¿Cómo viene todo?") is the exception: the same question got answers of 500 and of 2700 tokens, from 13 to 72 seconds. The timeout of each attempt is 120 seconds by default (it was 60, which that question exceeded in 4 of 12 runs; `LLM_TIMEOUT_SECONDS` changes it); on a slower machine, or one without a GPU, the long questions can reach it and come back `degraded`, so raise it there. Asking for "at most 10 lines" in the prompt cut the longest answer to 440 tokens but the answers said 262 to 287 of the 564 needed commitments, against 365 to 397 without it, so the answering prompt carries no such limit. The numbers and how they were taken are in `docs/MEASUREMENTS.md`; `uv run scripts/measure_latency.py` measures your own machine.
- The chat bank (`docs/DATASET.md`, "Chat bank") measures how the LLM filters and words a list of at most a few dozen commitments on one synthetic dataset, judging the answers with rules. It does not measure questions that need the org chart, the size of a real list, instructions hidden in a document or what the extraction misses, so a good result there does not mean the chat is tested.
- With Ollama the app asks for a context window of `LLM_CONTEXT_TOKENS` (default 10240, what `qwen2.5:14b` needs to run entirely on a 12 GB GPU) and does not send the LLM a prompt that is estimated not to fit: it answers like when the LLM fails (`degraded`) with a text that says the question brings too many commitments, and the list. The estimate is the length in characters divided by 3 with a 5% margin, not a count with the model's tokenizer, and the room the answer itself needs is not reserved. With `openai_compatible` and `anthropic` there is no check unless `LLM_CONTEXT_TOKENS` is set, as the app cannot make that server use a window (a prompt the API rejects comes back as a failed LLM call, `degraded`). A question that brings every commitment ("¿Qué prometí?" with 72) is about 3900 tokens today (#27).
- The text of every commitment, which comes from the documents, is put in the prompt as it is. With sources that are not your own, a document could carry instructions for the model (#28).
- Each commitment points to a single source document. The same commitment mentioned in later documents is stored again as a new one, so near-duplicates can appear.
- Retrieval works with rules over the question text: a person (full name, first name or a surname no one else shares; a name that is also an ordinary word, like a person called "Rosa", would be read as that person), "jefe"/"jefa" (the user's boss, or the boss of someone, "el jefe de Edna"), and the phrases "esta semana", "en la semana" and "la semana que viene". A rule narrows only when it understands the phrase; anything else leaves the result wider, so the LLM that answers can discard what is not needed. A question with none of the rules gets every commitment, and so does one that mentions a week in any other way ("la semana pasada", "la semana del 19", "dentro de una semana"). A person named without a word about the user ("tengo", "prometí", "debo", "me prometió"/"me deben" and similar, or "con" right before the person, as in "con Frink") brings all of their commitments, not only those shared with the user ("mi", "yo" and a request like "¿me podés decir…?" do not count as such a word). A surname shared by two people (such as "Bouvier") picks no one, silently. The user is found in the catalog by name. Today it does not understand days ("hoy", "mañana", "el viernes", exact dates), months, overdue or undated commitments, projects, areas, roles, topics or typos: it returns every commitment and the chat has to discard the rest. The retrieval bank measures all of this (`docs/DATASET.md`).
- Every document must come with its type, date and participants as metadata. Sources that do not carry them (meetings, group chats) are not supported yet.

## Documentation

`docs/SPEC.md` defines the V0 scope, `docs/VISION.md` the product direction, `docs/DATASET.md` the format of the synthetic dataset, `docs/PROGRESS.md` logs closed work, `docs/DECISIONS.md` logs technical decisions and `docs/MEASUREMENTS.md` logs how long the app takes with a real LLM, on which machine. Pending work is tracked as GitHub Issues.
