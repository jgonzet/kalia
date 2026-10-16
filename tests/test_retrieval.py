from datetime import date, timedelta

import pytest

from app.answering.retrieval import AllCommitmentsRetriever, RuleRetriever
from app.models import Catalog, Commitment, Person

TODAY = date(2026, 10, 12)

BURNS = Person("p01", "Montgomery Burns", "CEO", "Direccion", 1, None)
SMITHERS = Person("p02", "Waylon Smithers", "Director", "Produccion", 2, "p01")
USER = Person("p05", "Lalo Landa", "Producer", "Produccion", 3, "p02")
PATTY = Person("p07", "Patty Bouvier", "Community Manager", "Produccion", 3, "p02")
SELMA = Person("p11", "Selma Bouvier", "Animadora", "Arte", 3, "p04")
FRINK = Person("p09", "Profesor Frink", "Backend Programmer", "Programacion", 3, "p03")
JOSE = Person("p13", "José Pérez", "Tester", "Programacion", 3, "p03")

CATALOG = Catalog(user=USER.name, people=(BURNS, SMITHERS, USER, PATTY, SELMA, FRINK, JOSE), projects=())


def commitment(id: str, who: Person, to_whom: Person, due: date | None = None) -> Commitment:
    return Commitment(id, "owner", who.id, to_whom.id, "do something", due, None, "doc-1", TODAY)


class FakeStore:
    """The two methods the retriever reads, backed by lists."""

    def __init__(self, commitments: list[Commitment], catalog: Catalog | None = CATALOG) -> None:
        self._commitments = commitments
        self._catalog = catalog

    def list_commitments(self) -> list[Commitment]:
        return self._commitments

    def load_catalog(self) -> Catalog | None:
        return self._catalog


def retrieve(question: str, commitments: list[Commitment], catalog: Catalog | None = CATALOG) -> list[str]:
    retriever = RuleRetriever(FakeStore(commitments, catalog), TODAY)  # type: ignore[arg-type]
    return [c.id for c in retriever.retrieve(question)]


@pytest.fixture
def commitments() -> list[Commitment]:
    return [
        commitment("a", USER, SMITHERS),
        commitment("b", SMITHERS, USER),
        commitment("c", FRINK, USER),
        commitment("d", FRINK, BURNS),
        commitment("e", PATTY, USER),
        commitment("f", USER, SELMA),
        commitment("g", USER, JOSE),
    ]


# --- people ---


