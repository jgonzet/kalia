"""Rule-based retrieval: picks the stored commitments a question asks about, without an LLM.

The rules follow one principle: they narrow the result only when they understand the phrase. A phrase they do not
understand leaves the result wider, never narrower, because the LLM that answers afterwards can discard what is
not needed but cannot recover what the retrieval left out.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from app.models import Catalog, Commitment, Person
from app.storage import Store

WEEK_DAYS_AFTER_TODAY = 6
BOSS_WORDS = ("jefe", "jefa")
INVOLVES_WORDS = ("involucr",)
# The only phrases about a week that filter; any other mention ("la semana pasada", "la semana del 19",
# "dentro de una semana") leaves the dates unfiltered.
THIS_WEEK = r"\besta semana\b|\bsemana actual\b|\b(?:en|durante) la semana\b"
NEXT_WEEK = r"\bsemana (?:que viene|proxima|siguiente|entrante)\b|\b(?:proxima|siguiente) semana\b"
# Parts of a name that are also ordinary words ("van" in "Van Houten"): they only count inside the full name.
NAME_PARTICLES = ("de", "del", "la", "las", "los", "el", "y", "van", "von", "da", "di", "le", "dos")
# What tells the question speaks of the user. "con" counts only before a person ("con Frink"); "me" only with a verb of
# promising or owing in the third person ("me prometió", "me deben"), not in a request ("¿me podés decir...?");
# "mi", "mis" and "yo" do not count: "para mi demo" says nothing about who promised what to whom.
FIRST_PERSON_WORDS = ("conmigo", "tengo", "tenemos", "prometi", "debo")
TO_THE_USER = (
    r"\bme (?:prometio|prometieron|promete|prometen|debe|deben|debia|debian|entrego|entregaron|mando|mandaron"
    r"|paso|pasaron|dio|dieron|pidio|pidieron|envio|enviaron)\b"
)
MANAGER_OF = r"\bjef[ea]s? de\b"


@dataclass(frozen=True)
class QuestionFilters:
    """What the rules found in a question. Empty fields mean "no filter"."""

    person_ids: tuple[str, ...] = ()
    involves_anyone: bool = False  # True: any commitment of the person; False: only those shared with the user
    due_from: date | None = None
    due_to: date | None = None


class RuleRetriever:
    """Retrieves commitments by person, boss and week; with no filter found it returns all of them.

    Several people in one question are joined with OR; the person and date filters are joined with AND.
    Without a catalog nothing can be recognised, so every commitment is returned.
    """

    def __init__(self, store: Store, today: date) -> None:
        self._store = store
        self._today = today

    def retrieve(self, question: str, catalog: Catalog | None = None) -> list[Commitment]:
        """Return the commitments that match the filters found in the question, ordered by id.

        `catalog` is the one the caller already read, to avoid reading it again; it is loaded from the store if omitted.
        """
        commitments = self._store.list_commitments()
        catalog = catalog or self._store.load_catalog()
        if catalog is None:
            return commitments
        filters = find_filters(question, catalog, self._today)
        user = _user_person(catalog)
        user_id = user.id if user else None
        return [c for c in commitments if _matches(c, filters, user_id)]


class AllCommitmentsRetriever:
    """Retrieves every commitment whatever the question: the baseline any real retrieval has to improve on."""

    def __init__(self, store: Store, today: date) -> None:
        self._store = store

    def retrieve(self, question: str, catalog: Catalog | None = None) -> list[Commitment]:
        """Return every stored commitment."""
        return self._store.list_commitments()


def find_filters(question: str, catalog: Catalog, today: date) -> QuestionFilters:
    """Read the person, boss and week filters out of the question text."""
    text = _normalize(question)
    text, manager_ids, unresolved_manager = _resolve_managers(text, catalog)
    person_ids = [p.id for p in _people_named(text, catalog)]
    for manager_id in manager_ids:
        if manager_id not in person_ids:
            person_ids.append(manager_id)
    if not unresolved_manager and any(_has_word(text, word) for word in BOSS_WORDS):
        boss_id = _boss_id(catalog)
        if boss_id and boss_id not in person_ids:
            person_ids.append(boss_id)
    due_from, due_to = _week_range(text, today)
    mentions_user = _has_first_person_word(text) or _is_with_a_person(text, catalog)
    return QuestionFilters(
        person_ids=tuple(person_ids),
        involves_anyone=any(word in text for word in INVOLVES_WORDS) or not mentions_user,
        due_from=due_from,
        due_to=due_to,
    )


def _week_range(text: str, today: date) -> tuple[date | None, date | None]:
    """Dates of "this week" or "next week" if the question says so in a phrase we know; otherwise no dates."""
    if re.search(NEXT_WEEK, text):
        return today + timedelta(days=WEEK_DAYS_AFTER_TODAY + 1), today + timedelta(days=2 * WEEK_DAYS_AFTER_TODAY + 1)
    if re.search(THIS_WEEK, text):
        return today, today + timedelta(days=WEEK_DAYS_AFTER_TODAY)
    return None, None


def _resolve_managers(text: str, catalog: Catalog) -> tuple[str, list[str], bool]:
    """Turn "el jefe de X" and "el jefe de mi jefe" into the manager's id and cut those phrases out of the text.

    Returns the text without the resolved phrases, the manager ids, and whether a "jefe de ..." phrase
    was left that names nobody known (then "jefe" must not be read as the user's boss).
    """
    people = {p.id: p for p in catalog.people}
    references = _name_references(catalog)
    alternatives = sorted(references, key=len, reverse=True) + ["mi jefe", "mi jefa"]
    pattern = re.compile(rf"{MANAGER_OF} (?P<ref>{'|'.join(re.escape(a) for a in alternatives)})\b")
    manager_ids: list[str] = []

    def resolve(match: re.Match[str]) -> str:
        reference = match["ref"]
        if reference in ("mi jefe", "mi jefa"):
            boss = people.get(_boss_id(catalog) or "")
            manager_id = boss.reports_to if boss else None
        else:
            manager_id = references[reference].reports_to
        if manager_id:
            manager_ids.append(manager_id)
        return " "

    text = pattern.sub(resolve, text)
    return text, manager_ids, re.search(MANAGER_OF, text) is not None


def _name_references(catalog: Catalog) -> dict[str, Person]:
    """Every full name, and every name part that belongs to one person only, mapped to that person."""
    return {_normalize(p.name): p for p in catalog.people} | _unique_name_parts(list(catalog.people))


def _unique_name_parts(people: list[Person]) -> dict[str, Person]:
    """Name parts that belong to one person only, without the particles that are also ordinary words."""
    owners: dict[str, dict[str, Person]] = {}
    for person in people:
        for part in _normalize(person.name).split():
            if part not in NAME_PARTICLES:
                owners.setdefault(part, {})[person.id] = person
    return {part: next(iter(by_id.values())) for part, by_id in owners.items() if len(by_id) == 1}


def _has_first_person_word(text: str) -> bool:
    return any(_has_word(text, word) for word in FIRST_PERSON_WORDS) or re.search(TO_THE_USER, text) is not None


def _is_with_a_person(text: str, catalog: Catalog) -> bool:
    """True if "con" is followed by a person or by "jefe" ("con Frink", "con el profesor", "con mi jefe")."""
    names = sorted(_name_references(catalog), key=len, reverse=True) + list(BOSS_WORDS)
    pattern = rf"\bcon (?:(?:el|la|los|las|mi|mis) )?(?:{'|'.join(re.escape(name) for name in names)})\b"
    return re.search(pattern, text) is not None


def _matches(commitment: Commitment, filters: QuestionFilters, user_id: str | None) -> bool:
    if filters.person_ids and not any(_involves(commitment, pid, filters.involves_anyone, user_id) for pid in filters.person_ids):
        return False
    if filters.due_from and filters.due_to:
        return commitment.due is not None and filters.due_from <= commitment.due <= filters.due_to
    return True


def _involves(commitment: Commitment, person_id: str, involves_anyone: bool, user_id: str | None) -> bool:
    parties = {commitment.who_id, commitment.to_whom_id}
    if person_id not in parties:
        return False
    return involves_anyone or user_id in parties


def _people_named(text: str, catalog: Catalog) -> list[Person]:
    """People whose full name, or a name part that no other person shares, appears in the text. The user is skipped."""
    user = _user_person(catalog)
    others = [p for p in catalog.people if p != user]
    unique_parts = _unique_name_parts(others)
    found: list[Person] = []
    for person in others:
        by_part = any(_has_word(text, part) for part, owner in unique_parts.items() if owner == person)
        if (_has_word(text, _normalize(person.name)) or by_part) and person not in found:
            found.append(person)
    return found


def _user_person(catalog: Catalog) -> Person | None:
    """The catalog entry of the user; `Catalog.user` holds the name, not the id."""
    return next((p for p in catalog.people if p.name == catalog.user), None)


def _boss_id(catalog: Catalog) -> str | None:
    user = _user_person(catalog)
    return user.reports_to if user else None


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _normalize(text: str) -> str:
    """Lowercase and strip accents, so "Frink" and "frínk" compare equal."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
