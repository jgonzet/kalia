"""Evaluate the stored commitments against the `expected` files of a synthetic dataset.

A development tool, not part of the app: real documents have no answer key. See README ("Evaluate the extraction").

    uv run scripts/evaluate_extraction.py lamanija                  table per document (worst first), detail, totals
    uv run scripts/evaluate_extraction.py lamanija --doc <id>       full detail of one document
    uv run scripts/evaluate_extraction.py lamanija --out run.json   also save the result, to compare two runs

Uses DB_PATH and OWNER_ID from the environment. Only documents that are stored and annotated are evaluated.
Matching, per document: first the pairs with the same people and due date, then, among what is left, the
pairs with the same people and a different due date (a match with a wrong due date). Ties go to the most
similar `what`. What stays unpaired is MISSING (expected only) or EXTRA (extracted only).
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

from app.config import Settings  # noqa: E402
from app.models import Catalog, Commitment  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402


@dataclass(frozen=True)
class Expected:
    id: str
    who_id: str
    to_whom_id: str
    what: str
    due: date | None
    project_id: str | None


@dataclass(frozen=True)
class AnswerKey:
    """What one document should give: its commitments and the phrases that are not commitments."""

    document_id: str
    commitments: tuple[Expected, ...]
    not_commitments: tuple[str, ...]


@dataclass(frozen=True)
class Match:
    expected_id: str
    extracted_id: str
    due_ok: bool
    project_ok: bool

    @property
    def ok(self) -> bool:
        return self.due_ok and self.project_ok


@dataclass
class DocumentResult:
    document_id: str
    expected: int
    extracted: int
    matches: list[Match] = field(default_factory=list)
    missing: list[Expected] = field(default_factory=list)
    extra: list[Commitment] = field(default_factory=list)
    not_commitments: list[str] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return len(self.missing) + len(self.extra) + sum(not m.ok for m in self.matches)


@dataclass(frozen=True)
class Totals:
    documents: int
    expected: int
    extracted: int
    matched: int
    due_ok: int
    project_ok: int
    extra_in_documents_with_not_commitments: int


def load_answer_keys(company_dir: Path, catalog: Catalog) -> dict[str, AnswerKey]:
    """Read `expected/*.json`, translating names to catalog ids; files without annotations are skipped."""
    people = {p.name: p.id for p in catalog.people}
    projects = {p.name: p.id for p in catalog.projects}
    keys: dict[str, AnswerKey] = {}
    for path in sorted((company_dir / "expected").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "commitments" not in data.get("extractions", {}):
            continue
        commitments = tuple(
            Expected(
                id=c["id"],
                who_id=people[c["who"]],
                to_whom_id=people[c["to_whom"]],
                what=c["what"],
                due=date.fromisoformat(c["due"]) if c["due"] else None,
                project_id=projects[c["project"]] if c["project"] else None,
            )
            for c in data["extractions"]["commitments"]
        )
        keys[data["document_id"]] = AnswerKey(data["document_id"], commitments, tuple(data.get("not_commitments", [])))
    return keys


def _pair_up(expected: list[Expected], extracted: list[Commitment], same_due: bool) -> list[tuple[Expected, Commitment]]:
    """Pair commitments with the same people (and due date if asked), most similar `what` first."""
    candidates = [
        (SequenceMatcher(None, e.what.lower(), c.what.lower()).ratio(), e, c)
        for e in expected
        for c in extracted
        if e.who_id == c.who_id and e.to_whom_id == c.to_whom_id and (not same_due or e.due == c.due)
    ]
    candidates.sort(key=lambda item: -item[0])
    pairs: list[tuple[Expected, Commitment]] = []
    used_expected: set[str] = set()
    used_extracted: set[str] = set()
    for _, e, c in candidates:
        if e.id not in used_expected and c.id not in used_extracted:
            pairs.append((e, c))
            used_expected.add(e.id)
            used_extracted.add(c.id)
    return pairs


def evaluate_document(key: AnswerKey, extracted: list[Commitment]) -> DocumentResult:
    """Match one document's extracted commitments against its answer key (rules in the module docstring)."""
    pairs = _pair_up(list(key.commitments), extracted, same_due=True)
    left_expected = [e for e in key.commitments if e.id not in {p[0].id for p in pairs}]
    left_extracted = [c for c in extracted if c.id not in {p[1].id for p in pairs}]
    pairs += _pair_up(left_expected, left_extracted, same_due=False)
    matched_expected = {e.id for e, _ in pairs}
    matched_extracted = {c.id for _, c in pairs}
    return DocumentResult(
        document_id=key.document_id,
        expected=len(key.commitments),
        extracted=len(extracted),
        matches=[Match(e.id, c.id, e.due == c.due, e.project_id == c.project_id) for e, c in sorted(pairs, key=lambda p: p[0].id)],
        missing=[e for e in key.commitments if e.id not in matched_expected],
        extra=[c for c in extracted if c.id not in matched_extracted],
        not_commitments=list(key.not_commitments),
    )


