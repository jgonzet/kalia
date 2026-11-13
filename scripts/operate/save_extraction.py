"""Turn the answer files of a manual extraction into a saved extraction of a company, to ship with the repo.

    uv run scripts/operate/save_extraction.py lamanija responses/batch-*.json \
        --model "Claude (manual flow)" --slug claudemanual --date 2026-10-09

It writes `data/<company>/extracted/<YYYYMMDD>-<slug>.json` (format and naming in docs/DATASET.md). Every answer is checked
as the app checks a live extraction; nothing is written if one fails, if a document has no answer, or if the id exists.
This is a development tool: the app only reads the file it writes.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

from app.extraction.parse import ExtractedCommitment, parse_items  # noqa: E402
from app.extraction.saved import EXTRACTED_DIR, SavedExtractionFile  # noqa: E402
from app.ingestion.dataset import DatasetSource  # noqa: E402

SLUG = re.compile(r"[a-z0-9]+(-\d+)?")  # the model, plus `-N` when the same model repeats the same day


def build(company_dir: Path, response_files: list[Path], model: str, slug: str, extraction_date: date) -> tuple[SavedExtractionFile, list[str]]:
    """Merge the answer files into the content of the saved extraction and list what is wrong with them."""
    source = DatasetSource(company_dir)
    catalog = source.catalog()
    documents = list(source.documents())
    answers: dict[str, list[ExtractedCommitment]] = {}
    problems: list[str] = []
    for path in response_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            problems.append(f"{path.name}: expected an object keyed by document id")
            continue
        for doc_id, items in data.items():
            if doc_id in answers:
                problems.append(f"{doc_id}: answered in more than one file")
            answers[doc_id] = items
    by_id = {d.id: d for d in documents}
    problems += [f"{doc_id}: not a document of the company (or held out)" for doc_id in answers if doc_id not in by_id]
    problems += [f"{doc.id}: no answer" for doc in documents if doc.id not in answers]
    for doc in documents:
        if doc.id in answers:
            problems += parse_items(answers[doc.id], doc, catalog, "local").problems
    content = SavedExtractionFile(
        id=f"{extraction_date:%Y%m%d}-{slug}",
        company=source.company["id"],
        model=model,
        date=extraction_date.isoformat(),
        documents={doc.id: answers[doc.id] for doc in documents if doc.id in answers},
    )
    return content, problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company", help="folder name under data/")
    parser.add_argument("responses", type=Path, nargs="+", help="answer files of the manual extraction")
    parser.add_argument("--model", required=True, help='model or flow as the chat page shows it, e.g. "Claude (manual flow)"')
    parser.add_argument("--slug", required=True, help="the model part of the id: lowercase letters and digits, plus -N if repeated that day, e.g. claudemanual")
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="day the extraction was made (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    if not SLUG.fullmatch(args.slug):
        print(f"--slug must be lowercase letters and digits, plus an optional -N, got {args.slug!r}")
        return 1

    company_dir = ROOT / "data" / args.company
    content, problems = build(company_dir, args.responses, args.model, args.slug, args.date)
    target = company_dir / EXTRACTED_DIR / f"{content['id']}.json"
    if target.exists():
        problems.append(f"{target.relative_to(ROOT)} exists: an id is never reused (for another extraction of the same day, end the slug in -2)")
    if problems:
        print("nothing written:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    items = sum(len(v) for v in content["documents"].values())
    print(f"wrote {target.relative_to(ROOT)}: {len(content['documents'])} documents, {items} commitments")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
