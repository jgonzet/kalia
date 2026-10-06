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

## Configuration

Environment variables are listed in `.env.example`, which is the only source.

## Known limitations

- Single user, no authentication.
- Content is synthetic and in Spanish.
- Commitments have no status: all extracted commitments are treated as open.
- Each commitment points to a single source document. The same commitment mentioned in later documents is stored again as a new one, so near-duplicates can appear.
- Every document must come with its type, date and participants as metadata. Sources that do not carry them (meetings, group chats) are not supported yet.

## Documentation

`docs/SPEC.md` defines the V0 scope, `docs/VISION.md` the product direction, `docs/PROGRESS.md` logs closed work and `docs/DECISIONS.md` logs technical decisions. Pending work is tracked as GitHub Issues.
