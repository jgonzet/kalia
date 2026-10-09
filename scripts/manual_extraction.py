"""Manual extraction through an external LLM session, one with no access to the repo.

1. Load the dataset: `uv run scripts/load_dataset.py lamanija`.
2. `uv run scripts/manual_extraction.py export` writes `requests/batch-NN.md` (git-ignored).
3. Open a session in an empty folder outside the repo, paste one request file and let it answer.
4. Save the answer as `responses/batch-NN.json`.
5. `uv run scripts/manual_extraction.py import responses/batch-NN.json` validates it and reports problems.

Uses DB_PATH and OWNER_ID from the environment. Storing the commitments waits for issue #11.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.extraction.manual import export_requests, import_responses  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write the request files")
    export.add_argument("--batch-size", type=int, default=8)
    export.add_argument("--out", type=Path, default=ROOT / "requests")
    imp = sub.add_parser("import", help="validate an answer file")
    imp.add_argument("response", type=Path)
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    store = SqliteStore(settings.db_path, settings.owner_id)
    catalog = store.load_catalog()
    documents = store.list_documents()
    if catalog is None or not documents:
        print(f"{settings.db_path} has no catalog or documents; run scripts/load_dataset.py first")
        return 1

    if args.command == "export":
        paths = export_requests(documents, catalog, args.out, args.batch_size)
        print(f"wrote {len(paths)} request files for {len(documents)} documents in {args.out}")
        return 0

    report = import_responses(args.response, documents, catalog, settings.owner_id)
    print(f"documents processed: {len(report.processed)}; not processed: {len(report.not_processed)}")
    print(f"valid commitments: {len(report.commitments)}; problems: {len(report.problems)}")
    for problem in report.problems:
        print(f"  - {problem}")
    if report.not_processed:
        print(f"  not in the answer: {', '.join(report.not_processed)}")
    print("not stored: CommitmentStore has no SQLite implementation yet (issue #11)")
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
