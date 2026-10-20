"""Measure what the LLM of the chat does with a list of commitments that is already chosen, with a real LLM.

A development tool, not part of the app: real users have no answer key. It is how a model or a prompt of the chat is
compared (the answering prompt is `app/prompts/answer_question.md`, the model is `LLM_MODEL`). See README ("Evaluate the chat").

    uv run scripts/evaluate_chat.py lamanija                                  the whole chat bank, with the model in the environment
    uv run scripts/evaluate_chat.py lamanija --model llama3.1
    uv run scripts/evaluate_chat.py lamanija --prompt /tmp/other_prompt.md   a prompt that is not the app's
    uv run scripts/evaluate_chat.py lamanija --category date --show           one category, with each answer and what was wrong in it
    uv run scripts/evaluate_chat.py lamanija --question skinner --no-log      the questions whose id contains this text

The questions are those of `data/<company>/chat_bank.jsonl` (the latest version of each). For each one the LLM is given a
controlled list, not the output of the retriever: the commitments the question needs plus some it does not (the noise),
all taken from the `expected` files, so the retrieval and the extraction cannot be blamed for what the answer lacks. The
question goes through `answer_from_commitments`, the same code the chat runs after it retrieves, and the answer is judged
by `scripts/chat_judge.py` (rules, no second LLM; what it can and cannot notice is in its docstring and checked by
`scripts/check_chat_judge.py`).

Per question it counts: the commitments needed (`needed`), how many the answer says (`said`), how many it leaves out
(`missing`), how many of the noise it says anyway (`extra`), how many it says with the wrong people (`people`) or the wrong
due date (`due`), how many say no date at all (`no date`) and how many lines look like a commitment nobody gave (`invented`, an upper bound).
Three more checks run apart from the bank: the answer when the LLM fails, comes back empty, or the prompt does not fit.
The LLM runs with the server's default temperature, so the same prompt gives different numbers each time: compare prompts
with repeated runs. Each run is appended to `runs/metrics.jsonl` (stage "chat_bank") with the commit, the model, a hash of the
prompt file and the bank version; `--no-log` skips it.
"""

import argparse
import hashlib
import json
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

import run_log  # noqa: E402  (scripts/ is already on sys.path when this file is run or imported by another script)
from app.answering import Answer  # noqa: E402
from app.answering.llm_answerer import DEGRADED_TEXT, TOO_LONG_TEXT, answer_from_commitments  # noqa: E402
from app.answering.prompt import PROMPT_PATH  # noqa: E402
from app.config import Settings  # noqa: E402
from app.ingestion.dataset import DatasetSource  # noqa: E402
from app.llm import LLMClient, LLMError, build_llm  # noqa: E402
from app.models import Catalog, Commitment  # noqa: E402
from chat_bank import BANK_FILE, ChatRecord, latest, read_bank  # noqa: E402
from chat_judge import Item, Judgement, judge  # noqa: E402
from evaluate_retrieval import build_store  # noqa: E402

STAGE = "chat_bank"
DEGRADATION_SAMPLE = 8  # commitments the degradation checks hand to the chat


@dataclass(frozen=True)
class QuestionResult:
    name: str  # the question id
    category: str
    question: str
    needed: int
    noise_given: int
    said: int  # needed commitments the answer says
    missing: int
    extra: int  # noise commitments the answer says anyway
    wrong_people: int  # needed commitments said with a person or a direction that is not theirs
    wrong_due: int  # needed commitments said with another due date
    no_due: int  # needed commitments said without any due date
    invented: int  # lines of the answer that claim a commitment nobody gave
    degraded: bool
    seconds: float
    answer: str
    lines: dict[str, list[str]]  # what was wrong, by kind: missing, extra, wrong_people, wrong_due, invented


@dataclass(frozen=True)
class Totals:
    questions: int
    needed: int
    noise_given: int
    said: int
    missing: int
    extra: int
    wrong_people: int
    wrong_due: int
    no_due: int
    invented: int
    degraded: int


