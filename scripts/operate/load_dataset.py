"""Initial load: store the catalog and the non-held-out documents of a company dataset.

Run with `uv run scripts/operate/load_dataset.py lamanija`. Uses DB_PATH and OWNER_ID from the environment.
Held-out documents are ingested afterwards through `POST /documents`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.ingestion.dataset import load_dataset  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: load_dataset.py <company>")
        return 2
    company_dir = ROOT / "data" / argv[1]
    if not company_dir.is_dir():
        print(f"no dataset at {company_dir}")
        return 1
    settings = Settings.from_env()
    result = load_dataset(company_dir, SqliteStore(settings.db_path, settings.owner_id))
    print(f"loaded {result.documents} documents and the catalog into {settings.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
