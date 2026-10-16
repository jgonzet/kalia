"""Check that the retrieval bank notices when a rule of the rule-based retriever is broken. See README ("Evaluate the retrieval").

    uv run scripts/check_bank_sensitivity.py lamanija

For each mutation below, the script breaks one behaviour of `RuleRetriever` in memory (the code on disk is never touched),
measures the acceptance questions and the retrieval bank again, and counts the questions whose result changed. A mutation
that changes no question is NOT DETECTED: the bank would not notice if that behaviour broke by accident.

Run it after adding questions to the bank, and after adding or changing a rule of the retriever. Exit code 1 means a
mutation went undetected without being listed as a known blind spot; the fix is a new bank question for that behaviour
(docs/DATASET.md, "Adding questions"). A known blind spot that becomes detected is reported too, so its note can be removed.

Adding a rule to `app/answering/retrieval.py` means adding the mutation that breaks it here: the `patches` of a `Mutation`
replace attributes of that module (constants, functions) or the retriever itself. This script depends on the names in that
module; if it fails with an AttributeError after a refactor, update the patches.
It only applies to `RuleRetriever`: a retriever that works differently needs mutations of its own.
"""

import argparse
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # make `app` importable

import evaluate_retrieval  # noqa: E402  (scripts/ is already on sys.path when this file is run)
from app.answering import Retriever, retrieval  # noqa: E402
from app.answering.retrieval import AllCommitmentsRetriever, QuestionFilters  # noqa: E402
from app.models import Catalog, Commitment  # noqa: E402
from app.storage import Store  # noqa: E402

ORIGINAL_FIND_FILTERS = retrieval.find_filters
NEVER = r"(?!)"  # a regular expression that matches nothing

RetrieverFactory = Callable[[Store, date], Retriever]


class ReturnsNothing:
    def __init__(self, store: Store, today: date) -> None:
        pass

    def retrieve(self, question: str) -> list[Commitment]:
        return []


def _without_people(question: str, catalog: Catalog, today: date) -> QuestionFilters:
    return replace(ORIGINAL_FIND_FILTERS(question, catalog, today), person_ids=())


def _without_dates(question: str, catalog: Catalog, today: date) -> QuestionFilters:
    return replace(ORIGINAL_FIND_FILTERS(question, catalog, today), due_from=None, due_to=None)


def _first_person_only(question: str, catalog: Catalog, today: date) -> QuestionFilters:
    found = ORIGINAL_FIND_FILTERS(question, catalog, today)
    return replace(found, person_ids=found.person_ids[:1])


def _always_involves(question: str, catalog: Catalog, today: date) -> QuestionFilters:
    return replace(ORIGINAL_FIND_FILTERS(question, catalog, today), involves_anyone=True)


def _without_manager_phrases(text: str, catalog: Catalog) -> tuple[str, list[str], bool]:
    return text, [], False


def _any_week_is_this_week(text: str, today: date) -> tuple[date | None, date | None]:
    if "semana" in text:
        return today, today + timedelta(days=retrieval.WEEK_DAYS_AFTER_TODAY)
    return None, None


@dataclass(frozen=True)
class Mutation:
    name: str
    breaks: str  # what stops working, in words
    patches: dict[str, object] = field(default_factory=dict)  # attributes of app.answering.retrieval to replace
    build_retriever: RetrieverFactory | None = None  # replaces RuleRetriever altogether
    blind_spot: str | None = None  # why the bank cannot notice it, when that is known and accepted