@dataclass(frozen=True)
class DegradationCheck:
    name: str
    ok: bool
    detail: str


class _RaisingLLM:
    def complete(self, prompt: str) -> str:
        raise LLMError("simulated failure")


class _EmptyLLM:
    def complete(self, prompt: str) -> str:
        return "   "


class _MustNotBeCalledLLM:
    def complete(self, prompt: str) -> str:
        raise AssertionError("the LLM was called with a prompt that does not fit the context window")


def describe(item: Item, names: dict[str, str]) -> str:
    return f"{item.id} {names[item.who]} -> {names[item.to_whom]}: {item.what} ({item.due or 'sin fecha'})"


def measure(
    record: ChatRecord,
    commitments: dict[str, Commitment],
    catalog: Catalog,
    today: date,
    llm: LLMClient,
    prompt: Path,
    context_tokens: int | None,
) -> QuestionResult:
    """Give the LLM the needed commitments and the noise of a question and count what its answer does with them."""
    needed = set(record["needed"])
    given = [commitments[cid] for cid in sorted(needed | set(record["noise"]))]
    items = [Item(c.id, c.who_id, c.to_whom_id, c.what, c.due, c.id in needed) for c in given]
    started = time.monotonic()
    answer = answer_from_commitments(llm, record["question"], given, catalog, today, prompt, context_tokens)
    seconds = time.monotonic() - started
    people = {p.id: p.name for p in catalog.people}
    user_id = next((p.id for p in catalog.people if p.name == catalog.user), None)
    judgement = judge(answer.text, items, people, user_id, today.year)
    return _result(record, judgement, len(record["noise"]), answer, seconds, people)


def _result(record: ChatRecord, j: Judgement, noise_given: int, answer: Answer, seconds: float, people: dict[str, str]) -> QuestionResult:
    kinds = {
        "missing": [describe(v.item, people) for v in j.needed_missing],
        "extra": [describe(v.item, people) for v in j.noise_present],
        "wrong_people": [f"{describe(v.item, people)}  <-  {v.line}" for v in j.wrong_people],
        "wrong_due": [f"{describe(v.item, people)}  <-  {v.line}" for v in j.wrong_due],
        "invented": list(j.invented),
    }
    return QuestionResult(
        name=record["id"],
        category=record["category"],
        question=record["question"],
        needed=len(j.needed_present) + len(j.needed_missing),
        noise_given=noise_given,
        said=len(j.needed_present),
        missing=len(j.needed_missing),
        extra=len(j.noise_present),
        wrong_people=len(j.wrong_people),
        wrong_due=len(j.wrong_due),
        no_due=len(j.missing_due),
        invented=len(j.invented),
        degraded=answer.degraded,
        seconds=round(seconds, 1),
        answer=answer.text,
        lines=kinds,
    )


def check_degradation(commitments: list[Commitment], catalog: Catalog, today: date, prompt: Path) -> list[DegradationCheck]:
    """Run the three failures the chat must survive: the LLM raises, comes back empty, or the prompt does not fit."""
    cases: list[tuple[str, LLMClient, int | None, str]] = [
        ("the LLM fails", _RaisingLLM(), None, DEGRADED_TEXT),
        ("the LLM comes back empty", _EmptyLLM(), None, DEGRADED_TEXT),
        ("the prompt does not fit the context window", _MustNotBeCalledLLM(), 1, TOO_LONG_TEXT),
    ]
    checks = []
    for name, llm, context_tokens, text in cases:
        try:
            answer = answer_from_commitments(llm, "¿Qué compromisos hay?", commitments, catalog, today, prompt, context_tokens)
        except Exception as error:  # a degradation that raises is exactly what is being checked
            checks.append(DegradationCheck(name, False, f"raised {type(error).__name__}: {error}"))
            continue
        problems = []
        if not answer.degraded:
            problems.append("not marked degraded")
        if answer.text != text:
            problems.append("text is not the fixed one")
        if answer.commitments != commitments:
            problems.append("the commitments were not returned")
        checks.append(DegradationCheck(name, not problems, "; ".join(problems) or "degraded, with the fixed text and the commitments"))
    return checks


