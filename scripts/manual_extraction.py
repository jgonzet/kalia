"""Manual extraction through an external LLM session, one with no access to the repo.

Run `uv run scripts/manual_extraction.py status` at any point: it says where you are and what to run next.
The steps, in order:
1. `uv run scripts/load_dataset.py lamanija` stores the catalog and the documents.
2. `export` writes `requests/batch-NN.md` (git-ignored).
3. Open a session in an empty folder outside the repo, paste one request file and let it answer (the only manual step).
4. Save the answer as `responses/batch-NN.json`.
5. `import responses/batch-*.json` validates the answers, reports problems and stores the valid commitments
   (re-importing replaces each document's commitments).

Uses DB_PATH and OWNER_ID from the environment.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.extraction.manual import export_requests, import_responses  # noqa: E402
from app.models import Document  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402


def show_status(store: SqliteStore, documents: list[Document], requests: Path, responses: Path) -> int:
    """Print the state of the manual extraction and the next command to run."""
    stored = {c.document_id for c in store.list_commitments()}
    request_files = sorted(requests.glob("batch-*.md")) if requests.is_dir() else []
    response_files = sorted(responses.glob("batch-*.json")) if responses.is_dir() else []
    answered: dict[str, int] = {}  # document id -> number of commitments the answer files give it
    for path in response_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # import reports it
        if isinstance(data, dict):
            answered.update({doc_id: len(items) for doc_id, items in data.items() if isinstance(items, list)})
    unanswered = [d.id for d in documents if d.id not in answered]
    not_imported = [d.id for d in documents if answered.get(d.id) and d.id not in stored]
    print(f"documents stored: {len(documents)}; with commitments in the database: {len(stored)}")
    print(f"request files: {len(request_files)}; answer files: {len(response_files)}")
    if unanswered:
        print("  no answer yet: " + ", ".join(unanswered))
    if not_imported:
        print("  answered but not imported: " + ", ".join(not_imported))
    if not request_files:
        print("Next: uv run scripts/manual_extraction.py export")
    elif unanswered:
        print("Next: give each requests/batch-NN.md to an external Claude session and save its answer as responses/batch-NN.json")
    elif not_imported:
        print("Next: uv run scripts/manual_extraction.py import responses/batch-*.json")
    else:
        print("Nothing left to do: every stored document was answered and its commitments are in the database.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write the request files")
    export.add_argument("--batch-size", type=int, default=8)
    export.add_argument("--out", type=Path, default=ROOT / "requests")
    imp = sub.add_parser("import", help="validate answer files and store their commitments")
    imp.add_argument("responses", type=Path, nargs="+")
    sub.add_parser("status", help="show where the manual extraction stands and the next command to run")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    store = SqliteStore(settings.db_path, settings.owner_id)
    catalog = store.load_catalog()
    documents = store.list_documents()
    if catalog is None or not documents:
        print(f"{settings.db_path} has no catalog or documents. Next: uv run scripts/load_dataset.py <company>")
        return 1

    if args.command == "status":
        return show_status(store, documents, ROOT / "requests", ROOT / "responses")

    if args.command == "export":
        paths = export_requests(documents, catalog, args.out, args.batch_size)
        print(f"wrote {len(paths)} request files for {len(documents)} documents in {args.out}")
        return 0

    exit_code = 0
    for response in args.responses:
        report = import_responses(response, documents, catalog, settings.owner_id)
        print(f"{response.name}: documents processed: {len(report.processed)}; not processed: {len(report.not_processed)}")
        print(f"valid commitments: {len(report.commitments)}; problems: {len(report.problems)}")
        for problem in report.problems:
            print(f"  - {problem}")
        for doc_id in report.processed:
            store.save_document_commitments(doc_id, [c for c in report.commitments if c.document_id == doc_id])
        print(f"stored: {len(report.commitments)} commitments for {len(report.processed)} documents")
        if report.problems:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
