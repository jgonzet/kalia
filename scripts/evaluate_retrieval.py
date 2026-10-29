"""Measure the retrieval against the questions of a synthetic dataset.

A development tool, not part of the app: real users have no answer key. See README ("Evaluate the retrieval").

    uv run scripts/evaluate_retrieval.py lamanija                       both suites; logs one run per suite
    uv run scripts/evaluate_retrieval.py lamanija --suite bank          only the retrieval bank (retrieval_bank.jsonl)
    uv run scripts/evaluate_retrieval.py lamanija --suite acceptance    only the acceptance questions (questions.jsonl)
    uv run scripts/evaluate_retrieval.py lamanija --retriever all       the baseline that returns every commitment
    uv run scripts/evaluate_retrieval.py lamanija --strict              exit code 1 if a commitment is missing where no known gap is declared
    uv run scripts/evaluate_retrieval.py lamanija --no-log              same, without adding runs to runs/metrics.jsonl

The retriever works on a temporary database built from the `expected` files, not on the stored commitments:
this way an extraction error cannot count against the retrieval. A question with `after_held_out` is measured
twice, before and after the held-out document. For each question the commitments retrieved are compared with its
`expected` ids: matched, missing (expected but not retrieved: the LLM cannot recover those) and extra (retrieved but
not needed: the LLM has to discard them). A question may declare a `known_gap` (the retrieval loses commitments there and
it is accepted for now): it is listed apart and does not fail `--strict`. Only counts are shown, per category and in total; the totals add up counts,
not percentages. If a question has several versions, the latest one is used. The reference date comes from `company.json`.
"""

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, NotRequired, TypedDict, cast

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

import run_log  # noqa: E402  (scripts/ is already on sys.path when this file is run)
from app.answering import Retriever  # noqa: E402
from app.answering.retrieval import AllCommitmentsRetriever, RuleRetriever  # noqa: E402
from app.ingestion.dataset import DatasetSource  # noqa: E402
from app.models import Catalog, Commitment  # noqa: E402
from app.storage.sqlite import SqliteStore  # noqa: E402
from evaluate_extraction import load_answer_keys  # noqa: E402
from scripts.dataset.retrieval_bank import AfterHeldOut  # noqa: E402

OWNER_ID = "evaluation"
SUITE_FILES = {"acceptance": "questions.jsonl", "bank": "retrieval_bank.jsonl"}
RETRIEVERS = {"rules": RuleRetriever, "all": AllCommitmentsRetriever}


class QuestionRecord(TypedDict):
    """One line of `questions.jsonl` or `retrieval_bank.jsonl`: the first has `acceptance`, the second `category`."""

    id: str
    version: str
    question: str
    expected: list[str]
    after_held_out: AfterHeldOut | None
    acceptance: NotRequired[str]
    category: NotRequired[str]
    known_gap: NotRequired[str]


@dataclass(frozen=True)
class QuestionResult:
    name: str  # question id, with "@after" for the run after the held-out document
    category: str
    expected: int
    retrieved: int
    matched: int
    known_gap: str | None = None

    @property
    def missing(self) -> int:
        return self.expected - self.matched

    @property
    def extra(self) -> int:
        return self.retrieved - self.matched


@dataclass(frozen=True)
class Counts:
    """Sums of the counts of several questions."""

    questions: int
    exact: int  # questions with nothing missing and nothing extra
    full_coverage: int  # questions with nothing missing
    expected: int
    retrieved: int
    matched: int

    @property
    def missing(self) -> int:
        return self.expected - self.matched

    @property
    def extra(self) -> int:
        return self.retrieved - self.matched

    @property
    def recall(self) -> float:
        return self.matched / self.expected if self.expected else 1.0

    @property
    def precision(self) -> float:
        return self.matched / self.retrieved if self.retrieved else 1.0


def add_up(results: list[QuestionResult]) -> Counts:
    return Counts(
        questions=len(results),
        exact=sum(r.missing == 0 and r.extra == 0 for r in results),
        full_coverage=sum(r.missing == 0 for r in results),
        expected=sum(r.expected for r in results),
        retrieved=sum(r.retrieved for r in results),
        matched=sum(r.matched for r in results),
    )


