"""Check that the documents and the expected files of a synthetic dataset agree, and that its retrieval bank and its chat bank still match them.

Usage: uv run scripts/dataset/check_dataset.py [company ...] [--stamp] [--allow-pending]

Formats are defined in docs/DATASET.md. Whether a text really contains each
commitment is not checked here: that stays a manual review.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))  # make `scripts` importable when this file is run by path

from scripts.quality.chat_judge import content_words  # noqa: E402
from scripts.dataset.chat_bank import check_company_chat_bank  # noqa: E402
from scripts.dataset.retrieval_bank import check_company_bank  # noqa: E402

DATA_DIR = ROOT / "data"
MIN_JUDGEABLE_WORDS = 3  # words of four letters or more a commitment's `what` needs for the judge of the chat to find it
COMMITMENT_ID = re.compile(r"^(?P<doc>.+)-c(?P<n>\d+)$")
HEADER_KEYS = ("id", "type", "date", "participants")


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of records."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def parse_document(path: Path) -> tuple[dict[str, str], str]:
    """Split a document into its header fields and its body text."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("does not start with a '---' header")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError("header is not closed with '---'") from None
    header: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"header line without ':': {line!r}")
        header[key.strip()] = value.strip()
    return header, "\n".join(lines[end + 1 :])


def text_hash(body: str) -> str:
    """SHA-256 of the body, stripped, as defined in docs/DATASET.md."""
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()


def check_expected(
    expected: dict,
    people: set[str],
    projects: set[str],
    earlier_commitments: set[str],
    errors: list[str],
) -> set[str]:
    """Check one expected file against the catalog; return its commitment ids."""
    doc_id = expected["document_id"]
    err = lambda msg: errors.append(f"{doc_id}: {msg}")  # noqa: E731
    participants = set(expected.get("participants", []))
    for name in participants - people:
        err(f"participant not in catalog: {name}")
    for name in set(expected.get("projects", [])) - projects:
        err(f"project not in catalog: {name}")
    ids: set[str] = set()
    for c in expected.get("extractions", {}).get("commitments", []):
        cid = c["id"]
        m = COMMITMENT_ID.match(cid)
        if not m or m["doc"] != doc_id:
            err(f"commitment id {cid} is not of the form {doc_id}-cN")
        if cid in ids:
            err(f"duplicate commitment id {cid}")
        ids.add(cid)
        for field in ("who", "to_whom"):
            if c[field] not in participants:
                err(f"{cid}: {field} {c[field]!r} is not a participant")
        if c["project"] is not None and c["project"] not in expected.get("projects", []):
            err(f"{cid}: project {c['project']!r} is not one of the document's projects")
    for mention in expected.get("mentions", []):
        if mention not in earlier_commitments:
            err(f"mention {mention} is not a commitment of an earlier document")
    return ids


def check_company(company_dir: Path, stamp: bool, allow_pending: bool) -> tuple[list[str], list[str]]:
    """Run every check for one company; return the error and warning messages."""
    errors: list[str] = []
    warnings: list[str] = []
    people = {p["name"] for p in read_jsonl(company_dir / "people.jsonl")}
    projects = {p["name"] for p in read_jsonl(company_dir / "projects.jsonl")}
    expected_files = {p.stem: p for p in sorted((company_dir / "expected").glob("*.json"))}
    document_files = {p.stem: p for p in sorted((company_dir / "documents").glob("*.md"))}

    for doc_id in sorted(document_files.keys() - expected_files.keys()):
        errors.append(f"{doc_id}: document without expected file")
    if not allow_pending:
        for doc_id in sorted(expected_files.keys() - document_files.keys()):
            errors.append(f"{doc_id}: expected file without document")

    seen_commitments: set[str] = set()
    for doc_id, path in expected_files.items():
        expected = json.loads(path.read_text(encoding="utf-8"))
        if expected["document_id"] != doc_id:
            errors.append(f"{doc_id}: file name differs from document_id {expected['document_id']}")
        seen_commitments |= check_expected(expected, people, projects, seen_commitments, errors)
        for c in expected.get("extractions", {}).get("commitments", []):
            if len(content_words(c["what"])) < MIN_JUDGEABLE_WORDS:
                warnings.append(f"{c['id']}: `what` has fewer than {MIN_JUDGEABLE_WORDS} words of four letters or more, so the judge of the chat cannot tell it from others (docs/DATASET.md, \"Chat bank\")")

        if doc_id not in document_files:
            continue
        try:
            header, body = parse_document(document_files[doc_id])
        except ValueError as e:
            errors.append(f"{doc_id}: {e}")
            continue
        for key in HEADER_KEYS:
            if key not in header:
                errors.append(f"{doc_id}: header missing {key}")
        if header.get("id") != doc_id:
            errors.append(f"{doc_id}: header id is {header.get('id')!r}")
        for key in ("type", "date"):
            if header.get(key) != expected[key]:
                errors.append(f"{doc_id}: header {key} {header.get(key)!r} != expected {expected[key]!r}")
        header_people = [n.strip() for n in header.get("participants", "").split(",") if n.strip()]
        if sorted(header_people) != sorted(expected["participants"]):
            errors.append(f"{doc_id}: header participants differ from expected")
        if not body.strip():
            errors.append(f"{doc_id}: empty text")
            continue
        for c in expected.get("extractions", {}).get("commitments", []):
            if c["due_text"] and c["due_text"].lower() not in body.lower():
                warnings.append(f"{c['id']}: due_text {c['due_text']!r} not found in the text")
        digest = text_hash(body)
        if stamp:
            if expected.get("text_sha256") != digest:
                expected["text_sha256"] = digest
                path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"{doc_id}: text_sha256 stamped")
        elif expected.get("text_sha256") is None:
            errors.append(f"{doc_id}: text_sha256 is null (run with --stamp once the text is accepted)")
        elif expected["text_sha256"] != digest:
            errors.append(f"{doc_id}: text changed since text_sha256 was stamped")
    errors += [f"retrieval bank: {problem}" for problem in check_company_bank(company_dir)]
    errors += [f"chat bank: {problem}" for problem in check_company_chat_bank(company_dir)]
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("companies", nargs="*", help="company folders under data/ (default: all)")
    parser.add_argument("--stamp", action="store_true", help="fill in text_sha256 of every present document")
    parser.add_argument("--allow-pending", action="store_true", help="do not fail on expected files without a document yet")
    args = parser.parse_args()

    names = args.companies or sorted(p.parent.name for p in DATA_DIR.glob("*/company.json"))
    all_errors: list[str] = []
    for name in names:
        errors, warnings = check_company(DATA_DIR / name, args.stamp, args.allow_pending)
        all_errors += [f"[{name}] {e}" for e in errors]
        for w in warnings:
            print(f"[{name}] warning: {w}")
    for e in all_errors:
        print(e)
    print(f"{len(all_errors)} error(s)" if all_errors else "ok")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