def test_person_filter_keeps_both_directions_with_the_user(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué compromisos tengo con Smithers?", commitments) == ["a", "b"]


def test_person_filter_leaves_out_commitments_between_others(commitments: list[Commitment]) -> None:
    assert "d" not in retrieve("¿Qué compromisos tengo con Frink?", commitments)


def test_involves_includes_commitments_without_the_user(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué compromisos abiertos involucran a Frink?", commitments) == ["c", "d"]


def test_name_matches_ignoring_case_and_accents(commitments: list[Commitment]) -> None:
    assert retrieve("compromisos con JOSE", commitments) == ["g"]
    assert retrieve("compromisos con josé pérez", commitments) == ["g"]


def test_first_name_and_full_name_find_the_person(commitments: list[Commitment]) -> None:
    assert retrieve("compromisos con Selma", commitments) == ["f"]
    assert retrieve("compromisos con Patty Bouvier", commitments) == ["e"]


def test_shared_surname_does_not_pick_anyone(commitments: list[Commitment]) -> None:
    assert retrieve("compromisos con Bouvier", commitments) == [c.id for c in commitments]


def test_the_users_own_name_is_ignored(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué compromisos tiene Lalo?", commitments) == [c.id for c in commitments]


def test_several_people_are_joined_with_or(commitments: list[Commitment]) -> None:
    assert retrieve("compromisos con Smithers y Patty", commitments) == ["a", "b", "e"]


# --- boss ---


def test_boss_resolves_to_the_person_the_user_reports_to(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué compromisos tengo con mi jefe?", commitments) == ["a", "b"]
    assert retrieve("¿Qué compromisos tengo con mi jefa?", commitments) == ["a", "b"]


def test_boss_without_a_manager_in_the_catalog_adds_no_filter(commitments: list[Commitment]) -> None:
    orphan = Person(USER.id, USER.name, USER.role, USER.area, USER.level, None)
    catalog = Catalog(user=USER.name, people=(SMITHERS, orphan), projects=())
    assert retrieve("compromisos con mi jefe", commitments, catalog) == [c.id for c in commitments]


# --- dates ---


def test_week_runs_from_the_reference_date_to_six_days_later() -> None:
    items = [
        commitment("yesterday", USER, SMITHERS, TODAY - timedelta(days=1)),
        commitment("today", USER, SMITHERS, TODAY),
        commitment("day6", USER, SMITHERS, TODAY + timedelta(days=6)),
        commitment("day7", USER, SMITHERS, TODAY + timedelta(days=7)),
        commitment("undated", USER, SMITHERS, None),
    ]
    assert retrieve("¿Qué compromisos vencen esta semana?", items) == ["today", "day6"]


def test_week_word_must_be_a_whole_word() -> None:
    items = [commitment("a", USER, SMITHERS, TODAY), commitment("b", USER, SMITHERS, TODAY + timedelta(days=30))]
    assert retrieve("la reunión semanal", items) == ["a", "b"]


def test_person_and_week_are_joined_with_and() -> None:
    items = [
        commitment("in-week-smithers", USER, SMITHERS, TODAY),
        commitment("late-smithers", USER, SMITHERS, TODAY + timedelta(days=20)),
        commitment("in-week-patty", USER, PATTY, TODAY),
    ]
    assert retrieve("¿Qué hay esta semana con Smithers?", items) == ["in-week-smithers"]


# --- fallbacks ---


def test_a_question_with_no_filter_returns_everything(commitments: list[Commitment]) -> None:
    assert retrieve("¿Cómo viene el proyecto?", commitments) == [c.id for c in commitments]


def test_without_a_catalog_everything_is_returned(commitments: list[Commitment]) -> None:
    assert retrieve("compromisos con Smithers", commitments, catalog=None) == [c.id for c in commitments]


# --- phrases the rules do not fully understand widen the result, never narrow it ---


def test_next_week_is_the_seven_days_after_this_week() -> None:
    items = [
        commitment("this-week", USER, SMITHERS, TODAY + timedelta(days=6)),
        commitment("next-first", USER, SMITHERS, TODAY + timedelta(days=7)),
        commitment("next-last", USER, SMITHERS, TODAY + timedelta(days=13)),
        commitment("after", USER, SMITHERS, TODAY + timedelta(days=14)),
    ]
    assert retrieve("¿Qué vence la semana que viene?", items) == ["next-first", "next-last"]
    assert retrieve("¿Qué vence la próxima semana?", items) == ["next-first", "next-last"]


def test_a_week_the_rules_do_not_compute_gets_no_date_filter() -> None:
    items = [commitment("a", USER, SMITHERS, TODAY - timedelta(days=5)), commitment("b", USER, SMITHERS, TODAY + timedelta(days=3))]
    assert retrieve("¿Qué venció la semana pasada?", items) == ["a", "b"]


def test_without_the_user_in_the_question_a_person_means_any_commitment_of_theirs(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué prometió Frink?", commitments) == ["c", "d"]
    assert retrieve("¿Qué le prometieron a Burns?", commitments) == ["d"]
    assert retrieve("¿Qué compromisos hay entre Frink y Burns?", commitments) == ["c", "d"]  # a superset: Frink or Burns


def test_involves_wins_over_a_first_person_word(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué compromisos tengo abiertos que involucren a Frink?", commitments) == ["c", "d"]


def test_first_person_words_keep_the_commitments_shared_with_the_user(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué le prometí a Frink?", commitments) == ["c"]
    assert retrieve("¿Qué me prometió Frink?", commitments) == ["c"]


# --- the manager of someone ---


def test_the_boss_of_a_person_is_that_persons_manager() -> None:
    items = [commitment("smithers", SMITHERS, USER), commitment("burns", BURNS, USER), commitment("patty", PATTY, USER)]
    assert retrieve("¿Qué prometió el jefe de Patty?", items) == ["smithers"]  # Smithers manages Patty


def test_the_boss_of_my_boss() -> None:
    items = [commitment("smithers", SMITHERS, USER), commitment("burns", BURNS, USER)]
    assert retrieve("¿Qué compromisos tengo con el jefe de mi jefe?", items) == ["burns"]  # Burns manages Smithers


def test_a_boss_of_somebody_unknown_is_not_read_as_my_boss(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué prometió el jefe de QA?", commitments) == [c.id for c in commitments]


# --- the baseline ---


def test_the_baseline_retriever_returns_everything(commitments: list[Commitment]) -> None:
    retriever = AllCommitmentsRetriever(FakeStore(commitments), TODAY)  # type: ignore[arg-type]
    assert [c.id for c in retriever.retrieve("¿Qué compromisos tengo con Smithers?")] == [c.id for c in commitments]


# --- found by the audit: phrases and names the rules must not misread ---

MILHOUSE = Person("p06", "Milhouse Van Houten", "QA Lead", "Produccion", 3, "p02")


def retrieve_with_milhouse(question: str) -> list[str]:
    catalog = Catalog(user=USER.name, people=(*CATALOG.people, MILHOUSE), projects=())
    items = [commitment("m", MILHOUSE, USER, TODAY), commitment("s", SMITHERS, USER, TODAY + timedelta(days=30))]
    return retrieve(question, items, catalog)


def test_a_name_part_that_is_an_ordinary_word_picks_no_one() -> None:
    assert retrieve_with_milhouse("¿Qué compromisos van a vencer?") == ["m", "s"]  # "van" is a verb here, not Van Houten
    assert retrieve_with_milhouse("¿Qué compromisos van a vencer esta semana?") == ["m"]  # only the week narrows it


def test_the_rest_of_the_name_still_picks_the_person() -> None:
    assert retrieve_with_milhouse("compromisos con Milhouse") == ["m"]
    assert retrieve_with_milhouse("compromisos con Houten") == ["m"]
    assert retrieve_with_milhouse("compromisos con Milhouse Van Houten") == ["m"]


@pytest.mark.parametrize(
    "question",
    ["¿Qué viene esta semana?", "¿Qué vence en la semana?", "¿Qué vence durante la semana?", "¿Qué vence en la semana actual?"],
)
def test_phrases_about_this_week(question: str) -> None:
    items = [commitment("in", USER, SMITHERS, TODAY), commitment("out", USER, SMITHERS, TODAY + timedelta(days=9))]
    assert retrieve(question, items) == ["in"]


@pytest.mark.parametrize(
    "question",
    ["¿Qué vence la semana del 19?", "¿Qué vence dentro de una semana?", "¿Qué vencía hace una semana?", "¿Qué vence la semana?", "¿Qué hay para las próximas semanas?"],
)
def test_other_phrases_with_week_do_not_filter_by_date(question: str) -> None:
    items = [commitment("in", USER, SMITHERS, TODAY), commitment("out", USER, SMITHERS, TODAY + timedelta(days=9))]
    assert retrieve(question, items) == ["in", "out"]


def test_this_week_that_is_coming_means_next_week() -> None:
    items = [commitment("this", USER, SMITHERS, TODAY), commitment("next", USER, SMITHERS, TODAY + timedelta(days=9))]
    assert retrieve("¿Qué vence esta semana que viene?", items) == ["next"]


@pytest.mark.parametrize("question", ["", "   ", "((((", "jefe de [", "jefe de .* \\", "¿?¡!", "😀 jefe de 😀", "x" * 100_000])
def test_strange_text_never_breaks_the_retriever(question: str, commitments: list[Commitment]) -> None:
    assert retrieve(question, commitments) == [c.id for c in commitments]


def test_a_catalog_where_the_user_is_missing_does_not_break_anything(commitments: list[Commitment]) -> None:
    stranger = Catalog(user="Nobody Here", people=(SMITHERS, BURNS), projects=())
    assert retrieve("¿Qué compromisos tengo con mi jefe?", commitments, stranger) == [c.id for c in commitments]
    retrieve("¿Qué prometió el jefe de Smithers?", commitments, stranger)  # must not raise


def test_con_followed_by_something_that_is_not_a_person_does_not_mean_the_user(commitments: list[Commitment]) -> None:
    assert retrieve("¿Qué prometió Frink con el presupuesto?", commitments) == ["c", "d"]  # Frink with anyone
    assert retrieve("¿Qué compromisos con fecha tiene Frink?", commitments) == ["c", "d"]


def test_con_followed_by_a_person_keeps_meaning_the_user(commitments: list[Commitment]) -> None:
    assert retrieve("compromisos con Frink", commitments) == ["c"]
    assert retrieve("compromisos con el profesor Frink", commitments) == ["c"]
    assert retrieve("compromisos con mi jefe", commitments) == ["a", "b"]
