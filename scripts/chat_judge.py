"""Judge an answer of the chat against the commitments the LLM was given, with rules and no second LLM.

Used by `scripts/evaluate_chat.py` and checked by `scripts/check_chat_judge.py`. For every commitment the LLM was given
(the ones the question needs and the noise) it decides whether the answer says it and, if so, whether it names the
right people and the right due date; and it finds the lines of the answer that claim a commitment nobody gave.

How it reads an answer: it splits it into lines (bullets and numbers taken off) and, for long lines, also into
sentences. Each commitment is matched with the line that shares most of its `what` words (at least half of them), with
the people and the date helping to tell apart commitments that read alike; a line stands for one commitment. On the line
it found it then looks for:
- people: those named are compared with the two the commitment has. A different person named while one of the two is
  missing is wrong; when a line names no one the commitment does not have, it is not judged. The direction (who
  promised, who received) is judged only on lines with an arrow (`->`), which the prompt asks for.
- the due date, in ISO, "6 de octubre" or "06/10"; "sin fecha" stands for no date. A date that differs is wrong; no date on
  the line is "missing", not wrong.
A line that names a person and has an arrow or a date, and stands for no given commitment, is "invented".

It is a heuristic with limits, and a narrow one: a set of rules written for the answers we have seen, not a general reader.
A paraphrase that shares fewer than half of the four-letter words of a commitment is not found (the commitment counts as
left out and its line as invented); a line stands for one commitment, so two said in one line count one; the direction is
judged only on lines with an arrow; dates are read in the forms of `dates_in` only; people by the name parts of four
letters or more (`MIN_NAME_PART`) and by the words in `USER_WORDS`. What the data must keep for it to work is in
docs/DATASET.md ("What the judge needs from the dataset"). Making it read many more forms is future work.
`scripts/check_chat_judge.py` shows what it tells apart and `tests/test_chat_judge.py` pins down its parts.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

PRESENT_SHARE = 0.5  # share of the content words of a commitment that must appear in a line for it to be said there
MIN_WORD_LENGTH = 4
MIN_NAME_PART = 4  # shorter parts of a name are ordinary words ("van" in "Milhouse Van Houten")
LONG_LINE = 160  # characters from which a line is also split into sentences
PEOPLE_BONUS = 0.2  # added to a line's score for each of: the two people named, the right date
USER_WORDS = {"yo", "me", "mi", "mis", "vos", "tu", "tus", "te", "ti"}
TITLES = {"profesor", "profesora", "doctor", "doctora", "senor", "senora"}
ARROW = re.compile(r"->|→|—>|=>")
MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}  # fmt: skip
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
WRITTEN_DATE = re.compile(r"\b(\d{1,2})\s+(?:de\s+)?([a-z]{3,10})\.?(?:\s+(?:de\s+)?(\d{4}))?\b")
SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
NO_DATE_PHRASES = ("sin fecha", "sin plazo", "no tiene fecha", "sin fecha limite")
BULLET = re.compile(r"^\s*(?:[-*•–]+|\d+[.)])\s*")
SENTENCE_BREAK = re.compile(r"(?<=[.;!?])\s+")

PersonVerdict = Literal["ok", "wrong", "unclear"]
DateVerdict = Literal["ok", "wrong", "missing"]


@dataclass(frozen=True)
class Item:
    """A commitment the LLM was given; `needed` says whether the question needs it or it is noise. People are catalog ids."""

    id: str
    who: str
    to_whom: str
    what: str
    due: date | None
    needed: bool


@dataclass(frozen=True)
class Verdict:
    """What the answer does with one commitment it was given."""

    item: Item
    present: bool
    people: PersonVerdict = "unclear"
    due: DateVerdict = "missing"
    line: str = ""  # the line of the answer that stands for it


@dataclass(frozen=True)
class Judgement:
    verdicts: list[Verdict]
    invented: list[str] = field(default_factory=list)  # lines of the answer that claim a commitment nobody gave

    @property
    def needed_present(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.item.needed and v.present]

    @property
    def needed_missing(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.item.needed and not v.present]

    @property
    def noise_present(self) -> list[Verdict]:
        return [v for v in self.verdicts if not v.item.needed and v.present]

    @property
    def wrong_people(self) -> list[Verdict]:
        return [v for v in self.needed_present if v.people == "wrong"]

    @property
    def wrong_due(self) -> list[Verdict]:
        return [v for v in self.needed_present if v.due == "wrong"]

    @property
    def missing_due(self) -> list[Verdict]:
        return [v for v in self.needed_present if v.due == "missing"]


def plain(text: str) -> str:
    """Lowercase text without accents."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def content_words(text: str) -> set[str]:
    """Words of four letters or more, lowercase and without accents: what two phrasings of one commitment share."""
    return {word for word in re.findall(r"[a-z0-9]+", plain(text)) if len(word) >= MIN_WORD_LENGTH}


def split_answer(answer: str) -> list[str]:
    """Candidate lines: each line of the answer without its bullet, and the sentences of the long ones."""
    candidates: list[str] = []
    for raw in answer.splitlines():
        line = BULLET.sub("", raw).strip().strip("*_# ").strip()
        if not line:
            continue
        candidates.append(line)
        if len(line) > LONG_LINE:
            candidates += [s.strip() for s in SENTENCE_BREAK.split(line) if s.strip() and s.strip() != line]
    return candidates


