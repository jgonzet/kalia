"""Build and check the retrieval bank of a synthetic dataset (`data/<company>/retrieval_bank.jsonl`).

    uv run scripts/retrieval_bank.py lamanija            add the questions of the spec that are not in the file yet
    uv run scripts/retrieval_bank.py lamanija --check    only verify the file against the spec and the `expected` files

Each question of the bank is defined in `scripts/retrieval_bank_<company>.py` as a condition over one commitment
(`Cond`). The correct answer is every commitment of the `expected` files that meets the condition; the condition's
text is stored in the file as `rule`. Nothing here imports `app/`: the answers must not come from the code under test.
Formats, definitions of each term and how to extend the bank: docs/DATASET.md ("Retrieval bank").

A published question is never edited: if the computed answer of a published question stops matching the file (the
`expected` files changed, or the spec did), the script stops and says so; the fix is a new `version` of that question.
The one thing that can change on a published question is its `known_gap`, a status and not part of the question.
"""

import argparse
import importlib
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, NotRequired, TypedDict, cast

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BANK_FILE = "retrieval_bank.jsonl"
FIRST_VERSION = "v1"


class AfterHeldOut(TypedDict):
    document: str
    expected: list[str]


class BankRecord(TypedDict):
    """One line of `retrieval_bank.jsonl`."""

    id: str
    version: str
    category: str
    question: str
    rule: str
    expected: list[str]
    after_held_out: AfterHeldOut | None
    known_gap: NotRequired[str]


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    role: str
    area: str
    level: int
    reports_to: str | None


@dataclass(frozen=True)
class Row:
    """One commitment of an `expected` file, with the catalog names translated to ids."""

    id: str
    document_id: str
    who_id: str
    to_whom_id: str
    due: date | None
    project_id: str | None
    what: str


@dataclass(frozen=True)
class Cond:
    """A condition over one commitment, with the text that describes it (stored as the question's `rule`)."""

    text: str
    test: Callable[[Row], bool]

    def __and__(self, other: "Cond") -> "Cond":
        return Cond(f"({self.text}) and ({other.text})", lambda r: self.test(r) and other.test(r))

    def __or__(self, other: "Cond") -> "Cond":
        return Cond(f"({self.text}) or ({other.text})", lambda r: self.test(r) or other.test(r))


@dataclass(frozen=True)
class Spec:
    """A question of the bank and the condition that defines its correct answer."""

    id: str
    category: str
    question: str
    cond: Cond
    version: str = FIRST_VERSION
    known_gap: str | None = None  # the retrieval is known to lose commitments here and it is accepted for now: why, and the issue


@dataclass(frozen=True)
class Context:
    """What the specs of a company can refer to: the reference date, the user and the catalog."""

    today: date
    user: Person
    people: tuple[Person, ...]
    projects: dict[str, str]  # project id -> name

    def person(self, name_part: str) -> Person:
        """Return the only person whose name contains the text (ignoring case); fail if none or several."""
        found = [p for p in self.people if name_part.lower() in p.name.lower()]
        if len(found) != 1:
            raise ValueError(f"{name_part!r} matches {len(found)} people, expected exactly 1")
        return found[0]

    def manager_of(self, person: Person) -> Person:
        return next(p for p in self.people if p.id == person.reports_to)

    @property
    def boss(self) -> Person:
        return self.manager_of(self.user)

    def peers(self) -> list[Person]:
        """People at the user's level with the same manager, the user left out."""
        return [p for p in self.people if p.reports_to == self.user.reports_to and p.level == self.user.level and p != self.user]

    def reports(self) -> list[Person]:
        return [p for p in self.people if p.reports_to == self.user.id]

    def area(self, name: str) -> list[Person]:
        return [p for p in self.people if p.area == name]

    def next_weekday(self, weekday: int) -> date:
        """The first date after today that falls on this weekday (Monday is 0)."""
        days = (weekday - self.today.weekday() - 1) % 7 + 1
        return self.today + timedelta(days=days)

    @property
    def month_end(self) -> date:
        first_of_next = (self.today.replace(day=1) + timedelta(days=32)).replace(day=1)
        return first_of_next - timedelta(days=1)


# --- conditions the specs are built from ---


def who(p: Person) -> Cond:
    return Cond(f"who = {p.name}", lambda r: r.who_id == p.id)


def to_whom(p: Person) -> Cond:
    return Cond(f"to_whom = {p.name}", lambda r: r.to_whom_id == p.id)


def involves(p: Person) -> Cond:
    return Cond(f"{p.name} is who or to_whom", lambda r: p.id in (r.who_id, r.to_whom_id))


def between(a: Person, b: Person) -> Cond:
    return Cond(f"{a.name} and {b.name} are the two parties, in either direction", lambda r: {r.who_id, r.to_whom_id} == {a.id, b.id})


