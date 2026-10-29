"""Measure what happens to a document that arrives after the first load, stage by stage, with a real LLM.

A development tool, not part of the app: real documents have no answer key. It is acceptance question 5 of
`docs/SPEC.md` (after one new document is ingested, does a related question return an answer that reflects it?). See
README ("Evaluate the ingestion").

    uv run scripts/quality/evals/evaluate_ingestion.py lamanija                                   with the extractor and the answerer of the environment
    uv run scripts/quality/evals/evaluate_ingestion.py lamanija --extractor-model a --answerer-model b
    uv run scripts/quality/evals/evaluate_ingestion.py lamanija --show --no-log                   print each answer; do not add the run to runs/metrics.jsonl

The questions are the `Q5` ones of `data/<company>/questions.jsonl` (the latest version of each). Only the documents those
questions need are loaded, so the run is shorter than a full load. Everything goes through the code of the app: each
document enters with `POST /documents` (extractor of the app, `LLMExtractor`) and each question with `POST /chat`
(`RuleRetriever` and `LLMAnswerer`), on a temporary database. The new document is the one the questions declare in
`after_held_out`. Each question is asked before and after it is ingested.

Four stages, measured apart so a loss or an addition can be placed:

1. Extraction: what the extractor returns for the new document, against its `expected` file (`evaluate_extraction.py`
   pairs them by people and due date): matched, missing, extra, wrong due date or project.
2. Storage: the commitments of the other documents must be the same after the ingestion, and what the extractor
   returned for the new document must be what got stored.
3. Retrieval: of the commitments the question expects from the new document and that stages 1 and 2 delivered, how many
   the chat retrieves (lost), and how many others of the new document it retrieves (added). Before the ingestion
   the chat must retrieve none of them (leaked).
4. Answer: of the ones retrieved, how many the answer says (judged by `scripts/quality/chat_judge.py`: rules, no second LLM), with
   what wrong people or due date; lines that look like a commitment nobody gave (invented, an upper bound); and the
   commitments of other documents that the answer leaves out, before and after, to see whether the new document pushed one out.

A commitment is blamed on the first stage that lost it: one the extractor missed is not counted again as lost in
retrieval. The LLMs run with the server's default temperature, so the numbers move between runs. Each run is appended to
`runs/metrics.jsonl` (stage "ingestion") with the commit, both models and the hash of both prompts.
"""

import argparse
import hashlib
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))  # make `app` and `scripts` importable

from scripts.quality import run_log  # noqa: E402
from app.answering.prompt import PROMPT_PATH  # noqa: E402
from app.config import Settings  # noqa: E402
from app.extraction import CommitmentExtractor  # noqa: E402
from app.extraction.llm_extractor import LLMExtractor  # noqa: E402
from app.ingestion.dataset import DatasetSource  # noqa: E402
from app.llm import LLMClient, build_llm  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Catalog, Commitment, Document  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402
from scripts.quality.chat_judge import Item, judge  # noqa: E402
from scripts.quality.evals.evaluate_extraction import PROMPT_FILE as EXTRACTION_PROMPT  # noqa: E402
from scripts.quality.evals.evaluate_extraction import DocumentResult, evaluate_document, load_answer_keys  # noqa: E402
from scripts.quality.evals.evaluate_retrieval import QuestionRecord, load_latest_questions  # noqa: E402

STAGE = "ingestion"
ACCEPTANCE = "Q5"


class RecordingExtractor:
    """Wraps the app's extractor and keeps what it returned for each document, to tell the extraction from the storage."""

    def __init__(self, inner: CommitmentExtractor) -> None:
        self._inner = inner
        self.returned: dict[str, list[Commitment]] = {}

    def extract(self, document: Document, catalog: Catalog) -> list[Commitment]:
        """Extract with the wrapped extractor; an LLM failure propagates and nothing is recorded."""
        commitments = self._inner.extract(document, catalog)
        self.returned[document.id] = commitments
        return commitments


@dataclass(frozen=True)
class Reading:
    """What `POST /chat` returned: the answer and the ids of the commitments it was built from."""

    answer: str
    degraded: bool
    retrieved: tuple[str, ...]
    seconds: float


