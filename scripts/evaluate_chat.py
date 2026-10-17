"""Measure what the chat puts in its answers, with a real LLM, against the acceptance questions of a dataset.

A development tool, not part of the app: real users have no answer key. See README ("Evaluate the chat").
Use it to compare a model or a prompt on the chat: it is how the quality of the answers was measured in #18 and
what #16 grows into (its own bank of questions) and #21 puts together with the retrieval.

    uv run scripts/evaluate_chat.py lamanija --db runs/<name>.db            all the acceptance questions, with the model in the environment
    uv run scripts/evaluate_chat.py lamanija --db runs/<name>.db --model llama3.1
    uv run scripts/evaluate_chat.py lamanija --db runs/<name>.db --prompt /tmp/other_prompt.md   a prompt that is not the app's
    uv run scripts/evaluate_chat.py lamanija --db runs/<name>.db --question q2-semana --show    one question, with the answer in full
    uv run scripts/evaluate_chat.py lamanija --db runs/<name>.db --out runs/chat.json --no-log

What it does, per question of `questions.jsonl` (the latest version of each):
1. Takes a COPY of the database (`--db`, default `DB_PATH`), which must already hold the extracted commitments
   (README, "Evaluate the extraction"). The database you name is never written.
2. Runs the real chat on it: the rule retriever, the prompt and the LLM (`LLM_BASE_URL`, `LLM_MODEL`, `--model`).
3. Finds, in the database, the commitments each question needs, comparing by content (people and due date), not by id:
   the ids of a real extraction do not match those of the `expected` files. The ones that were not extracted are
   "lost in extraction": no later stage can recover them, so they are not counted against the chat.
4. Counts how many of the needed commitments the retriever brought, how many of those the answer contains, and how
   many commitments that were not needed the answer contains ("extra").
A question with `after_held_out` (acceptance question 5) is measured before and after the held-out document is
ingested and extracted into the copy; the extraction uses `--extraction-model` (default: the app's default model).

"The answer contains a commitment" is a heuristic: at least half of the words of its `what` (longer than three
letters, without accents) appear in the answer. It can miss a commitment the model rewrote a lot and cannot tell
that a person or a date was changed. Read the answers (`--show`, or `--out`) before trusting a difference of a few.
Only counts are printed. The LLM runs with the server's default temperature, so the same prompt gives different
numbers each time (about five of the 140 needed commitments between runs of the same prompt, more on one question):
a change smaller than that is not a finding. Each run is appended to `runs/metrics.jsonl` (stage "chat") with the commit,
the model, a hash of the prompt file and the database name; `--no-log` skips it.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

import run_log  # noqa: E402  (scripts/ is already on sys.path when this file is run or imported by another script)
from app.answering import Answerer  # noqa: E402
from app.answering.llm_answerer import LLMAnswerer  # noqa: E402
from app.answering.prompt import PROMPT_PATH  # noqa: E402
from app.answering.retrieval import RuleRetriever  # noqa: E402
from app.config import Settings  # noqa: E402
from app.extraction.llm_extractor import LLMExtractor  # noqa: E402
from app.extraction.run import extract_and_store  # noqa: E402
from app.ingestion import ingest_document  # noqa: E402
from app.ingestion.dataset import DatasetSource  # noqa: E402
from app.llm import LLMClient, build_llm  # noqa: E402
from app.models import Commitment  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402
from evaluate_extraction import AnswerKey, Expected, load_answer_keys, pair_expected  # noqa: E402
from evaluate_retrieval import load_latest_questions  # noqa: E402

IN_ANSWER_SHARE = 0.5  # share of the content words of a commitment that must appear in the answer
MIN_WORD_LENGTH = 4


@dataclass(frozen=True)
class QuestionResult:
    name: str  # the question id; "<id>@before" and "<id>@after" for a question measured around the held-out document
    question: str
    expected: int
    lost_in_extraction: int  # expected but not in the database: the chat cannot be blamed for them
    retrieved: int
    needed_retrieved: int  # needed commitments the retriever brought
    needed_in_answer: int  # needed commitments the answer contains (a heuristic, see the module docstring)
    extra_in_answer: int  # commitments that were not needed and the answer contains anyway
    degraded: bool
    seconds: float
    answer: str
    omitted: list[str]  # needed, retrieved and not in the answer, one line each
    extra: list[str]


@dataclass(frozen=True)
class Totals:
    questions: int
    expected: int
    lost_in_extraction: int
    retrieved: int
    needed_retrieved: int
    needed_in_answer: int
    extra_in_answer: int
    degraded: int


def content_words(text: str) -> set[str]:
    """Lowercase words of four letters or more, without accents: what two phrasings of one commitment share."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return {word for word in re.findall(r"[a-z0-9]+", plain) if len(word) >= MIN_WORD_LENGTH}