def evaluate(
    company_dir: Path,
    llm: LLMClient,
    prompt: Path = PROMPT_PATH,
    question_filters: list[str] | None = None,
    categories: list[str] | None = None,
    context_tokens: int | None = None,
    log: Callable[[str], None] = print,
) -> tuple[list[QuestionResult], list[DegradationCheck], list[ChatRecord]]:
    """Run the chat bank (or the part chosen) through `llm`, plus the degradation checks."""
    source = DatasetSource(company_dir)
    catalog = source.catalog()
    today = date.fromisoformat(source.company["reference_date"])
    records = [
        r
        for r in latest(read_bank(company_dir / BANK_FILE))
        if (not question_filters or any(f in r["id"] for f in question_filters)) and (not categories or r["category"] in categories)
    ]
    if not records:
        raise ValueError(f"no question of {BANK_FILE} matches what was asked")
    with tempfile.TemporaryDirectory() as tmp:
        store = build_store(str(Path(tmp) / "all.db"), company_dir, catalog, True, set())
        commitments = {c.id: c for c in store.list_commitments()}
    results: list[QuestionResult] = []
    for record in records:
        result = measure(record, commitments, catalog, today, llm, prompt, context_tokens)
        results.append(result)
        log(f"{result.name}: {result.said} of {result.needed} needed, {result.extra} extra ({result.seconds} s)")
    checks = check_degradation(list(commitments.values())[:DEGRADATION_SAMPLE], catalog, today, prompt)
    return results, checks, records


def totals(results: list[QuestionResult]) -> Totals:
    """Add up the counts of the questions (not their percentages)."""
    return Totals(
        questions=len(results),
        needed=sum(r.needed for r in results),
        noise_given=sum(r.noise_given for r in results),
        said=sum(r.said for r in results),
        missing=sum(r.missing for r in results),
        extra=sum(r.extra for r in results),
        wrong_people=sum(r.wrong_people for r in results),
        wrong_due=sum(r.wrong_due for r in results),
        no_due=sum(r.no_due for r in results),
        invented=sum(r.invented for r in results),
        degraded=sum(r.degraded for r in results),
    )


HEADER = f"{'':<28}{'questions':>10}{'needed':>8}{'said':>6}{'missing':>8}{'extra':>7}{'people':>7}{'due':>5}{'no date':>8}{'invented':>9}{'degraded':>9}"


def _row(label: str, t: Totals) -> str:
    return f"{label:<28}{t.questions:>10}{t.needed:>8}{t.said:>6}{t.missing:>8}{t.extra:>7}{t.wrong_people:>7}{t.wrong_due:>5}{t.no_due:>8}{t.invented:>9}{t.degraded:>9}"


def has_problem(r: QuestionResult) -> bool:
    return bool(r.missing or r.extra or r.wrong_people or r.wrong_due or r.invented or r.degraded)