@dataclass(frozen=True)
class ChatStages:
    """Stages 3 and 4 for one reading. `wanted` are the ids the question expects from the new document and that arrived stored."""

    wanted: int
    retrieved: int  # commitments of the new document in the list the chat retrieved
    retrieval_lost: int  # wanted but not retrieved
    retrieval_added: int  # retrieved from the new document without being wanted (before the ingestion: leaked)
    said: int  # wanted and retrieved, and said by the answer
    answer_lost: int  # wanted and retrieved, but not said
    wrong_people: int
    wrong_due: int
    others_missing: int  # retrieved from other documents and left out of the answer
    invented: int
    degraded: bool  # the LLM did not answer: the answer stage could not be measured
    seconds: float
    answer: str


@dataclass(frozen=True)
class StorageStage:
    others_before: int
    others_changed: int  # commitments of other documents that are gone, different, or new after the ingestion
    returned: int  # what the extractor returned for the new document
    stored: int
    new_lost: int  # returned by the extractor but not stored the same


@dataclass(frozen=True)
class QuestionOutcome:
    id: str
    question: str
    expected_new: int  # commitments of the new document the question expects
    before: ChatStages
    after: ChatStages


@dataclass(frozen=True)
class Outcome:
    new_document: str
    base_documents: list[str]
    base_failed: list[str]  # base documents whose extraction failed
    extraction_failed: bool  # the new document's extraction failed: stage 1 counts everything as missing
    extraction: DocumentResult
    storage: StorageStage
    questions: list[QuestionOutcome]


def document_of(commitment_id: str) -> str:
    """The id of the document a commitment id belongs to (`<document id>-cN`)."""
    return commitment_id.rsplit("-c", 1)[0]


def acceptance_questions(company_dir: Path) -> tuple[list[QuestionRecord], str]:
    """Read the Q5 questions and the one document they declare as arriving later."""
    questions = [q for q in load_latest_questions(company_dir / "questions.jsonl") if q.get("acceptance") == ACCEPTANCE and q["after_held_out"]]
    if not questions:
        raise ValueError(f"no {ACCEPTANCE} question with after_held_out in {company_dir / 'questions.jsonl'}")
    documents = {q["after_held_out"]["document"] for q in questions if q["after_held_out"]}
    if len(documents) != 1:
        raise ValueError(f"the {ACCEPTANCE} questions declare more than one document arriving later: {sorted(documents)}")
    return questions, documents.pop()


def base_documents(questions: list[QuestionRecord], new_document: str) -> list[str]:
    """The documents the questions need before the new one arrives, by id."""
    return sorted({document_of(cid) for q in questions for cid in q["expected"]} - {new_document})


def key(c: Commitment) -> tuple[str, str, str, str, date | None, str | None]:
    """What identifies a stored commitment for comparing before and after (not the owner)."""
    return (c.id, c.who_id, c.to_whom_id, c.what, c.due, c.project_id)


def storage_stage(before: list[Commitment], after: list[Commitment], returned: list[Commitment], new_document: str) -> StorageStage:
    """Compare the commitments of the other documents before and after, and what was returned with what was stored."""
    others_before = {key(c) for c in before if c.document_id != new_document}
    others_after = {key(c) for c in after if c.document_id != new_document}
    stored = {key(c) for c in after if c.document_id == new_document}
    return StorageStage(
        others_before=len(others_before),
        others_changed=len(others_before ^ others_after),
        returned=len(returned),
        stored=len(stored),
        new_lost=len({key(c) for c in returned} - stored),
    )


def wanted_ids(result: DocumentResult, expected_ids: list[str], stored_ids: set[str]) -> set[str]:
    """Ids, as the extractor numbered them, of the commitments a question expects from the new document and that arrived stored."""
    return {m.extracted_id for m in result.matches if m.expected_id in expected_ids and m.extracted_id in stored_ids}


