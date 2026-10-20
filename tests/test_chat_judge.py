"""Tests of the parts of the judge of the chat (scripts/chat_judge.py): lines, dates, names and the matching of a line to a commitment.

`scripts/check_chat_judge.py` (which the CI also runs) checks the whole judge on whole answers; these pin down the pieces
it is built from, so a change that breaks one fails here with a name instead of with a count that moved.
"""

from datetime import date

import pytest

from chat_judge import Item, Judgement, content_words, dates_in, judge, people_named, person_aliases, plain, split_answer

PEOPLE = {"u": "Ana Ruiz", "b": "Bruno Vega", "l": "Lucía Pérez", "m": "Marta Pérez", "s": "Profesor Soto", "v": "Víctor Van Der Berg"}
ALIASES = person_aliases(PEOPLE, "u")


def item(id: str, who: str, to: str, what: str, due: date | None, needed: bool = True) -> Item:
    return Item(id, who, to, what, due, needed)


# --- text ---


def test_plain_is_lowercase_without_accents() -> None:
    assert plain("Reunión DE Planificación") == "reunion de planificacion"


def test_content_words_are_the_long_ones_without_accents() -> None:
    assert content_words("Armar la propuesta de reconexión") == {"armar", "propuesta", "reconexion"}


def test_split_answer_takes_off_bullets_numbers_and_markdown() -> None:
    answer = "## Alfa\n- uno dos\n* tres cuatro\n1. cinco seis\n2) siete ocho\n\n**nueve diez**"
    assert split_answer(answer) == ["Alfa", "uno dos", "tres cuatro", "cinco seis", "siete ocho", "nueve diez"]


def test_a_long_line_is_also_split_into_sentences() -> None:
    long_line = "Ana le prometió algo a Bruno para mañana. " * 6
    pieces = split_answer(long_line)
    assert pieces[0] == long_line.strip() and len(pieces) > 1 and pieces[1] == "Ana le prometió algo a Bruno para mañana."


def test_a_short_line_is_not_split() -> None:
    assert split_answer("Una. Dos. Tres.") == ["Una. Dos. Tres."]


# --- dates ---


@pytest.mark.parametrize(
    "text",
    ["2026-10-06", "el 6 de octubre", "6 octubre", "6 de oct", "06/10", "6/10/2026", "6/10/26"],
)
def test_a_date_is_read_in_every_format_the_answers_use(text: str) -> None:
    assert dates_in(text, 2026) == {date(2026, 10, 6)}


def test_a_date_without_a_year_takes_the_one_given() -> None:
    assert dates_in("el 6 de octubre", 2027) == {date(2027, 10, 6)}
    assert dates_in("el 6 de octubre de 2025", 2027) == {date(2025, 10, 6)}


def test_a_date_that_does_not_exist_or_a_word_that_is_not_a_month_is_ignored() -> None:
    assert dates_in("31 de febrero, 12 de nada, 3 bugs", 2026) == set()


def test_several_dates_in_a_text_are_all_found() -> None:
    assert dates_in("del 6 de octubre al 2026-10-09", 2026) == {date(2026, 10, 6), date(2026, 10, 9)}


# --- names ---


def test_a_full_name_names_only_that_person_even_if_the_surname_is_shared() -> None:
    assert people_named("Marta Pérez", ALIASES) == {"m"}
    assert people_named("Lucía Pérez", ALIASES) == {"l"}


def test_a_shared_surname_alone_names_everyone_who_has_it() -> None:
    assert people_named("Pérez", ALIASES) == {"l", "m"}


def test_a_first_name_or_a_surname_names_the_person_and_accents_do_not_matter() -> None:
    assert people_named("lucia", ALIASES) == {"l"}
    assert people_named("Vega", ALIASES) == {"b"}


def test_a_title_is_not_a_name() -> None:
    assert people_named("Profesor", ALIASES) == set()
    assert people_named("Profesor Soto", ALIASES) == {"s"}


def test_the_short_parts_of_a_name_are_ordinary_words() -> None:
    assert people_named("los reclamos van a llegar", ALIASES) == set()
    assert people_named("Víctor Van Der Berg", ALIASES) == {"v"}
    assert people_named("Berg", ALIASES) == {"v"}


def test_the_words_that_mean_the_user_name_the_user() -> None:
    assert people_named("yo se lo debo a vos", ALIASES) == {"u"}


def test_a_name_inside_another_word_is_not_a_name() -> None:
    assert people_named("la anaconda", ALIASES) == set()


# --- matching a line with a commitment ---

N1 = item("n1", "b", "u", "enviar el informe mensual de ventas", date(2026, 10, 14))
N2 = item("n2", "u", "b", "organizar la reunión de planificación trimestral", date(2026, 10, 20))


def verdicts(answer: str, *items: Item) -> Judgement:
    return judge(answer, list(items), PEOPLE, "u", 2026)


