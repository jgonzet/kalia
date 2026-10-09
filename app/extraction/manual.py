"""Manual extraction: export requests for an external LLM session, import its answers."""

import json
from dataclasses import dataclass
from pathlib import Path

from app.extraction.parse import parse_items
from app.extraction.prompt import build_prompt
from app.models import Catalog, Commitment, Document

_PREAMBLE = """\
You will receive {count} independent requests, one per document. Treat each one on its own.
Answer with a single JSON object and nothing else: each key is a document id and each value is
the JSON list that the request for that document asks for.

"""


def export_requests(
    documents: list[Document], catalog: Catalog, out_dir: Path, batch_size: int
) -> list[Path]:
    """Write `batch-NN.md` files, each with the self-contained prompts of up to `batch_size` documents."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for number, start in enumerate(range(0, len(documents), batch_size), start=1):
        batch = documents[start : start + batch_size]
        blocks = [f"=== DOCUMENT {d.id} ===\n\n{build_prompt(d, catalog)}" for d in batch]
        path = out_dir / f"batch-{number:02d}.md"
        path.write_text(_PREAMBLE.format(count=len(batch)) + "\n\n".join(blocks) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


@dataclass(frozen=True)
class ImportReport:
    commitments: list[Commitment]
    problems: list[str]
    processed: list[str]
    not_processed: list[str]


def import_responses(
    response_path: Path, documents: list[Document], catalog: Catalog, owner_id: str
) -> ImportReport:
    """Validate an answer file `{"<document id>": [...]}`; report what is invalid or missing."""
    try:
        data = json.loads(response_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ImportReport([], [f"{response_path.name}: not valid JSON ({exc})"], [], [d.id for d in documents])
    if not isinstance(data, dict):
        return ImportReport([], [f"{response_path.name}: expected an object keyed by document id"], [], [d.id for d in documents])
    by_id = {d.id: d for d in documents}
    commitments: list[Commitment] = []
    problems = [f"{doc_id}: not a stored document, ignored" for doc_id in data if doc_id not in by_id]
    processed: list[str] = []
    for doc_id, items in data.items():
        if doc_id not in by_id:
            continue
        result = parse_items(items, by_id[doc_id], catalog, owner_id)
        commitments.extend(result.commitments)
        problems.extend(result.problems)
        processed.append(doc_id)
    return ImportReport(commitments, problems, processed, [i for i in by_id if i not in data])