def with_user(user: Person, p: Person) -> Cond:
    """The commitments between the user and a person, in either direction."""
    return Cond(f"between {user.name} and {p.name}, in either direction", lambda r: {r.who_id, r.to_whom_id} == {user.id, p.id})


def any_of(conds: Iterable[Cond], nobody: str) -> Cond:
    """True when any condition is; `nobody` is the text for an empty list, which matches nothing."""
    conds = list(conds)
    if not conds:
        return Cond(f"nothing matches ({nobody})", lambda r: False)
    return Cond(" or ".join(f"({c.text})" for c in conds), lambda r: any(c.test(r) for c in conds))


def due_on(day: date) -> Cond:
    return Cond(f"due = {day}", lambda r: r.due == day)


def due_between(first: date, last: date) -> Cond:
    return Cond(f"due from {first} to {last}, both included", lambda r: r.due is not None and first <= r.due <= last)


def dated() -> Cond:
    return Cond("has a due date", lambda r: r.due is not None)


def overdue(today: date) -> Cond:
    return Cond(f"due before {today} (overdue)", lambda r: r.due is not None and r.due < today)


def undated() -> Cond:
    return Cond("no due date", lambda r: r.due is None)


def in_project(projects: dict[str, str], name: str) -> Cond:
    project_id = next(pid for pid, n in projects.items() if n == name)
    return Cond(f"project = {name}", lambda r: r.project_id == project_id)


def no_project() -> Cond:
    return Cond("no project", lambda r: r.project_id is None)


def what_has(*words: str) -> Cond:
    """The text of `what` contains any of the words (ignoring case)."""
    return Cond(f"`what` contains any of: {', '.join(words)}", lambda r: any(w.lower() in r.what.lower() for w in words))


def nothing(reason: str) -> Cond:
    return Cond(f"nothing matches ({reason})", lambda r: False)


def everything() -> Cond:
    return Cond("every commitment (the question narrows nothing)", lambda r: True)


# --- reading the dataset ---


def read_bank(path: Path) -> list[BankRecord]:
    """Read the published bank file; an absent file means no questions yet."""
    return cast(list[BankRecord], read_jsonl(path)) if path.exists() else []


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_context(company_dir: Path) -> Context:
    company = json.loads((company_dir / "company.json").read_text(encoding="utf-8"))
    people = tuple(Person(p["id"], p["name"], p["role"], p["area"], p["level"], p["reports_to"]) for p in read_jsonl(company_dir / "people.jsonl"))
    user = next(p for p in people if p.id == company["user_id"])
    projects = {p["id"]: p["name"] for p in read_jsonl(company_dir / "projects.jsonl")}
    return Context(date.fromisoformat(company["reference_date"]), user, people, projects)


