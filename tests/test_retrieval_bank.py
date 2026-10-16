"""Tests of the engine that computes the correct answers of the retrieval bank (scripts/retrieval_bank.py).

They use a tiny made-up company, not the real dataset: an error here would corrupt the answer key without any warning.
"""

import json
from datetime import date
from pathlib import Path

import pytest

import retrieval_bank as rb
from retrieval_bank import Context, Person, Row, Spec

TODAY = date(2026, 10, 12)  # a Monday

BOSS = Person("p1", "Ana Boss", "Director", "Dir", 2, None)
USER = Person("p2", "Lalo User", "Producer", "Prod", 3, "p1")
PEER = Person("p3", "Pablo Peer", "QA", "Prod", 3, "p1")
OTHER = Person("p4", "Olga Other", "Artist", "Art", 3, "p5")
HEAD = Person("p5", "Hugo Head", "Director", "Art", 2, "p1")
PEOPLE = (BOSS, USER, PEER, OTHER, HEAD)
CTX = Context(TODAY, USER, PEOPLE, {"j1": "Alpha", "j2": "Beta"})


def row(id: str, who: Person, to: Person, due: date | None = None, project: str | None = None, what: str = "do it", doc: str = "d1") -> Row:
    return Row(id, doc, who.id, to.id, due, project, what)


def ids(cond: rb.Cond, rows: list[Row]) -> list[str]:
    return [r.id for r in rows if cond.test(r)]


# --- the context ---


def test_next_weekday_is_strictly_after_today() -> None:
    assert CTX.next_weekday(4) == date(2026, 10, 16)  # Friday
    assert CTX.next_weekday(6) == date(2026, 10, 18)  # Sunday
    assert CTX.next_weekday(0) == date(2026, 10, 19)  # today is Monday: the next one, not today


def test_month_end() -> None:
    assert CTX.month_end == date(2026, 10, 31)
    assert Context(date(2026, 12, 5), USER, PEOPLE, {}).month_end == date(2026, 12, 31)
    assert Context(date(2028, 2, 10), USER, PEOPLE, {}).month_end == date(2028, 2, 29)


def test_person_lookup_needs_exactly_one_match() -> None:
    assert CTX.person("peer") == PEER
    with pytest.raises(ValueError):
        CTX.person("zzz")
    with pytest.raises(ValueError):
        CTX.person("o")  # several names contain it


def test_hierarchy_helpers() -> None:
    assert CTX.boss == BOSS
    assert CTX.manager_of(OTHER) == HEAD
    assert CTX.peers() == [PEER]
    assert CTX.reports() == []
    assert CTX.area("Art") == [OTHER, HEAD]


# --- the conditions ---


def test_with_user_takes_both_directions_and_nothing_else() -> None:
    rows = [row("a", USER, PEER), row("b", PEER, USER), row("c", PEER, OTHER), row("d", USER, BOSS)]
    assert ids(rb.with_user(USER, PEER), rows) == ["a", "b"]


def test_between_leaves_the_user_out_of_the_rule() -> None:
    rows = [row("a", PEER, OTHER), row("b", OTHER, PEER), row("c", PEER, USER)]
    assert ids(rb.between(PEER, OTHER), rows) == ["a", "b"]


def test_who_to_whom_and_involves() -> None:
    rows = [row("a", USER, PEER), row("b", PEER, USER), row("c", OTHER, HEAD)]
    assert ids(rb.who(USER), rows) == ["a"]
    assert ids(rb.to_whom(USER), rows) == ["b"]
    assert ids(rb.involves(PEER), rows) == ["a", "b"]


def test_due_between_includes_both_ends() -> None:
    rows = [row(str(d), USER, PEER, date(2026, 10, d)) for d in (11, 12, 15, 18, 19)] + [row("none", USER, PEER)]
    assert ids(rb.due_between(date(2026, 10, 12), date(2026, 10, 18)), rows) == ["12", "15", "18"]


def test_overdue_is_strictly_before_today_and_undated_is_not_overdue() -> None:
    rows = [row("old", USER, PEER, date(2026, 10, 11)), row("today", USER, PEER, TODAY), row("none", USER, PEER)]
    assert ids(rb.overdue(TODAY), rows) == ["old"]
    assert ids(rb.undated(), rows) == ["none"]


def test_project_conditions() -> None:
    rows = [row("a", USER, PEER, project="j1"), row("b", USER, PEER, project="j2"), row("c", USER, PEER)]
    assert ids(rb.in_project(CTX.projects, "Alpha"), rows) == ["a"]
    assert ids(rb.no_project(), rows) == ["c"]


def test_what_has_ignores_case_and_takes_any_word() -> None:
    rows = [row("a", USER, PEER, what="Revisar el PRESUPUESTO"), row("b", USER, PEER, what="armar el costo"), row("c", USER, PEER, what="otra cosa")]
    assert ids(rb.what_has("presupuesto", "costo"), rows) == ["a", "b"]


def test_an_empty_any_of_matches_nothing() -> None:
    assert ids(rb.any_of([], "nobody reports to the user"), [row("a", USER, PEER)]) == []