def chat_stages(
    reading: Reading,
    stored: dict[str, Commitment],
    wanted: set[str],
    new_document: str,
    people: dict[str, str],
    user_id: str | None,
    year: int,
) -> ChatStages:
    """Split a reading into retrieval and answer counts (rules in the module docstring)."""
    retrieved = set(reading.retrieved)
    in_new = {i for i in retrieved if stored[i].document_id == new_document}
    wanted_here = wanted & retrieved
    said = wrong_people = wrong_due = others_missing = invented = 0
    if not reading.degraded:
        items = [Item(c.id, c.who_id, c.to_whom_id, c.what, c.due, True) for c in (stored[i] for i in reading.retrieved)]
        judgement = judge(reading.answer, items, people, user_id, year)
        said = len(wanted_here & {v.item.id for v in judgement.needed_present})
        wrong_people = sum(v.item.id in wanted_here for v in judgement.wrong_people)
        wrong_due = sum(v.item.id in wanted_here for v in judgement.wrong_due)
        others_missing = sum(v.item.id not in in_new for v in judgement.needed_missing)
        invented = len(judgement.invented)
    return ChatStages(
        wanted=len(wanted),
        retrieved=len(in_new),
        retrieval_lost=len(wanted - retrieved),
        retrieval_added=len(in_new - wanted),
        said=said,
        answer_lost=0 if reading.degraded else len(wanted_here) - said,
        wrong_people=wrong_people,
        wrong_due=wrong_due,
        others_missing=others_missing,
        invented=invented,
        degraded=reading.degraded,
        seconds=reading.seconds,
        answer=reading.answer,
    )


def ask(client: TestClient, question: str) -> Reading:
    """Ask the chat of the app one question."""
    started = time.monotonic()
    body = client.post("/chat", json={"question": question}).json()
    return Reading(body["answer"], body["degraded"], tuple(c["id"] for c in body["commitments"]), round(time.monotonic() - started, 1))


def ingest(client: TestClient, document: Document) -> bool:
    """Send one document to the app; return whether its commitments were extracted."""
    body = {"id": document.id, "type": document.type, "date": document.date.isoformat(), "participants": list(document.participants), "text": document.text}
    return bool(client.post("/documents", json=body).json()["extracted"])


def run_check(
    company_dir: Path,
    extractor: CommitmentExtractor,
    answer_llm: LLMClient,
    settings: Settings,
    log: Callable[[str], None] = print,
) -> Outcome:
    """Load the base documents, ask the Q5 questions, ingest the new document and ask again, all through the app."""
    questions, new_document = acceptance_questions(company_dir)
    source = DatasetSource(company_dir)
    catalog = source.catalog()
    today = date.fromisoformat(source.company["reference_date"])
    people = {p.id: p.name for p in catalog.people}
    user_id = next((p.id for p in catalog.people if p.name == catalog.user), None)
    key_of_new = load_answer_keys(company_dir, catalog)[new_document]
    base = base_documents(questions, new_document)
    recorder = RecordingExtractor(extractor)

    with tempfile.TemporaryDirectory() as tmp:
        store = SqliteStore(str(Path(tmp) / "ingestion.db"), settings.owner_id)
        store.save_catalog(catalog)
        client = TestClient(create_app(replace(settings, reference_date=today, sample_company=None), llm=answer_llm, store=store, extractor=recorder))

        base_failed = []
        for document_id in base:
            if not ingest(client, source.document(document_id)):
                base_failed.append(document_id)
                log(f"{document_id}: extraction failed")
        log(f"{len(base)} base documents loaded, {len(base_failed)} without commitments")
        before_commitments = store.list_commitments()
        stored_before = {c.id: c for c in before_commitments}
        readings_before = {q["id"]: ask(client, q["question"]) for q in questions}
        log("questions asked before the new document")

        extracted = ingest(client, source.document(new_document))
        log(f"{new_document}: {'extracted' if extracted else 'extraction failed'}")
        after_commitments = store.list_commitments()
        stored_after = {c.id: c for c in after_commitments}
        returned = recorder.returned.get(new_document, [])
        result = evaluate_document(key_of_new, returned)
        storage = storage_stage(before_commitments, after_commitments, returned, new_document)
        stored_new_ids = {c.id for c in after_commitments if c.document_id == new_document}

        outcomes = []
        for q in questions:
            held_out = q["after_held_out"]
            assert held_out is not None  # acceptance_questions keeps only those that have it
            expected_new = [cid for cid in held_out["expected"] if document_of(cid) == new_document]
            wanted = wanted_ids(result, expected_new, stored_new_ids)
            reading_after = ask(client, q["question"])
            outcomes.append(
                QuestionOutcome(
                    id=q["id"],
                    question=q["question"],
                    expected_new=len(expected_new),
                    before=chat_stages(readings_before[q["id"]], stored_before, set(), new_document, people, user_id, today.year),
                    after=chat_stages(reading_after, stored_after, wanted, new_document, people, user_id, today.year),
                )
            )
            log(f"{q['id']}: asked after the new document")
    return Outcome(new_document, base, base_failed, not extracted, result, storage, outcomes)


