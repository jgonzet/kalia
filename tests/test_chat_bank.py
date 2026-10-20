"""Tests of the engine that computes the lists of the chat bank (scripts/chat_bank.py): the noise, the records and the check.

They use a tiny made-up company, not the real dataset: an error here would hand the LLM the wrong list without any warning.
"""

import json
from datetime import date
from pathlib import Path

import pytest

import retrieval_bank as rb
from chat_bank import BANK_FILE, ChatRecord, ChatSpec, Noise, check_company_chat_bank, compare, compute_records, latest, pick_noise, spread
from retrieval_bank import Context, Person, Row

TODAY = date(2026, 10, 12)
BOSS = Person("p1", "Ana Boss", "Director", "Dir", 2, None)
USER = Person("p2", "Lalo User", "Producer", "Prod", 3, "p1")
PEER = Person("p3", "Pablo Peer", "QA", "Prod", 3, "p1")
PEOPLE = (BOSS, USER, PEER)
CTX = Context(TODAY, USER, PEOPLE, {"j1": "Alpha"})


def row(id: str, who: Person, to: Person, due: date | None = None) -> Row:
    return Row(id, "d1", who.id, to.id, due, None, "x")


# a user-to-peer commitment, a peer-to-user one, and ten from the boss to the peer that serve as candidates for noise
ROWS = [row("a", USER, PEER), row("b", PEER, USER)] + [row(f"c{n:02d}", BOSS, PEER) for n in range(10)] + [row("u1", USER, BOSS), row("u2", USER, BOSS)]


def ids(rows: list[Row]) -> list[str]:
    return [r.id for r in rows]


# --- the noise ---


def test_spread_takes_evenly_spaced_candidates() -> None:
    candidates = [row(str(n), USER, PEER) for n in range(10)]
    assert ids(spread(candidates, 3)) == ["0", "3", "6"]


def test_spread_gives_all_when_there_are_not_more_than_asked_or_when_all_are_asked() -> None:
    candidates = [row(str(n), USER, PEER) for n in range(4)]
    assert ids(spread(candidates, 4)) == ids(spread(candidates, 9)) == ids(spread(candidates, None)) == ["0", "1", "2", "3"]


def test_noise_never_contains_what_is_needed() -> None:
    spec = ChatSpec("q", "c", "?", rb.with_user(USER, PEER), (Noise("everything", rb.everything()),), noise_size=None)
    noise = pick_noise(spec, ROWS)
    assert "a" not in noise and "b" not in noise and len(noise) == len(ROWS) - 2


def test_noise_is_capped_at_its_size_and_each_kind_gets_an_equal_share() -> None:
    spec = ChatSpec("q", "c", "?", rb.with_user(USER, PEER), (Noise("boss to peer", rb.who(BOSS)), Noise("user to boss", rb.who(USER) & rb.to_whom(BOSS))), noise_size=4)
    noise = pick_noise(spec, ROWS)
    assert len(noise) == 4
    assert sorted(noise.values()) == ["boss to peer", "boss to peer", "user to boss", "user to boss"]


def test_noise_is_never_more_than_its_size_even_when_the_shares_add_up_to_more() -> None:
    spec = ChatSpec("q", "c", "?", rb.with_user(USER, PEER), (Noise("boss to peer", rb.who(BOSS)), Noise("user to boss", rb.who(USER) & rb.to_whom(BOSS))), noise_size=3)
    assert len(pick_noise(spec, ROWS)) == 3  # two kinds of two each would be four


def test_a_commitment_of_two_kinds_is_given_once_with_the_first_reason() -> None:
    spec = ChatSpec("q", "c", "?", rb.with_user(USER, PEER), (Noise("first", rb.who(BOSS)), Noise("second", rb.who(BOSS))), noise_size=None)
    assert set(pick_noise(spec, ROWS).values()) == {"first"}


def test_no_noise_when_the_size_is_zero_or_there_are_no_kinds() -> None:
    assert pick_noise(ChatSpec("q", "c", "?", rb.who(USER), (Noise("all", rb.everything()),), noise_size=0), ROWS) == {}
    assert pick_noise(ChatSpec("q", "c", "?", rb.who(USER)), ROWS) == {}


def test_the_noise_is_the_same_every_time_and_sorted() -> None:
    spec = ChatSpec("q", "c", "?", rb.with_user(USER, PEER), (Noise("all", rb.everything()),), noise_size=5)
    assert pick_noise(spec, ROWS) == pick_noise(spec, ROWS) and list(pick_noise(spec, ROWS)) == sorted(pick_noise(spec, ROWS))


# --- the records ---