def person_aliases(people: dict[str, str], user_id: str | None) -> dict[str, set[str]]:
    """Map each word that can stand for someone (full name, a part of it) to the ids it can mean; a shared part means several."""
    aliases: dict[str, set[str]] = {}
    for person_id, name in people.items():
        words = [plain(name)] + [w for w in re.findall(r"[a-z]+", plain(name)) if len(w) >= MIN_NAME_PART and w not in TITLES]
        for word in words:
            aliases.setdefault(word, set()).add(person_id)
    if user_id is not None:
        for word in USER_WORDS:
            aliases.setdefault(word, set()).add(user_id)
    return aliases


def people_named(text: str, aliases: dict[str, set[str]]) -> set[str]:
    """Ids of the people a text names: by full name, by a part of it, or by the words that mean the user.

    The longest alias is looked for first and what it matched is not read again, so "Selma Bouvier" means Selma only,
    while "Bouvier" alone means every Bouvier.
    """
    normal = plain(text)
    named: set[str] = set()
    for word in sorted(aliases, key=len, reverse=True):
        pattern = re.compile(rf"(?<![a-z]){re.escape(word)}(?![a-z])")
        if pattern.search(normal):
            named |= aliases[word]
            normal = pattern.sub(" " * len(word), normal)
    return named


def dates_in(text: str, year: int) -> set[date]:
    """The dates a text writes: ISO, "6 de octubre" (in `year` if it has none) or "06/10"."""
    normal = plain(text)
    found: set[date] = set()
    for y, m, d in ISO_DATE.findall(normal):
        _add(found, int(y), int(m), int(d))
    for d, month, y in WRITTEN_DATE.findall(normal):
        if month in MONTHS:
            _add(found, int(y) if y else year, MONTHS[month], int(d))
    for d, m, y in SLASH_DATE.findall(normal):
        _add(found, _full_year(y, year), int(m), int(d))
    return found


def _full_year(text: str, default: int) -> int:
    if not text:
        return default
    return int(text) + 2000 if len(text) == 2 else int(text)


def _add(found: set[date], y: int, m: int, d: int) -> None:
    try:
        found.add(date(y, m, d))
    except ValueError:
        pass


def judge(answer: str, items: list[Item], people: dict[str, str], user_id: str | None, year: int) -> Judgement:
    """Judge the answer against the commitments the LLM was given; `year` is the one a date without a year means."""
    lines = split_answer(answer)
    aliases = person_aliases(people, user_id)
    named = [people_named(line, aliases) for line in lines]
    dates = [dates_in(line, year) for line in lines]
    words = [content_words(line) for line in lines]

    scored: list[tuple[float, int, int]] = []  # (score, item index, line index)
    for i, item in enumerate(items):
        item_words = content_words(item.what)
        if not item_words:
            continue
        for j in range(len(lines)):
            share = len(item_words & words[j]) / len(item_words)
            if share < PRESENT_SHARE:
                continue
            both_named = {item.who, item.to_whom} <= named[j]
            right_date = item.due in dates[j] if item.due else not dates[j]
            score = share + PEOPLE_BONUS * both_named + PEOPLE_BONUS * right_date - len(lines[j]) / 100_000
            scored.append((score, i, j))
    taken_items: dict[int, int] = {}
    taken_lines: set[int] = set()
    for _, i, j in sorted(scored, reverse=True):
        if i not in taken_items and j not in taken_lines:
            taken_items[i] = j
            taken_lines.add(j)

    verdicts: list[Verdict] = []
    for i, item in enumerate(items):
        if i not in taken_items:
            verdicts.append(Verdict(item, present=False))
            continue
        j = taken_items[i]
        verdicts.append(
            Verdict(item, True, _people_verdict(item, lines[j], named[j], aliases), _due_verdict(item, lines[j], dates[j]), lines[j])
        )
    invented = [lines[j] for j in range(len(lines)) if j not in taken_lines and _claims_a_commitment(lines[j], named[j], dates[j])]
    return Judgement(verdicts, invented)


def _people_verdict(item: Item, line: str, named: set[str], aliases: dict[str, set[str]]) -> PersonVerdict:
    """Whether the line names the two people of the commitment, and in the right direction when it has an arrow."""
    expected = {item.who, item.to_whom}
    if not expected <= named:
        return "wrong" if named - expected else "unclear"
    parts = ARROW.split(line, maxsplit=1)
    if len(parts) == 2 and item.who != item.to_whom:
        left, right = people_named(parts[0], aliases), people_named(parts[1], aliases)
        if item.to_whom in left and item.who in right and not (item.who in left and item.to_whom in right):
            return "wrong"
    return "ok"


def _due_verdict(item: Item, line: str, dates: set[date]) -> DateVerdict:
    """Whether the line gives the commitment's due date: ok, a different one (wrong) or none (missing)."""
    if item.due is None:
        return "wrong" if dates else "ok"
    if item.due in dates:
        return "ok"
    said_no_date = any(phrase in plain(line) for phrase in NO_DATE_PHRASES)
    return "wrong" if dates or said_no_date else "missing"


def _claims_a_commitment(line: str, named: set[str], dates: set[date]) -> bool:
    """Whether a line that stands for no given commitment reads like one: it names a person and has an arrow or a date."""
    return bool(named) and (bool(ARROW.search(line)) or bool(dates))
