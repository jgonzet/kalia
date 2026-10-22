"""Extract the commitments of every document of a database with an LLM, the way the app does.

Two ways to use it, both through the same path as `POST /documents` (the app's prompt, `LLMExtractor`, `extract_and_store`):

- New database from a synthetic dataset:
  `uv run scripts/extract_dataset.py lamanija --db runs/qwen.db --model qwen2.5:14b`
  loads the catalog and the documents of `data/<company>/` (held-out documents excluded) and extracts them. It refuses
  to write into a database that already exists, so a run never mixes with an earlier one.
- Database that already has its documents (for example one filled with `scripts/load_dataset.py`):
  `uv run scripts/extract_dataset.py --db kalia.db --existing`
  extracts every stored document and replaces its commitments (the ones from other documents are untouched). It needs
  the catalog to be stored. Do it on a copy if you want to keep the old commitments.

Then measure it with `DB_PATH=<db> uv run scripts/evaluate_extraction.py <company> --model <model>`.

The backend, the endpoint and the key are those of the extractor task (`EXTRACTOR_LLM_*` if set, else `LLM_*`); the model comes
from `--model` (default: the extractor's model).
A document whose LLM call fails is listed at the end and the exit code is 1; its stored commitments stay as they were.
"""

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.extraction.llm_extractor import LLMExtractor  # noqa: E402
from app.extraction.run import extract_and_store  # noqa: E402
from app.ingestion.dataset import load_dataset  # noqa: E402
from app.llm import build_llm  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402


def main(argv: list[str]) -> int:
    defaults = Settings.from_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company", nargs="?", help="dataset to load into a new database (not used with --existing)")
    parser.add_argument("--db", type=Path, required=True, help="database to fill in (must not exist, unless --existing)")
    parser.add_argument("--existing", action="store_true", help="extract the documents already stored in --db instead of loading a dataset")
    parser.add_argument("--model", default=defaults.llm_for("extractor").model, help="model that extracts (default: the extractor's model)")
    args = parser.parse_args(argv)

    db_existed = args.db.exists()  # before SqliteStore creates the file
    if args.existing:
        if args.company:
            print("--existing takes the documents stored in the database; do not name a company")
            return 1
        store = SqliteStore(str(args.db), defaults.owner_id) if db_existed else None
        if store is None or store.load_catalog() is None:
            print(f"{args.db} does not exist or has no catalog; load a dataset first (scripts/load_dataset.py)")
            return 1
    else:
        if not args.company:
            print("name the company to load, or use --existing")
            return 1
        company_dir = ROOT / "data" / args.company
        if not company_dir.is_dir():
            print(f"no dataset at {company_dir}")
            return 1
        if db_existed:
            print(f"{args.db} already exists; choose another name so runs do not mix, or use --existing")
            return 1
        args.db.parent.mkdir(parents=True, exist_ok=True)
        store = SqliteStore(str(args.db), defaults.owner_id)
        load_dataset(company_dir, store)
    extractor = LLMExtractor(build_llm(replace(defaults.llm_for("extractor"), model=args.model)), defaults.owner_id)

    failed: list[str] = []
    started = time.monotonic()
    for document in store.list_documents():
        t0 = time.monotonic()
        ok = extract_and_store(document, extractor, store)
        count = sum(1 for c in store.list_commitments() if c.document_id == document.id)
        print(f"{document.id:<16}{'ok' if ok else 'FAILED':<8}{count:>3} commitments{time.monotonic() - t0:>8.1f}s", flush=True)
        if not ok:
            failed.append(document.id)
    print(f"done in {time.monotonic() - started:.0f}s; failed documents: {', '.join(failed) or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