def format_report(results: list[QuestionResult], checks: list[DegradationCheck], show: bool) -> str:
    """The counts per category and in total, the questions with something wrong, and the degradation checks."""
    by_category: dict[str, list[QuestionResult]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)
    lines = [HEADER] + [_row(category, totals(items)) for category, items in by_category.items()] + [_row("TOTAL", totals(results)), ""]
    lines.append("needed: commitments the question needs | said: of those, the answer says them | missing: it leaves them out")
    lines.append("extra: noise the answer says anyway | people / due: said with the wrong person or direction / the wrong due date")
    lines.append("no date: said without any date | invented: lines that look like a commitment nobody gave (an upper bound: read them with --show)")
    bad = [r for r in results if has_problem(r)]
    lines += ["", f"Questions with something wrong: {len(bad)} of {len(results)}"]
    for r in bad:
        lines.append(f"  {r.name:<44}{r.said:>3}/{r.needed:<3} missing {r.missing}, extra {r.extra}, people {r.wrong_people}, due {r.wrong_due}, invented {r.invented}" + (", DEGRADED" if r.degraded else ""))
    if checks:
        lines += ["", "Degradation checks:"] + [f"  {'ok  ' if c.ok else 'FAIL'} {c.name}: {c.detail}" for c in checks]
    if show:
        for r in results:
            lines += ["", f"=== {r.name} [{r.category}]: {r.question}", r.answer]
            for kind, found in r.lines.items():
                if found:
                    lines += [f"-- {kind}:"] + [f"   {line}" for line in found]
    return "\n".join(lines)


def log_run(results: list[QuestionResult], checks: list[DegradationCheck], company: str, model: str, prompt: Path, versions: str) -> run_log.RunRecord:
    """Add the evaluation to the run log: what was tried, the totals and the counts of each question."""
    t = totals(results)
    metrics = {k: float(v) for k, v in asdict(t).items()}
    metrics["degradation_checks_failed"] = float(sum(not c.ok for c in checks))
    return run_log.append_run(
        stage=STAGE,
        params={"dataset": company, "model": model, "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest()[:12], "bank_versions": versions},
        metrics=metrics,
        details={
            r.name: {
                "needed": r.needed,
                "said": r.said,
                "missing": r.missing,
                "extra": r.extra,
                "wrong_people": r.wrong_people,
                "wrong_due": r.wrong_due,
                "invented": r.invented,
            }
            for r in results
        },
    )


def main(argv: list[str]) -> int:
    defaults = Settings.from_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    parser.add_argument("--model", default=defaults.llm_model, help="model that answers (default: LLM_MODEL)")
    parser.add_argument("--prompt", type=Path, default=PROMPT_PATH, help="instructions of the answering prompt (default: the app's)")
    parser.add_argument("--question", action="append", dest="questions", help="only the questions whose id contains this text (repeatable)")
    parser.add_argument("--category", action="append", dest="categories", help="only this category (repeatable)")
    parser.add_argument("--show", action="store_true", help="print each answer and what was wrong in it")
    parser.add_argument("--out", type=Path, help="write the full results, answers included, to this JSON file")
    parser.add_argument("--no-log", action="store_true", help="do not add the run to runs/metrics.jsonl")
    args = parser.parse_args(argv)

    company_dir = ROOT / "data" / args.company
    if not (company_dir / BANK_FILE).exists():
        print(f"no {BANK_FILE} at {company_dir}: run scripts/chat_bank.py {args.company} first")
        return 1
    if defaults.llm_backend == "fake":
        print("LLM_BACKEND=fake: the answers are fixed text, so this only checks the plumbing")
    llm = build_llm(replace(defaults, llm_model=args.model))
    try:
        results, checks, records = evaluate(company_dir, llm, args.prompt, args.questions, args.categories, defaults.context_tokens)
    except ValueError as error:
        print(error)
        return 1
    print()
    print(format_report(results, checks, args.show))
    if all(r.degraded for r in results):
        print(f"\nevery answer came back degraded: the LLM did not answer (is {args.model} available at LLM_BASE_URL?). Nothing was logged.")
        return 1
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"results": [asdict(r) for r in results], "degradation": [asdict(c) for c in checks]}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.no_log:
        versions = ",".join(sorted({r["version"] for r in records}))
        record = log_run(results, checks, args.company, args.model, args.prompt, versions)
        print(f"\nlogged in {run_log.DEFAULT_LOG.relative_to(ROOT)} (commit {record['git']['commit']}{'*' if record['git']['dirty'] else ''})")
    return 1 if any(not c.ok for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