def is_in_answer(commitment: Commitment, answer: str) -> bool:
    """Whether the answer contains the commitment: half of the content words of its `what` appear in it."""
    words = content_words(commitment.what)
    return bool(words) and len(words & content_words(answer)) / len(words) >= IN_ANSWER_SHARE


def find_needed(expected_ids: list[str], keys: dict[str, AnswerKey], stored: list[Commitment]) -> tuple[list[Commitment], list[str]]:
    """Find, among the stored commitments, the ones the expected ids stand for; also return the expected ids with none."""
    wanted_by_document: dict[str, list[Expected]] = {}
    unknown: list[str] = []
    for expected_id in expected_ids:
        document_id = expected_id.rsplit("-c", 1)[0]
        key = keys.get(document_id)
        found = [e for e in key.commitments if e.id == expected_id] if key else []
        if found:
            wanted_by_document.setdefault(document_id, []).extend(found)
        else:
            unknown.append(expected_id)
    needed: list[Commitment] = []
    lost = list(unknown)
    for document_id, wanted in wanted_by_document.items():
        pairs = pair_expected(wanted, [c for c in stored if c.document_id == document_id])
        needed += [c for _, c in pairs]
        paired = {e.id for e, _ in pairs}
        lost += [e.id for e in wanted if e.id not in paired]
    return needed, lost


def measure(
    name: str,
    question: str,
    expected_ids: list[str],
    keys: dict[str, AnswerKey],
    store: SqliteStore,
    retriever: RuleRetriever,
    answerer: Answerer,
) -> QuestionResult:
    """Ask the chat one question and count what its answer has of the commitments the question needs."""
    needed, lost = find_needed(expected_ids, keys, store.list_commitments())
    retrieved = retriever.retrieve(question)
    started = time.monotonic()
    answer = answerer.answer(question)
    seconds = time.monotonic() - started
    needed_ids = {c.id for c in needed}
    needed_retrieved = [c for c in retrieved if c.id in needed_ids]
    in_answer = [c for c in retrieved if is_in_answer(c, answer.text)]

    def describe(c: Commitment) -> str:
        who, to_whom = answer.people.get(c.who_id, c.who_id), answer.people.get(c.to_whom_id, c.to_whom_id)
        return f"{c.id} {who} -> {to_whom}: {c.what} ({c.due or 'sin fecha'})"

    return QuestionResult(
        name=name,
        question=question,
        expected=len(expected_ids),
        lost_in_extraction=len(lost),
        retrieved=len(retrieved),
        needed_retrieved=len(needed_retrieved),
        needed_in_answer=sum(c.id in needed_ids for c in in_answer),
        extra_in_answer=sum(c.id not in needed_ids for c in in_answer),
        degraded=answer.degraded,
        seconds=round(seconds, 1),
        answer=answer.text,
        omitted=[describe(c) for c in needed_retrieved if c not in in_answer],
        extra=[describe(c) for c in in_answer if c.id not in needed_ids],
    )