def format_report(outcome: Outcome, show: bool = False) -> str:
    """Render the four stages as text."""
    r = outcome.extraction
    wrong_due = sum(not m.due_ok for m in r.matches)
    wrong_project = sum(not m.project_ok for m in r.matches)
    s = outcome.storage
    lines = [
        f"Document that arrives late: {outcome.new_document}; base: {len(outcome.base_documents)} documents ({len(outcome.base_failed)} without commitments)",
        "",
        f"1. Extraction of {outcome.new_document}{' (FAILED: the LLM call did not work)' if outcome.extraction_failed else ''}",
        f"   expected {r.expected}, extracted {r.extracted}, matched {len(r.matches)}, missing {len(r.missing)}, extra {len(r.extra)}, "
        f"wrong due {wrong_due}, wrong project {wrong_project}",
        "2. Storage",
        f"   commitments of the other documents that changed: {s.others_changed} of {s.others_before} (must be 0); "
        f"of the new document, returned {s.returned}, stored {s.stored}, lost {s.new_lost}",
        "3. Retrieval (commitments of the new document)",
    ]
    for q in outcome.questions:
        b, a = q.before, q.after
        lines.append(
            f"   {q.id}: before, retrieved {b.retrieved} (must be 0); after, expected {q.expected_new}, wanted {a.wanted}, "
            f"retrieved {a.retrieved}, lost {a.retrieval_lost}, added {a.retrieval_added}"
        )
    lines.append("4. Answer")
    for q in outcome.questions:
        b, a = q.before, q.after
        after = "LLM did not answer" if a.degraded else (
            f"said {a.said} of {a.wanted - a.retrieval_lost}, lost {a.answer_lost}, wrong people {a.wrong_people}, wrong due {a.wrong_due}, "
            f"invented {a.invented}, others left out {a.others_missing}"
        )
        before = "LLM did not answer" if b.degraded else f"invented {b.invented}, others left out {b.others_missing}"
        lines.append(f"   {q.id}: before, {before}; after, {after}")
    if show:
        for q in outcome.questions:
            lines += ["", f"--- {q.id}: {q.question}", f"before: {q.before.answer}", f"after: {q.after.answer}"]
    return "\n".join(lines)