def load_latest_questions(path: Path) -> list[QuestionRecord]:
    """Read a questions file, keeping for each question id its highest version."""
    latest: dict[str, QuestionRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            question = cast(QuestionRecord, json.loads(line))
            if question["id"] not in latest or question["version"] > latest[question["id"]]["version"]:
                latest[question["id"]] = question
    return list(latest.values())


def build_store(db_path: str, company_dir: Path, catalog: Catalog, include_held_out: bool, held_out: set[str]) -> SqliteStore:
    """Create a database with the catalog and the commitments of the `expected` files (the held-out ones only if asked)."""
    store = SqliteStore(db_path, OWNER_ID)
    store.save_catalog(catalog)
    for document_id, key in load_answer_keys(company_dir, catalog).items():
        if document_id in held_out and not include_held_out:
            continue
        document_date = date.fromisoformat(json.loads((company_dir / "expected" / f"{document_id}.json").read_text(encoding="utf-8"))["date"])
        store.save_document_commitments(
            document_id,
            [Commitment(e.id, OWNER_ID, e.who_id, e.to_whom_id, e.what, e.due, e.project_id, document_id, document_date) for e in key.commitments],
        )
    return store


def measure(name: str, category: str, retriever: Retriever, question: str, expected: list[str], known_gap: str | None = None) -> QuestionResult:
    """Compare the ids the retriever returns for a question with the expected ones."""
    retrieved = {c.id for c in retriever.retrieve(question)}
    return QuestionResult(name, category, len(expected), len(retrieved), len(retrieved & set(expected)), known_gap)


def measure_suite(questions: list[QuestionRecord], retrievers: dict[str, Retriever]) -> list[QuestionResult]:
    """Measure every question on the initial database and, when it has `after_held_out`, on the one with the held-out document."""
    results = []
    for q in questions:
        category = q.get("category") or q.get("acceptance") or "uncategorised"
        gap = q.get("known_gap")
        results.append(measure(q["id"], category, retrievers["initial"], q["question"], q["expected"], gap))
        held_out = q.get("after_held_out")
        if held_out:
            results.append(measure(f"{q['id']}@after", category, retrievers["after"], q["question"], held_out["expected"], gap))
    return results


def percent(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "n/a"


def unexpected_missing(results: list[QuestionResult]) -> list[QuestionResult]:
    """The questions that lose commitments without a declared known gap."""
    return [r for r in results if r.missing and not r.known_gap]


def print_suite(name: str, results: list[QuestionResult]) -> None:
    by_category: dict[str, list[QuestionResult]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)
    print(f"== {name} ==")
    print(f"{'category':<14}{'questions':>10}{'expected':>9}{'retrieved':>10}{'missing':>8}{'extra':>7}{'recall':>8}{'precision':>10}")
    for category, items in by_category.items():
        c = add_up(items)
        print(f"{category:<14}{c.questions:>10}{c.expected:>9}{c.retrieved:>10}{c.missing:>8}{c.extra:>7}{percent(c.matched, c.expected):>8}{percent(c.matched, c.retrieved):>10}")
    total = add_up(results)
    print(f"{'total':<14}{total.questions:>10}{total.expected:>9}{total.retrieved:>10}{total.missing:>8}{total.extra:>7}{percent(total.matched, total.expected):>8}{percent(total.matched, total.retrieved):>10}")
    print(f"Questions with nothing missing: {total.full_coverage}/{total.questions}; exact (nothing missing, nothing extra): {total.exact}/{total.questions}")
    lost = unexpected_missing(results)
    print(f"Questions that lose commitments with no known gap declared: {len(lost)}" + (f" ({', '.join(r.name for r in lost)})" if lost else ""))
    gaps = [r for r in results if r.known_gap]
    for r in gaps:
        status = f"still missing {r.missing}" if r.missing else "now passes: remove its known_gap"
        print(f"Known gap {r.name}: {status} ({r.known_gap})")
    off = [r for r in results if r.missing or r.extra]
    if off:
        print(f"\n{'question with differences':<44}{'expected':>9}{'retrieved':>10}{'missing':>8}{'extra':>7}")
        for r in sorted(off, key=lambda r: (-r.missing, -r.extra)):
            print(f"{r.name:<44}{r.expected:>9}{r.retrieved:>10}{r.missing:>8}{r.extra:>7}")
    print()


def log_suite(suite: str, results: list[QuestionResult], questions: list[QuestionRecord], company: str, retriever_name: str, reference_date: date) -> None:
    total = add_up(results)
    metrics: dict[str, float] = {
        "questions": total.questions,
        "exact": total.exact,
        "full_coverage": total.full_coverage,
        "expected": total.expected,
        "retrieved": total.retrieved,
        "matched": total.matched,
        "missing": total.missing,
        "extra": total.extra,
        "recall": total.recall,
        "precision": total.precision,
        "known_gaps": len([r for r in results if r.known_gap]),
        "missing_unexpected": sum(r.missing for r in unexpected_missing(results)),
    }
    by_category: dict[str, list[QuestionResult]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)
    for category, items in by_category.items():
        c = add_up(items)
        metrics |= {f"recall.{category}": c.recall, f"missing.{category}": c.missing, f"extra.{category}": c.extra}
    record = run_log.append_run(
        stage="retrieval",
        params={
            "retriever": retriever_name,
            "dataset": company,
            "suite": suite,
            "questions_version": ",".join(sorted({q["version"] for q in questions})),
            "reference_date": reference_date.isoformat(),
        },
        metrics=metrics,
        details={r.name: {"expected": r.expected, "retrieved": r.retrieved, "matched": r.matched, "missing": r.missing, "extra": r.extra} for r in results},
    )
    print(f"logged {suite} in {run_log.DEFAULT_LOG.relative_to(ROOT)} (commit {record['git']['commit']}{'*' if record['git']['dirty'] else ''})")


def evaluate(
    company_dir: Path,
    suites: list[str],
    build_retriever: Callable[[SqliteStore, date], Retriever] = RuleRetriever,
) -> dict[str, tuple[list[QuestionRecord], list[QuestionResult]]]:
    """Measure the chosen suites with the retriever `build_retriever` makes; return, per suite, its questions and results."""
    source = DatasetSource(company_dir)
    catalog = source.catalog()
    reference_date = date.fromisoformat(source.company["reference_date"])
    held_out = set(source.company.get("held_out", []))
    outcome = {}
    with tempfile.TemporaryDirectory() as tmp:
        retrievers = {
            stage: build_retriever(build_store(str(Path(tmp) / f"{stage}.db"), company_dir, catalog, include, held_out), reference_date)
            for stage, include in (("initial", False), ("after", True))
        }
        for suite in suites:
            questions = load_latest_questions(company_dir / SUITE_FILES[suite])
            outcome[suite] = (questions, measure_suite(questions, retrievers))
    return outcome


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    parser.add_argument("--suite", choices=[*SUITE_FILES, "all"], default="all")
    parser.add_argument("--retriever", choices=list(RETRIEVERS), default="rules", help="'all' is the baseline a real retrieval has to beat")
    parser.add_argument("--strict", action="store_true", help="exit with code 1 if a question loses commitments without a declared known gap")
    parser.add_argument("--no-log", action="store_true", help="do not add the runs to runs/metrics.jsonl")
    args = parser.parse_args(argv)

    company_dir = ROOT / "data" / args.company
    if not company_dir.is_dir():
        print(f"no dataset at {company_dir}")
        return 1
    wanted = list(SUITE_FILES) if args.suite == "all" else [args.suite]
    suites = [s for s in wanted if (company_dir / SUITE_FILES[s]).exists()]
    for missing in sorted(set(wanted) - set(suites)):
        print(f"skipping {missing}: {SUITE_FILES[missing]} does not exist")
    if not suites:
        return 1

    reference_date = date.fromisoformat(DatasetSource(company_dir).company["reference_date"])
    retriever_class = RETRIEVERS[args.retriever]
    outcome = evaluate(company_dir, suites, retriever_class)
    failed = False
    for suite, (questions, results) in outcome.items():
        print_suite(suite, results)
        failed = failed or bool(unexpected_missing(results))
        if not args.no_log:
            log_suite(suite, results, questions, args.company, retriever_class.__name__, reference_date)
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