def evaluate(
    company_dir: Path,
    db_path: str,
    owner_id: str,
    llm: LLMClient,
    extraction_llm: LLMClient,
    prompt: Path = PROMPT_PATH,
    question_ids: list[str] | None = None,
    log: Callable[[str], None] = print,
) -> list[QuestionResult]:
    """Measure the acceptance questions on a copy of the database; `db_path` itself is not written."""
    source = DatasetSource(company_dir)
    reference_date = date.fromisoformat(source.company["reference_date"])
    questions = [q for q in load_latest_questions(company_dir / "questions.jsonl") if not question_ids or q["id"] in question_ids]
    with tempfile.TemporaryDirectory() as tmp:
        copy = str(Path(tmp) / "copy.db")
        shutil.copyfile(db_path, copy)
        store = SqliteStore(copy, owner_id)
        catalog = store.load_catalog()
        if catalog is None:
            raise ValueError(f"{db_path} has no catalog: load the dataset and extract its commitments first (README)")
        keys = load_answer_keys(company_dir, catalog)
        retriever = RuleRetriever(store, reference_date)
        answerer = LLMAnswerer(llm, retriever, store, reference_date, prompt)

        # A held-out document that is already stored leaves nothing to measure "before", so its questions are skipped.
        already = {
            q["after_held_out"]["document"]
            for q in questions
            if q["after_held_out"] and store.get_document(q["after_held_out"]["document"])
        }
        runnable = [q for q in questions if not (q["after_held_out"] and q["after_held_out"]["document"] in already)]
        for document_id in sorted(already):
            log(f"skipping the questions around {document_id}: it is already in the database, so there is no 'before'")

        results: list[QuestionResult] = []
        for q in runnable:
            name = q["id"] + ("@before" if q["after_held_out"] else "")
            results.append(measure(name, q["question"], q["expected"], keys, store, retriever, answerer))
            log(f"{name}: {results[-1].needed_in_answer} of {results[-1].needed_retrieved} needed commitments in the answer ({results[-1].seconds} s)")

        after = [q for q in runnable if q["after_held_out"]]
        documents = sorted({q["after_held_out"]["document"] for q in after if q["after_held_out"]})
        ingested = True
        for document_id in documents:
            document = source.document(document_id)
            ingest_document(document, store)
            if not extract_and_store(document, LLMExtractor(extraction_llm, owner_id), store):
                log(f"the extraction of {document_id} failed: the questions measured after it are skipped")
                ingested = False
        for q in after if ingested else []:
            held_out = q["after_held_out"]
            if held_out:
                results.append(measure(q["id"] + "@after", q["question"], held_out["expected"], keys, store, retriever, answerer))
                log(f"{results[-1].name}: {results[-1].needed_in_answer} of {results[-1].needed_retrieved} needed commitments in the answer ({results[-1].seconds} s)")
    return results


def totals(results: list[QuestionResult]) -> Totals:
    """Add up the counts of every question (not their percentages)."""
    return Totals(
        questions=len(results),
        expected=sum(r.expected for r in results),
        lost_in_extraction=sum(r.lost_in_extraction for r in results),
        retrieved=sum(r.retrieved for r in results),
        needed_retrieved=sum(r.needed_retrieved for r in results),
        needed_in_answer=sum(r.needed_in_answer for r in results),
        extra_in_answer=sum(r.extra_in_answer for r in results),
        degraded=sum(r.degraded for r in results),
    )