def test_conditions_combine_and_describe_themselves() -> None:
    cond = rb.who(USER) & (rb.to_whom(PEER) | rb.to_whom(BOSS))
    rows = [row("a", USER, PEER), row("b", USER, BOSS), row("c", USER, OTHER), row("d", PEER, BOSS)]
    assert ids(cond, rows) == ["a", "b"]
    assert "Lalo User" in cond.text and "Pablo Peer" in cond.text and " and " in cond.text and " or " in cond.text


# --- building and checking the file ---


def write_company(root: Path, held_out: list[str], commitments: dict[str, list[dict]]) -> Path:
    company = root / "acme"
    (company / "expected").mkdir(parents=True)
    (company / "company.json").write_text(json.dumps({"user_id": "p2", "reference_date": "2026-10-12", "held_out": held_out}), encoding="utf-8")
    people = [{"id": p.id, "name": p.name, "role": p.role, "area": p.area, "level": p.level, "reports_to": p.reports_to} for p in PEOPLE]
    (company / "people.jsonl").write_text("\n".join(json.dumps(p) for p in people), encoding="utf-8")
    (company / "projects.jsonl").write_text(json.dumps({"id": "j1", "name": "Alpha"}), encoding="utf-8")
    for doc_id, items in commitments.items():
        body = {"document_id": doc_id, "extractions": {"commitments": items}}
        (company / "expected" / f"{doc_id}.json").write_text(json.dumps(body), encoding="utf-8")
    return company


def commitment(id: str, who: str, to: str, due: str | None = None) -> dict:
    return {"id": id, "who": who, "to_whom": to, "what": "x", "due": due, "due_text": None, "project": None}


@pytest.fixture
def company(tmp_path: Path) -> Path:
    return write_company(
        tmp_path,
        held_out=["d2"],
        commitments={
            "d1": [commitment("d1-c1", "Lalo User", "Pablo Peer"), commitment("d1-c2", "Pablo Peer", "Olga Other")],
            "d2": [commitment("d2-c1", "Pablo Peer", "Lalo User")],
        },
    )


def specs_for(ctx: Context) -> list[Spec]:
    return [
        Spec("with-peer", "person", "¿Qué tengo con Pablo?", rb.with_user(ctx.user, ctx.person("Pablo"))),
        Spec("other", "person", "¿Qué tiene Olga?", rb.involves(ctx.person("Olga"))),
    ]


def test_answers_exclude_the_held_out_document_and_record_the_change(company: Path) -> None:
    records = rb.compute_records(company, specs_for(rb.load_context(company)), rb.load_context(company))
    with_peer, other = records
    assert with_peer["expected"] == ["d1-c1"]
    assert with_peer["after_held_out"] == {"document": "d2", "expected": ["d1-c1", "d2-c1"]}
    assert other["expected"] == ["d1-c2"] and other["after_held_out"] is None  # the held-out document does not change it


def test_a_consistent_file_has_no_problems(company: Path) -> None:
    ctx = rb.load_context(company)
    records = rb.compute_records(company, specs_for(ctx), ctx)
    assert rb.compare(records, records) == []


def test_a_changed_answer_is_reported_and_asks_for_a_new_version(company: Path) -> None:
    ctx = rb.load_context(company)
    published = rb.compute_records(company, specs_for(ctx), ctx)
    published[0] = published[0] | {"expected": ["d1-c1", "d1-c2"]}
    problems = rb.compare(rb.compute_records(company, specs_for(ctx), ctx), published)
    assert len(problems) == 1 and "with-peer" in problems[0] and "new version" in problems[0]


def test_a_published_question_cannot_disappear_from_the_spec(company: Path) -> None:
    ctx = rb.load_context(company)
    published = rb.compute_records(company, specs_for(ctx), ctx)
    problems = rb.compare(rb.compute_records(company, specs_for(ctx)[:1], ctx), published)
    assert len(problems) == 1 and "other" in problems[0] and "never removed" in problems[0]


def test_a_new_question_is_not_a_problem(company: Path) -> None:
    ctx = rb.load_context(company)
    computed = rb.compute_records(company, specs_for(ctx), ctx)
    assert rb.compare(computed, computed[:1]) == []


def test_two_specs_with_the_same_id_and_version_are_rejected(company: Path) -> None:
    ctx = rb.load_context(company)
    spec = specs_for(ctx)[0]
    with pytest.raises(ValueError):
        rb.compute_records(company, [spec, spec], ctx)


# --- known gaps: a status of a question, not part of it ---


def test_a_known_gap_is_recorded_and_changing_it_is_not_a_problem(company: Path) -> None:
    ctx = rb.load_context(company)
    plain = specs_for(ctx)
    flagged = [Spec(s.id, s.category, s.question, s.cond, known_gap="needs the LLM, issue #22") if s.id == "other" else s for s in plain]
    published = rb.compute_records(company, plain, ctx)
    computed = rb.compute_records(company, flagged, ctx)
    assert computed[1]["known_gap"] == "needs the LLM, issue #22" and "known_gap" not in computed[0]
    assert rb.compare(computed, published) == []  # adding the status to a published question is allowed
    assert rb.compare(published, computed) == []  # and so is removing it
