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

## Known limitations

- `POST /documents` extracts commitments only with the real LLM backend (Ollama by default). With the fake one, or if the call fails, the document is stored and the response says `extracted: false`.
- The dataset in `data/` is not part of the Docker image, so the loader runs on the host, not inside the container.
- Single user, no authentication.
- Content is synthetic and in Spanish.
- Commitments have no status: all extracted commitments are treated as open.
- Each commitment points to a single source document. The same commitment mentioned in later documents is stored again as a new one, so near-duplicates can appear.
- Every document must come with its type, date and participants as metadata. Sources that do not carry them (meetings, group chats) are not supported yet.

## Documentation

`docs/SPEC.md` defines the V0 scope, `docs/VISION.md` the product direction, `docs/DATASET.md` the format of the synthetic dataset, `docs/PROGRESS.md` logs closed work and `docs/DECISIONS.md` logs technical decisions. Pending work is tracked as GitHub Issues.