MUTATIONS = [
    Mutation("ignores people", "no name is recognised", {"find_filters": _without_people}),
    Mutation("only the first person", "a question with two people uses only the first", {"find_filters": _first_person_only}),
    Mutation("treats 'van' as a name", "an ordinary word that is part of a name picks that person", {"NAME_PARTICLES": ()}),
    Mutation("ignores 'jefe'", "'jefe' no longer becomes the user's manager", {"BOSS_WORDS": ()}),
    Mutation("ignores 'jefe de X'", "'el jefe de Edna' is read as the user's boss", {"_resolve_managers": _without_manager_phrases}),
    Mutation("ignores 'esta semana'", "'esta semana' no longer filters by dates", {"THIS_WEEK": NEVER}),
    Mutation("ignores 'que viene'", "'la semana que viene' is read as this week", {"NEXT_WEEK": NEVER}),
    Mutation("any 'semana' is this week", "'la semana pasada' is read as this week", {"_week_range": _any_week_is_this_week}),
    Mutation("ignores dates", "no date filter at all", {"find_filters": _without_dates}),
    Mutation("week of 7 days after today", "the week ends a day later", {"WEEK_DAYS_AFTER_TODAY": 7}),
    Mutation(
        "week of 5 days after today",
        "the week ends a day earlier",
        {"WEEK_DAYS_AFTER_TODAY": 5},
        blind_spot="no commitment of the dataset is due on a weekend, so the sixth day changes no answer (tests/test_retrieval.py covers it)",
    ),
    Mutation("no first-person words", "'¿Qué le prometí a X?' brings the commitments without the user too", {"_has_first_person_word": lambda text: False}),
    Mutation("'con' is not enough", "'con X' brings the commitments without the user too", {"_is_with_a_person": lambda text, catalog: False}),
    Mutation("any 'con' counts", "'con el presupuesto' is read as being with the user", {"_is_with_a_person": lambda text, catalog: " con " in text}),
    Mutation("ignores 'involucr'", "'involucran a X' no longer brings the commitments without the user", {"INVOLVES_WORDS": ()}),
    Mutation("always 'involves'", "'con X' brings the commitments without the user too", {"find_filters": _always_involves}),
    Mutation("no accent folding", "'José' and 'jose' stop being the same name", {"_normalize": lambda text: text.lower()}),
    Mutation("returns everything", "the retriever filters nothing", build_retriever=AllCommitmentsRetriever),
    Mutation("returns nothing", "the retriever finds nothing", build_retriever=ReturnsNothing),
]


@contextmanager
def patched(mutation: Mutation) -> Iterator[None]:
    """Apply the mutation's patches to the retrieval module and undo them afterwards, whatever happens."""
    originals = {name: getattr(retrieval, name) for name in mutation.patches}  # AttributeError here = the name no longer exists
    try:
        for name, value in mutation.patches.items():
            setattr(retrieval, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(retrieval, name, value)


def snapshot(company_dir: Path, build_retriever: RetrieverFactory | None) -> dict[str, dict[str, tuple[int, int]]]:
    """Return, per suite and question, the (missing, extra) counts."""
    suites = list(evaluate_retrieval.SUITE_FILES)
    if build_retriever is None:
        outcome = evaluate_retrieval.evaluate(company_dir, suites)
    else:
        outcome = evaluate_retrieval.evaluate(company_dir, suites, build_retriever)
    return {suite: {r.name: (r.missing, r.extra) for r in results} for suite, (_, results) in outcome.items()}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    args = parser.parse_args(argv)

    company_dir = ROOT / "data" / args.company
    missing_files = [f for f in evaluate_retrieval.SUITE_FILES.values() if not (company_dir / f).exists()]
    if missing_files:
        print(f"missing in {company_dir}: {', '.join(missing_files)}")
        return 1

    baseline = snapshot(company_dir, None)
    print(f"{'mutation':<32}{'acceptance':>11}{'bank':>6}   result")
    problems = 0
    for mutation in MUTATIONS:
        with patched(mutation):
            mutated = snapshot(company_dir, mutation.build_retriever)
        changed = {suite: [q for q in baseline[suite] if baseline[suite][q] != mutated[suite].get(q)] for suite in baseline}
        detected = bool(changed["acceptance"] or changed["bank"])
        if detected and mutation.blind_spot:
            verdict = "detected, but listed as a blind spot: remove its note"
            problems += 1
        elif detected:
            verdict = "detected"
        elif mutation.blind_spot:
            verdict = f"NOT DETECTED (known: {mutation.blind_spot})"
        else:
            verdict = f"NOT DETECTED: add a bank question for '{mutation.breaks}'"
            problems += 1
        print(f"{mutation.name:<32}{len(changed['acceptance']):>11}{len(changed['bank']):>6}   {verdict}")
    print()
    print("acceptance / bank = questions whose result changed with the mutation")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