def write_company(root: Path, held_out: list[str]) -> Path:
    company = root / "acme"
    (company / "expected").mkdir(parents=True)
    (company / "company.json").write_text(json.dumps({"user_id": "p2", "reference_date": "2026-10-12", "held_out": held_out}), encoding="utf-8")
    people = [{"id": p.id, "name": p.name, "role": p.role, "area": p.area, "level": p.level, "reports_to": p.reports_to} for p in PEOPLE]
    (company / "people.jsonl").write_text("\n".join(json.dumps(p) for p in people), encoding="utf-8")
    (company / "projects.jsonl").write_text(json.dumps({"id": "j1", "name": "Alpha"}), encoding="utf-8")
    for doc_id, items in {"d1": [("d1-c1", "Lalo User", "Pablo Peer"), ("d1-c2", "Pablo Peer", "Ana Boss")], "d2": [("d2-c1", "Pablo Peer", "Lalo User")]}.items():
        commitments = [{"id": i, "who": w, "to_whom": t, "what": "x", "due": None, "due_text": None, "project": None} for i, w, t in items]
        body = {"document_id": doc_id, "extractions": {"commitments": commitments}}
        (company / "expected" / f"{doc_id}.json").write_text(json.dumps(body), encoding="utf-8")
    return company


def test_the_lists_are_those_of_the_whole_dataset_even_if_a_document_is_held_out(tmp_path: Path) -> None:
    company = write_company(tmp_path, held_out=["d2"])
    spec = ChatSpec("q", "c", "?", rb.with_user(USER, PEER), (Noise("others", rb.everything()),))
    [record] = compute_records(company, [spec], CTX)
    assert record["needed"] == ["d1-c1", "d2-c1"] and record["noise"] == {"d1-c2": "others"}
    assert "after_held_out" not in record


def test_a_record_keeps_the_rule_and_the_rules_of_the_noise_in_words(tmp_path: Path) -> None:
    company = write_company(tmp_path, held_out=[])
    spec = ChatSpec("q", "c", "?", rb.who(USER), (Noise("peer to anyone", rb.who(PEER)),))
    [record] = compute_records(company, [spec], CTX)
    assert "Lalo User" in record["rule"] and record["noise_rules"] == {"peer to anyone": "who = Pablo Peer"}


def test_two_specs_with_the_same_id_and_version_are_an_error(tmp_path: Path) -> None:
    company = write_company(tmp_path, held_out=[])
    spec = ChatSpec("q", "c", "?", rb.who(USER))
    with pytest.raises(ValueError, match="share an id"):
        compute_records(company, [spec, spec], CTX)


def test_two_kinds_of_noise_with_the_same_reason_are_an_error(tmp_path: Path) -> None:
    company = write_company(tmp_path, held_out=[])
    spec = ChatSpec("q", "c", "?", rb.who(USER), (Noise("same", rb.who(PEER)), Noise("same", rb.who(BOSS))))
    with pytest.raises(ValueError, match="share a reason"):
        compute_records(company, [spec], CTX)


# --- comparing with the published file ---


def record(id: str = "q", version: str = "v1", needed: list[str] | None = None, noise: dict[str, str] | None = None) -> ChatRecord:
    return {"id": id, "version": version, "category": "c", "question": "?", "rule": "r", "noise_rules": {}, "needed": needed or ["a"], "noise": noise or {}}


def test_an_unchanged_bank_has_no_problems_and_a_new_question_is_not_one() -> None:
    assert compare([record(), record("new")], [record()]) == []


def test_a_published_list_that_changed_is_a_problem_that_names_the_field() -> None:
    problems = compare([record(needed=["a", "b"])], [record(needed=["a"])])
    assert len(problems) == 1 and "needed" in problems[0] and "new version" in problems[0]


def test_a_published_noise_that_changed_is_a_problem() -> None:
    assert len(compare([record(noise={"x": "r"})], [record(noise={"y": "r"})])) == 1


def test_a_published_question_that_left_the_spec_is_a_problem_but_a_new_version_of_it_is_fine() -> None:
    assert len(compare([record("other")], [record()])) == 1
    assert compare([record(), record(version="v2")], [record()]) == []


def test_the_latest_version_of_each_question_is_the_one_kept() -> None:
    kept = latest([record("a", "v1"), record("a", "v2"), record("b", "v1")])
    assert sorted((r["id"], r["version"]) for r in kept) == [("a", "v2"), ("b", "v1")]


# --- the check used by check_dataset.py ---


def test_a_company_without_a_chat_bank_has_no_problems(tmp_path: Path) -> None:
    assert check_company_chat_bank(write_company(tmp_path, held_out=[])) == []


def test_a_chat_bank_without_its_spec_is_reported(tmp_path: Path) -> None:
    company = write_company(tmp_path, held_out=[])
    (company / BANK_FILE).write_text(json.dumps(record()) + "\n", encoding="utf-8")
    [problem] = check_company_chat_bank(company)
    assert BANK_FILE in problem and "does not" in problem