def test_a_commitment_is_found_when_at_least_half_of_its_words_are_in_a_line() -> None:
    j = verdicts("- Bruno Vega -> Ana Ruiz: enviar el informe, 2026-10-14", N1)
    assert [v.present for v in j.verdicts] == [True]


def test_a_commitment_is_not_found_when_less_than_half_of_its_words_are_in_the_line() -> None:
    j = verdicts("- Bruno Vega -> Ana Ruiz: mandar ventas, 2026-10-14", N1)
    assert [v.present for v in j.verdicts] == [False]


def test_a_line_stands_for_one_commitment_only() -> None:
    j = verdicts("- Bruno Vega -> Ana Ruiz: enviar el informe mensual de ventas y organizar la reunión de planificación trimestral", N1, N2)
    assert sorted(v.present for v in j.verdicts) == [False, True]


def test_two_commitments_that_read_alike_are_told_apart_by_people_and_date() -> None:
    a = item("a", "b", "u", "revisar el diseño de la pantalla", date(2026, 10, 14))
    b = item("b", "l", "u", "revisar el diseño de la pantalla", date(2026, 10, 20))
    j = verdicts("- Lucía Pérez -> Ana Ruiz: revisar el diseño de la pantalla, 2026-10-20\n- Bruno Vega -> Ana Ruiz: revisar el diseño de la pantalla, 2026-10-14", a, b)
    assert all(v.present and v.people == "ok" and v.due == "ok" for v in j.verdicts)


def test_a_wrong_due_date_is_wrong_and_no_date_at_all_is_missing() -> None:
    wrong = verdicts("- Bruno Vega -> Ana Ruiz: enviar el informe mensual de ventas, 2026-12-24", N1).verdicts[0]
    missing = verdicts("- Bruno Vega -> Ana Ruiz: enviar el informe mensual de ventas", N1).verdicts[0]
    assert (wrong.due, missing.due) == ("wrong", "missing")


def test_saying_there_is_no_date_for_a_commitment_that_has_one_is_wrong() -> None:
    v = verdicts("- Bruno Vega -> Ana Ruiz: enviar el informe mensual de ventas, sin fecha", N1).verdicts[0]
    assert v.due == "wrong"


def test_a_date_for_a_commitment_without_one_is_wrong_and_none_is_right() -> None:
    undated = item("n3", "b", "u", "definir el presupuesto del próximo semestre", None)
    assert verdicts("- Bruno Vega -> Ana Ruiz: definir el presupuesto del próximo semestre, 2026-10-30", undated).verdicts[0].due == "wrong"
    assert verdicts("- Bruno Vega -> Ana Ruiz: definir el presupuesto del próximo semestre, sin fecha", undated).verdicts[0].due == "ok"


def test_the_direction_is_judged_only_when_the_line_has_an_arrow() -> None:
    inverted = verdicts("- Ana Ruiz -> Bruno Vega: enviar el informe mensual de ventas, 2026-10-14", N1).verdicts[0]
    no_arrow = verdicts("- Ana Ruiz y Bruno Vega: enviar el informe mensual de ventas, 2026-10-14", N1).verdicts[0]
    assert (inverted.people, no_arrow.people) == ("wrong", "ok")


def test_a_different_person_in_place_of_one_of_the_two_is_wrong_and_no_person_is_unclear() -> None:
    other = verdicts("- Marta Pérez -> Ana Ruiz: enviar el informe mensual de ventas, 2026-10-14", N1).verdicts[0]
    nobody = verdicts("- enviar el informe mensual de ventas, 2026-10-14", N1).verdicts[0]
    assert (other.people, nobody.people) == ("wrong", "unclear")


def test_a_line_that_names_a_person_and_has_an_arrow_or_a_date_but_matches_nothing_is_invented() -> None:
    assert verdicts("- Bruno Vega -> Ana Ruiz: algo que nadie prometió", N1).invented == ["Bruno Vega -> Ana Ruiz: algo que nadie prometió"]
    assert len(verdicts("Bruno Vega dijo algo el 6 de octubre", N1).invented) == 1


def test_a_line_without_a_person_or_with_neither_arrow_nor_date_is_not_invented() -> None:
    assert verdicts("Estos son tus compromisos:\nAvisame si necesitás algo más", N1).invented == []
    assert verdicts("Bruno Vega siempre llega temprano", N1).invented == []


def test_an_empty_answer_leaves_out_everything() -> None:
    j = verdicts("", N1, N2)
    assert len(j.needed_missing) == 2 and j.invented == []


def test_noise_that_the_answer_says_is_counted_apart_from_what_was_needed() -> None:
    noise = item("x", "l", "m", "actualizar la documentación del servicio", date(2026, 10, 22), needed=False)
    j = verdicts("- Lucía Pérez -> Marta Pérez: actualizar la documentación del servicio, 2026-10-22", N1, noise)
    assert [v.item.id for v in j.noise_present] == ["x"] and [v.item.id for v in j.needed_missing] == ["n1"]