def evaluate(keys: dict[str, AnswerKey], stored: list[Commitment], stored_document_ids: set[str]) -> list[DocumentResult]:
    """Evaluate every document that is both stored and annotated, worst first."""
    results = [
        evaluate_document(key, [c for c in stored if c.document_id == doc_id])
        for doc_id, key in keys.items()
        if doc_id in stored_document_ids
    ]
    return sorted(results, key=lambda r: (-r.errors, r.document_id))


def totals(results: list[DocumentResult]) -> Totals:
    """Add up the counts of every document (not their percentages)."""
    return Totals(
        documents=len(results),
        expected=sum(r.expected for r in results),
        extracted=sum(r.extracted for r in results),
        matched=sum(len(r.matches) for r in results),
        due_ok=sum(m.due_ok for r in results for m in r.matches),
        project_ok=sum(m.project_ok for r in results for m in r.matches),
        extra_in_documents_with_not_commitments=sum(len(r.extra) for r in results if r.not_commitments),
    )


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def print_detail(result: DocumentResult, catalog: Catalog, show_all_matches: bool) -> None:
    """Print what is wrong in one document (and, if asked, every match)."""
    names = {p.id: p.name for p in catalog.people}
    print(f"{result.document_id}: expected {result.expected}, extracted {result.extracted}, matched {len(result.matches)}")
    for m in result.matches:
        if show_all_matches or not m.ok:
            problems = ("" if m.due_ok else " wrong due") + ("" if m.project_ok else " wrong project")
            print(f"    {'FIELD' if problems else 'OK':<8}{m.expected_id} <- {m.extracted_id}{problems}")
    for e in result.missing:
        print(f"    MISSING {names[e.who_id]} -> {names[e.to_whom_id]}, \"{e.what}\", {e.due}")
    for c in result.extra:
        print(f"    EXTRA   {names[c.who_id]} -> {names[c.to_whom_id]}, \"{c.what}\", {c.due}")
    for phrase in result.not_commitments:
        print(f"    not a commitment (may explain an EXTRA): {phrase}")


def to_json(results: list[DocumentResult]) -> str:
    """Serialize the per-document results and the totals, to compare two runs."""
    t = totals(results)
    summary = asdict(t) | {"recall": t.matched / t.expected if t.expected else 1.0, "precision": t.matched / t.extracted if t.extracted else 1.0}
    payload = {"totals": summary, "documents": [asdict(r) | {"errors": r.errors} for r in results]}
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    parser.add_argument("--doc", help="show the full detail of one document")
    parser.add_argument("--out", type=Path, help="save the result as JSON")
    args = parser.parse_args(argv)

    company_dir = ROOT / "data" / args.company
    if not company_dir.is_dir():
        print(f"no dataset at {company_dir}")
        return 1
    settings = Settings.from_env()
    store = SqliteStore(settings.db_path, settings.owner_id)
    catalog = store.load_catalog()
    if catalog is None:
        print(f"{settings.db_path} has no catalog; run scripts/load_dataset.py first")
        return 1
    stored_ids = {d.id for d in store.list_documents()}
    keys = load_answer_keys(company_dir, catalog)
    results = evaluate(keys, store.list_commitments(), stored_ids)

    if args.doc:
        chosen = [r for r in results if r.document_id == args.doc]
        if not chosen:
            print(f"{args.doc} is not stored or has no annotated expected file")
            return 1
        print_detail(chosen[0], catalog, show_all_matches=True)
        return 0

    print(f"{'document':<16}{'expected':>9}{'extracted':>10}{'matched':>8}{'missing':>8}{'extra':>6}{'field errors':>13}")
    for r in results:
        field_errors = sum(not m.ok for m in r.matches)
        print(f"{r.document_id:<16}{r.expected:>9}{r.extracted:>10}{len(r.matches):>8}{len(r.missing):>8}{len(r.extra):>6}{field_errors:>13}")
    print()
    for r in results:
        if r.errors:
            print_detail(r, catalog, show_all_matches=False)
    t = totals(results)
    skipped = sorted(set(keys) - stored_ids)
    print()
    print(f"Documents evaluated: {t.documents}" + (f" (annotated but not stored, skipped: {', '.join(skipped)})" if skipped else ""))
    print(f"Matched {t.matched} of {t.expected} expected   (recall {percent(t.matched, t.expected)})")
    print(f"Extra: {t.extracted - t.matched} of {t.extracted} extracted   (precision {percent(t.matched, t.extracted)})")
    print(f"Of the matched: due correct {t.due_ok}/{t.matched}, project correct {t.project_ok}/{t.matched}")
    print(f"Extra commitments in documents that have not_commitments: {t.extra_in_documents_with_not_commitments}")
    if args.out:
        args.out.write_text(to_json(results), encoding="utf-8")
        print(f"saved to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