def format_report(results: list[QuestionResult], show: bool) -> str:
    """The table of counts per question and the totals; with `show`, also each answer and what it omitted or added."""
    lines = [f"{'question':<20}{'expected':>9}{'lost':>6}{'retrieved':>10}{'needed':>8}{'in answer':>10}{'extra':>7}{'degraded':>9}{'seconds':>8}"]
    for r in results:
        lines.append(f"{r.name:<20}{r.expected:>9}{r.lost_in_extraction:>6}{r.retrieved:>10}{r.needed_retrieved:>8}{r.needed_in_answer:>10}{r.extra_in_answer:>7}{str(r.degraded):>9}{r.seconds:>8}")
    t = totals(results)
    lines.append(f"{'TOTAL':<20}{t.expected:>9}{t.lost_in_extraction:>6}{t.retrieved:>10}{t.needed_retrieved:>8}{t.needed_in_answer:>10}{t.extra_in_answer:>7}{t.degraded:>9}")
    lines.append("")
    lines.append("expected: commitments the question needs | lost: of those, not extracted (not the chat's fault) | needed: needed ones the retriever brought")
    lines.append("in answer: needed ones the answer contains (heuristic) | extra: not needed, but in the answer")
    if show:
        for r in results:
            lines += ["", f"=== {r.name}: {r.question}", r.answer]
            if r.omitted:
                lines += ["-- omitted:"] + [f"   {line}" for line in r.omitted]
            if r.extra:
                lines += ["-- extra:"] + [f"   {line}" for line in r.extra]
    return "\n".join(lines)


def log_run(results: list[QuestionResult], company: str, model: str, extraction_model: str, prompt: Path, db_path: str, questions_version: str) -> run_log.RunRecord:
    """Add the evaluation to the run log: what was tried, the totals and the counts of each question."""
    t = totals(results)
    return run_log.append_run(
        stage="chat",
        params={
            "dataset": company,
            "model": model,
            "extraction_model": extraction_model,
            "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest()[:12],
            "database": Path(db_path).name,
            "questions_version": questions_version,
        },
        metrics={k: float(v) for k, v in asdict(t).items()},
        details={
            r.name: {
                "expected": r.expected,
                "lost_in_extraction": r.lost_in_extraction,
                "retrieved": r.retrieved,
                "needed_retrieved": r.needed_retrieved,
                "needed_in_answer": r.needed_in_answer,
                "extra_in_answer": r.extra_in_answer,
            }
            for r in results
        },
    )


def main(argv: list[str]) -> int:
    defaults = Settings.from_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    parser.add_argument("--db", default=defaults.db_path, help="database with the extracted commitments; it is copied, never written (default: DB_PATH)")
    parser.add_argument("--model", default=defaults.llm_model, help="model that answers (default: LLM_MODEL)")
    parser.add_argument("--extraction-model", default=defaults.llm_model, help="model that extracts the held-out document (default: LLM_MODEL)")
    parser.add_argument("--prompt", type=Path, default=PROMPT_PATH, help="instructions of the answering prompt (default: the app's)")
    parser.add_argument("--question", action="append", dest="questions", help="measure only this question id (repeatable)")
    parser.add_argument("--show", action="store_true", help="print each answer and the commitments it omitted or added")
    parser.add_argument("--out", type=Path, help="write the full results, answers included, to this JSON file")
    parser.add_argument("--no-log", action="store_true", help="do not add the run to runs/metrics.jsonl")
    args = parser.parse_args(argv)

    company_dir = ROOT / "data" / args.company
    if not company_dir.is_dir():
        print(f"no dataset at {company_dir}")
        return 1
    if not Path(args.db).exists():
        print(f"no database at {args.db}")
        return 1
    if defaults.llm_backend == "fake":
        print("LLM_BACKEND=fake: the answers are fixed text, so this only checks the plumbing")
    llm = build_llm(replace(defaults, llm_model=args.model))
    extraction_llm = build_llm(replace(defaults, llm_model=args.extraction_model))
    try:
        results = evaluate(company_dir, args.db, defaults.owner_id, llm, extraction_llm, args.prompt, args.questions)
    except ValueError as error:
        print(error)
        return 1
    print()
    print(format_report(results, args.show))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.no_log:
        version = ",".join(sorted({q["version"] for q in load_latest_questions(company_dir / "questions.jsonl")}))
        record = log_run(results, args.company, args.model, args.extraction_model, args.prompt, args.db, version)
        print(f"\nlogged in {run_log.DEFAULT_LOG.relative_to(ROOT)} (commit {record['git']['commit']}{'*' if record['git']['dirty'] else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