def sha(path: Path) -> str:
    """Short hash of a prompt file, to tell which prompt a run used."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.exists() else "none"


def log_run(
    outcome: Outcome,
    company: str,
    extractor_model: str,
    answerer_model: str,
    questions_version: str,
    path: Path = run_log.DEFAULT_LOG,
) -> run_log.RunRecord:
    """Add the run to the run log: both models and prompts, the totals of each stage and the counts of each question."""
    r = outcome.extraction
    qs = outcome.questions
    metrics = {
        "base_documents": len(outcome.base_documents),
        "base_failed": len(outcome.base_failed),
        "extraction_failed": float(outcome.extraction_failed),
        "extraction_expected": r.expected,
        "extraction_extracted": r.extracted,
        "extraction_matched": len(r.matches),
        "extraction_missing": len(r.missing),
        "extraction_extra": len(r.extra),
        "extraction_wrong_due": sum(not m.due_ok for m in r.matches),
        "extraction_wrong_project": sum(not m.project_ok for m in r.matches),
        "storage_others_changed": outcome.storage.others_changed,
        "storage_new_lost": outcome.storage.new_lost,
        "retrieval_wanted": sum(q.after.wanted for q in qs),
        "retrieval_lost": sum(q.after.retrieval_lost for q in qs),
        "retrieval_added": sum(q.after.retrieval_added for q in qs),
        "retrieval_leaked_before": sum(q.before.retrieved for q in qs),
        "answer_said": sum(q.after.said for q in qs),
        "answer_lost": sum(q.after.answer_lost for q in qs),
        "answer_wrong_people": sum(q.after.wrong_people for q in qs),
        "answer_wrong_due": sum(q.after.wrong_due for q in qs),
        "answer_invented_before": sum(q.before.invented for q in qs),
        "answer_invented_after": sum(q.after.invented for q in qs),
        "answer_others_missing_before": sum(q.before.others_missing for q in qs),
        "answer_others_missing_after": sum(q.after.others_missing for q in qs),
        "answer_degraded": sum(q.before.degraded + q.after.degraded for q in qs),
    }
    details = {
        f"extraction:{outcome.new_document}": {
            "expected": r.expected,
            "extracted": r.extracted,
            "matched": len(r.matches),
            "missing": len(r.missing),
            "extra": len(r.extra),
        }
    }
    for q in qs:
        details[q.id] = {
            "expected": q.expected_new,
            "wanted": q.after.wanted,
            "leaked_before": q.before.retrieved,
            "retrieved": q.after.retrieved,
            "retrieval_lost": q.after.retrieval_lost,
            "retrieval_added": q.after.retrieval_added,
            "said": q.after.said,
            "answer_lost": q.after.answer_lost,
            "wrong_people": q.after.wrong_people,
            "wrong_due": q.after.wrong_due,
            "invented_before": q.before.invented,
            "invented_after": q.after.invented,
            "others_missing_before": q.before.others_missing,
            "others_missing_after": q.after.others_missing,
            "degraded": q.before.degraded + q.after.degraded,
        }
    return run_log.append_run(
        stage=STAGE,
        params={
            "dataset": company,
            "extractor_model": extractor_model,
            "extractor_prompt_sha256": sha(EXTRACTION_PROMPT),
            "answerer_model": answerer_model,
            "answerer_prompt_sha256": sha(PROMPT_PATH),
            "questions_version": questions_version,
            "new_document": outcome.new_document,
        },
        metrics={k: float(v) for k, v in metrics.items()},
        details={k: {n: float(v) for n, v in d.items()} for k, d in details.items()},
        path=path,
    )


def main(argv: list[str]) -> int:
    defaults = Settings.from_env()
    extractor_settings = defaults.llm_for("extractor")
    answerer_settings = defaults.llm_for("answerer")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    parser.add_argument("--extractor-model", default=extractor_settings.model, help="model that extracts (default: the extractor's model)")
    parser.add_argument("--answerer-model", default=answerer_settings.model, help="model that answers (default: the answerer's model)")
    parser.add_argument("--show", action="store_true", help="print each answer, before and after")
    parser.add_argument("--no-log", action="store_true", help="do not add the run to runs/metrics.jsonl")
    args = parser.parse_args(argv)

    company_dir = ROOT / "data" / args.company
    if not (company_dir / "questions.jsonl").exists():
        print(f"no questions.jsonl at {company_dir}")
        return 1
    if "fake" in (extractor_settings.backend, answerer_settings.backend):
        print("A backend is fake: its answers are fixed text, so this only checks the plumbing")
    extractor = LLMExtractor(build_llm(replace(extractor_settings, model=args.extractor_model)), defaults.owner_id)
    answer_llm = build_llm(replace(answerer_settings, model=args.answerer_model))
    try:
        outcome = run_check(company_dir, extractor, answer_llm, defaults)
        questions, _ = acceptance_questions(company_dir)
    except ValueError as error:
        print(error)
        return 1
    print()
    print(format_report(outcome, args.show))
    if all(q.before.degraded and q.after.degraded for q in outcome.questions):
        print(f"\nevery answer came back degraded: the LLM did not answer (is {args.answerer_model} available at the answerer's endpoint?). Nothing was logged.")
        return 1
    if not args.no_log:
        version = ",".join(sorted({q["version"] for q in questions}))
        record = log_run(outcome, args.company, args.extractor_model, args.answerer_model, version)
        print(f"\nlogged in {run_log.DEFAULT_LOG.relative_to(ROOT)} (commit {record['git']['commit']}{'*' if record['git']['dirty'] else ''})")
    broken = outcome.storage.others_changed or any(q.before.retrieved for q in outcome.questions)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