def load_rows(company_dir: Path, ctx: Context) -> list[Row]:
    """Read the commitments of every annotated `expected` file, in document order."""
    person_ids = {p.name: p.id for p in ctx.people}
    project_ids = {name: pid for pid, name in ctx.projects.items()}
    rows: list[Row] = []
    for path in sorted((company_dir / "expected").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data.get("extractions", {}).get("commitments", []):
            rows.append(
                Row(
                    id=c["id"],
                    document_id=data["document_id"],
                    who_id=person_ids[c["who"]],
                    to_whom_id=person_ids[c["to_whom"]],
                    due=date.fromisoformat(c["due"]) if c["due"] else None,
                    project_id=project_ids[c["project"]] if c["project"] else None,
                    what=c["what"],
                )
            )
    return rows


def load_specs(company: str, ctx: Context) -> list[Spec]:
    """Import `scripts/retrieval_bank_<company>.py` and ask it for the company's specs."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    module = importlib.import_module(f"retrieval_bank_{company}")
    return module.specs(ctx)


# --- building and checking ---


def compute_records(company_dir: Path, specs: list[Spec], ctx: Context) -> list[BankRecord]:
    """Compute the file record of every spec: its correct answer before and after the held-out document."""
    company = json.loads((company_dir / "company.json").read_text(encoding="utf-8"))
    held_out = company.get("held_out", [])
    if len(held_out) > 1:
        raise ValueError("the bank supports one held-out document, like questions.jsonl")
    rows = load_rows(company_dir, ctx)
    initial = [r for r in rows if r.document_id not in held_out]
    ids = [(s.id, s.version) for s in specs]
    if len(set(ids)) != len(ids):
        raise ValueError("two specs share an id and a version")
    records: list[BankRecord] = []
    for spec in specs:
        before = sorted(r.id for r in initial if spec.cond.test(r))
        after = sorted(r.id for r in rows if spec.cond.test(r))
        record: BankRecord = {
            "id": spec.id,
            "version": spec.version,
            "category": spec.category,
            "question": spec.question,
            "rule": spec.cond.text,
            "expected": before,
            "after_held_out": {"document": held_out[0], "expected": after} if held_out and after != before else None,
        }
        if spec.known_gap:
            record["known_gap"] = spec.known_gap
        records.append(record)
    return records


def _without_status(record: BankRecord) -> dict[str, object]:
    """The record without its `known_gap`, which is a status and not part of the question."""
    return {key: value for key, value in record.items() if key != "known_gap"}


def compare(computed: list[BankRecord], published: list[BankRecord]) -> list[str]:
    """List the differences between the computed records and the published file; `known_gap` is not compared."""
    problems = []
    by_key = {(r["id"], r["version"]): _without_status(r) for r in computed}
    for old in map(_without_status, published):
        key = (str(old["id"]), str(old["version"]))
        if key not in by_key:
            problems.append(f"{key[0]} {key[1]}: published but missing from the spec (a published question is never removed)")
        elif by_key[key] != old:
            changed = [f for f in old if by_key[key].get(f) != old[f]]
            problems.append(f"{key[0]} {key[1]}: differs from the file in {', '.join(changed)} (use a new version)")
    return problems


def build_bank(company_dir: Path) -> list[BankRecord]:
    """Compute the bank of a company from its spec and its `expected` files."""
    ctx = load_context(company_dir)
    return compute_records(company_dir, load_specs(company_dir.name, ctx), ctx)


def check_company_bank(company_dir: Path) -> list[str]:
    """Return the problems of the company's bank file (none if it is consistent); used by check_dataset.py."""
    path = company_dir / BANK_FILE
    if not path.exists():
        return []
    try:
        return compare(build_bank(company_dir), read_bank(path))
    except ModuleNotFoundError:
        return [f"{BANK_FILE} exists but scripts/retrieval_bank_{company_dir.name}.py does not"]
    except (KeyError, ValueError, OSError) as error:
        return [f"{BANK_FILE} cannot be computed: {type(error).__name__}: {error}"]


def print_summary(records: list[BankRecord], company_dir: Path, ctx: Context) -> None:
    """Print the size of the bank per category and what its questions leave uncovered."""
    by_category: dict[str, list[BankRecord]] = defaultdict(list)
    for r in records:
        by_category[r["category"]].append(r)
    print(f"{'category':<14}{'questions':>10}{'empty':>7}{'smallest':>9}{'median':>7}{'largest':>8}{'held-out changes':>18}")
    for category, items in by_category.items():
        sizes = [len(r["expected"]) for r in items]
        changes = sum(r["after_held_out"] is not None for r in items)
        print(f"{category:<14}{len(items):>10}{sizes.count(0):>7}{min(sizes):>9}{int(statistics.median(sizes)):>7}{max(sizes):>8}{changes:>18}")
    print(f"{'total':<14}{len(records):>10}")
    gaps = [r for r in records if r.get("known_gap")]
    print(f"Known gaps (accepted for now): {len(gaps)}" + (f" ({', '.join(r['id'] for r in gaps)})" if gaps else ""))

    rules = " ".join(r["rule"] for r in records)
    print()
    print("People named in no rule:", ", ".join(p.name for p in ctx.people if p.name not in rules) or "none")
    print("Projects named in no rule:", ", ".join(n for n in ctx.projects.values() if n not in rules) or "none")
    rows = load_rows(company_dir, ctx)
    used = {cid for r in records for cid in r["expected"]} | {cid for r in records if r["after_held_out"] for cid in r["after_held_out"]["expected"]}
    unused = [r for r in rows if r.id not in used]
    print(f"Commitments that no question expects: {len(unused)} of {len(rows)}" + (f" ({', '.join(r.id for r in unused)})" if unused else ""))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("company")
    parser.add_argument("--check", action="store_true", help="verify the file, do not write it")
    args = parser.parse_args(argv)

    company_dir = DATA_DIR / args.company
    if not (company_dir / "company.json").exists():
        print(f"no dataset at {company_dir}")
        return 1
    try:
        ctx = load_context(company_dir)
        computed = compute_records(company_dir, load_specs(args.company, ctx), ctx)
    except ModuleNotFoundError:
        print(f"scripts/retrieval_bank_{args.company}.py does not exist: write it with a specs(ctx) function first")
        return 1
    except (KeyError, ValueError, OSError) as error:
        print(f"cannot build the bank: {type(error).__name__}: {error}")
        return 1
    path = company_dir / BANK_FILE
    published = read_bank(path)

    problems = compare(computed, published)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    if not args.check:
        added = len(computed) - len(published)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in computed), encoding="utf-8")
        print(f"{BANK_FILE}: {len(computed)} questions ({added} added)\n")
    print_summary(computed, company_dir, ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
