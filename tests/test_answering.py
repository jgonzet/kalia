from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.answering import Answer
from app.answering.llm_answerer import DEGRADED_TEXT, LLMAnswerer
from app.answering.ordering import due_state, group_by_project
from app.answering.prompt import NO_PROJECT, build_prompt
from app.answering.retrieval import RuleRetriever
from app.config import Settings
from app.llm import LLMError
from app.main import MAX_QUESTION_CHARS, create_app
from app.models import Catalog, Commitment, Person, Project
from app.storage.sqlite import SqliteStore

TODAY = date(2026, 10, 12)

NAMES = {"p-ana": "Ana Ruiz", "p-beto": "Beto Paz"}
ANA = Person("p-ana", "Ana Ruiz", "Dev", "Tech", 2, "p-beto")
BETO = Person("p-beto", "Beto Paz", "Lead", "Tech", 1, None)
SOON = Project("j-soon", "Soon", "", "active", date(2026, 11, 1))
LATE = Project("j-late", "Late", "", "active", date(2027, 3, 1))
NO_DEADLINE = Project("j-none", "NoDeadline", "", "active", None)
CATALOG = Catalog("Ana Ruiz", (ANA, BETO), (LATE, NO_DEADLINE, SOON))  # on purpose not in deadline order


def commitment(number: int, due: date | None = None, project_id: str | None = None, who: Person = ANA, to_whom: Person = BETO) -> Commitment:
    return Commitment(f"d-c{number}", "owner", who.id, to_whom.id, f"task {number}", due, project_id, "d", date(2026, 10, 1))


def group_ids(commitments: list[Commitment], catalog: Catalog | None = CATALOG) -> list[tuple[str | None, list[str]]]:
    return [(g.project.id if g.project else None, [c.id for c in g.commitments]) for g in group_by_project(commitments, catalog)]


class TestDueState:
    def test_no_due_date(self) -> None:
        assert due_state(commitment(1), TODAY) == "no deadline"

    def test_before_today_is_overdue(self) -> None:
        assert due_state(commitment(1, date(2026, 10, 11)), TODAY) == "overdue"

    def test_today_is_pending(self) -> None:
        assert due_state(commitment(1, TODAY), TODAY) == "pending"

    def test_after_today_is_pending(self) -> None:
        assert due_state(commitment(1, date(2026, 10, 13)), TODAY) == "pending"


class TestGroupByProject:
    def test_projects_go_by_deadline_then_no_deadline_then_no_project(self) -> None:
        commitments = [commitment(1, project_id="j-none"), commitment(2), commitment(3, project_id="j-late"), commitment(4, project_id="j-soon")]
        assert [project for project, _ in group_ids(commitments)] == ["j-soon", "j-late", "j-none", None]

    def test_projects_with_the_same_deadline_go_by_id(self) -> None:
        a = Project("j-a", "A", "", "active", date(2026, 12, 1))
        b = Project("j-b", "B", "", "active", date(2026, 12, 1))
        catalog = Catalog("Ana Ruiz", (ANA, BETO), (b, a))
        assert [p for p, _ in group_ids([commitment(1, project_id="j-b"), commitment(2, project_id="j-a")], catalog)] == ["j-a", "j-b"]

    def test_inside_a_project_nearest_due_first_and_undated_last(self) -> None:
        commitments = [commitment(1, project_id="j-soon"), commitment(2, date(2026, 10, 20), "j-soon"), commitment(3, date(2026, 10, 5), "j-soon")]
        assert group_ids(commitments) == [("j-soon", ["d-c3", "d-c2", "d-c1"])]

    def test_same_due_date_goes_by_id(self) -> None:
        commitments = [commitment(2, TODAY, "j-soon"), commitment(1, TODAY, "j-soon")]
        assert group_ids(commitments) == [("j-soon", ["d-c1", "d-c2"])]

    def test_a_project_missing_from_the_catalog_counts_as_no_project(self) -> None:
        assert group_ids([commitment(1, project_id="j-unknown")]) == [(None, ["d-c1"])]

    def test_without_catalog_everything_is_one_group_with_no_project(self) -> None:
        assert group_ids([commitment(1, project_id="j-soon"), commitment(2)], None) == [(None, ["d-c1", "d-c2"])]

    def test_empty_list_gives_no_groups(self) -> None:
        assert group_by_project([], CATALOG) == []

    def test_no_commitment_is_lost_or_repeated(self) -> None:
        commitments = [commitment(n, project_id=p) for n, p in enumerate(["j-soon", None, "j-late", "j-soon", "j-none"], start=1)]
        ids = [i for _, group in group_ids(commitments) for i in group]
        assert sorted(ids) == sorted(c.id for c in commitments)


class TestBuildPrompt:
    def test_groups_come_in_order_with_a_heading_each(self) -> None:
        commitments = [commitment(1), commitment(2, project_id="j-late"), commitment(3, project_id="j-soon")]
        prompt = build_prompt("¿Qué hay?", commitments, CATALOG, TODAY)
        assert prompt.index("## Soon") < prompt.index("## Late") < prompt.index(f"## {NO_PROJECT}")

    def test_lines_show_names_state_and_source_not_catalog_ids(self) -> None:
        prompt = build_prompt("q", [commitment(1, date(2026, 10, 1), "j-soon")], CATALOG, TODAY)
        line = next(line for line in prompt.splitlines() if line.startswith("d-c1"))
        assert line == "d-c1 | Ana Ruiz -> Beto Paz | task 1 | 2026-10-01 | overdue | d (2026-10-01)"
        assert "p-ana" not in prompt

    def test_undated_commitment_says_no_deadline(self) -> None:
        prompt = build_prompt("q", [commitment(1)], CATALOG, TODAY)
        assert "| task 1 | none | no deadline |" in prompt

    def test_question_user_and_today_are_in_the_prompt(self) -> None:
        prompt = build_prompt("¿Qué prometí?", [commitment(1)], CATALOG, TODAY)
        assert prompt.rstrip().endswith("Question: ¿Qué prometí?")
        assert "assistant of Ana Ruiz" in prompt
        assert "Today is 2026-10-12" in prompt

    def test_no_placeholder_is_left(self) -> None:
        prompt = build_prompt("q", [commitment(1)], CATALOG, TODAY)
        assert "$" not in prompt

    def test_empty_list_says_none(self) -> None:
        assert "Commitments:\n\n(none)\n" in build_prompt("q", [], CATALOG, TODAY)

    def test_without_catalog_ids_stand_in_for_names(self) -> None:
        prompt = build_prompt("q", [commitment(1)], None, TODAY)
        assert "p-ana -> p-beto" in prompt
        assert "assistant of the user" in prompt

    def test_a_dollar_sign_in_the_question_or_a_commitment_does_not_break_it(self) -> None:
        tricky = Commitment("d-c1", "o", ANA.id, BETO.id, "pay $user $100", None, None, "d", TODAY)
        prompt = build_prompt("cost in $?", [tricky], CATALOG, TODAY)
        assert "pay $user $100" in prompt and "cost in $?" in prompt


def example_of(prompt: str) -> str:
    """The worked example of the prompt: from its heading to the line before the list of commitments."""
    return prompt[prompt.index("Example (") : prompt.index("\nCommitments:\n")]


class TestPromptFile:
    @pytest.mark.parametrize("user", ["Ana Ruiz", "Mara Gil"])
    def test_the_example_is_about_whoever_the_user_is(self, user: str) -> None:
        catalog = Catalog(user, (ANA, BETO), ())
        example = example_of(build_prompt("q", [commitment(1)], catalog, TODAY))
        assert f"the asker is {user}" in example
        assert f"{user} -> Zeta" in example and f"Zeta -> {user}" in example

    def test_the_example_does_not_name_a_fixed_user(self) -> None:
        catalog = Catalog("Mara Gil", (ANA, BETO), ())
        prompt = build_prompt("q", [], catalog, TODAY)
        assert "Beto" not in example_of(prompt)  # a literal name would contradict the real user
        assert "$" not in prompt

    @pytest.mark.parametrize("state", ["overdue", "pending", "no deadline"])
    def test_every_state_the_code_writes_is_explained_in_the_prompt(self, state: str) -> None:
        prompt = build_prompt("q", [], CATALOG, TODAY)
        instructions = prompt[: prompt.index("Example (")]
        assert f'"{state}"' in instructions
        assert state in {due_state(commitment(1, d), TODAY) for d in (None, date(2026, 1, 1), TODAY)}


class StubRetriever:
    def __init__(self, commitments: list[Commitment]) -> None:
        self.commitments = commitments
        self.questions: list[str] = []
        self.catalogs: list[Catalog | None] = []

    def retrieve(self, question: str, catalog: Catalog | None = None) -> list[Commitment]:
        self.questions.append(question)
        self.catalogs.append(catalog)
        return self.commitments


class StubStore:
    def __init__(self, catalog: Catalog | None = CATALOG) -> None:
        self._catalog = catalog
        self.catalog_loads = 0

    def load_catalog(self) -> Catalog | None:
        self.catalog_loads += 1
        return self._catalog


class StubLLM:
    def __init__(self, response: str = "answer", error: bool = False) -> None:
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise LLMError("down")
        return self.response


def make_answerer(llm: StubLLM, commitments: list[Commitment]) -> tuple[LLMAnswerer, StubRetriever]:
    retriever = StubRetriever(commitments)
    return LLMAnswerer(llm, retriever, StubStore(), TODAY), retriever  # type: ignore[arg-type]


class TestLLMAnswerer:
    def test_returns_the_llm_text_with_the_retrieved_commitments(self) -> None:
        commitments = [commitment(1), commitment(2)]
        answerer, retriever = make_answerer(StubLLM("  hola  "), commitments)
        answer = answerer.answer("¿Qué?")
        assert answer == Answer("hola", commitments, degraded=False, people=NAMES)
        assert retriever.questions == ["¿Qué?"]

    def test_the_llm_gets_the_question_and_the_retrieved_commitments_only(self) -> None:
        llm = StubLLM()
        answerer, _ = make_answerer(llm, [commitment(1)])
        answerer.answer("¿Qué?")
        assert len(llm.prompts) == 1
        assert "Question: ¿Qué?" in llm.prompts[0] and "task 1" in llm.prompts[0]

    def test_llm_error_degrades_instead_of_raising(self) -> None:
        commitments = [commitment(1)]
        answerer, _ = make_answerer(StubLLM(error=True), commitments)
        assert answerer.answer("q") == Answer(DEGRADED_TEXT, commitments, degraded=True, people=NAMES)

    @pytest.mark.parametrize("empty", ["", "   ", "\n"])
    def test_empty_answer_degrades(self, empty: str) -> None:
        answerer, _ = make_answerer(StubLLM(empty), [commitment(1)])
        assert answerer.answer("q").degraded is True

    def test_works_without_a_stored_catalog(self) -> None:
        retriever = StubRetriever([commitment(1)])
        answerer = LLMAnswerer(StubLLM("ok"), retriever, StubStore(None), TODAY)  # type: ignore[arg-type]
        answer = answerer.answer("q")
        assert answer.text == "ok" and answer.people == {}

    def test_the_catalog_is_read_once_per_question(self) -> None:
        retriever, store = StubRetriever([commitment(1)]), StubStore()
        LLMAnswerer(StubLLM(), retriever, store, TODAY).answer("q")  # type: ignore[arg-type]
        assert store.catalog_loads == 1

    def test_the_catalog_it_read_is_handed_to_the_retriever(self) -> None:
        retriever = StubRetriever([commitment(1)])
        LLMAnswerer(StubLLM(), retriever, StubStore(), TODAY).answer("q")  # type: ignore[arg-type]
        assert retriever.catalogs == [CATALOG]

    def test_with_the_real_retriever_the_catalog_is_read_once_per_question(self, tmp_path: Path) -> None:
        class Counting(SqliteStore):
            loads = 0

            def load_catalog(self) -> Catalog | None:
                Counting.loads += 1
                return super().load_catalog()

        counting = Counting(str(tmp_path / "c.db"), "owner")
        counting.save_catalog(CATALOG)
        counting.save_document_commitments("d", [commitment(1)])
        LLMAnswerer(StubLLM(), RuleRetriever(counting, TODAY), counting, TODAY).answer("¿Qué hay con Beto?")
        assert Counting.loads == 1

    def test_another_prompt_file_can_be_used(self, tmp_path: Path) -> None:
        template = tmp_path / "other.md"
        template.write_text("OTHER $user | $question | $commitments", encoding="utf-8")
        llm = StubLLM()
        LLMAnswerer(llm, StubRetriever([commitment(1)]), StubStore(), TODAY, template).answer("hola")  # type: ignore[arg-type]
        assert llm.prompts[0].startswith("OTHER Ana Ruiz | hola |")


@pytest.fixture
def store(tmp_path: Path) -> SqliteStore:
    sqlite = SqliteStore(str(tmp_path / "t.db"), "owner")
    sqlite.save_catalog(CATALOG)
    sqlite.save_document_commitments(
        "d", [commitment(1, date(2026, 10, 13), "j-soon"), commitment(2, None, None, who=BETO, to_whom=ANA)]
    )
    return sqlite


def client(store: SqliteStore, llm: StubLLM) -> TestClient:
    settings = Settings(llm_backend="fake", reference_date=TODAY)
    return TestClient(create_app(settings=settings, llm=llm, store=store))


class TestChatEndpoint:
    def test_answers_with_names_instead_of_ids(self, store: SqliteStore) -> None:
        response = client(store, StubLLM("la respuesta")).post("/chat", json={"question": "¿Qué compromisos hay?"})
        body = response.json()
        assert response.status_code == 200
        assert body["answer"] == "la respuesta" and body["degraded"] is False
        assert {(c["who"], c["to_whom"]) for c in body["commitments"]} == {("Ana Ruiz", "Beto Paz"), ("Beto Paz", "Ana Ruiz")}
        assert next(c for c in body["commitments"] if c["id"] == "d-c1")["due"] == "2026-10-13"

    def test_llm_failure_is_a_normal_response_marked_degraded(self, store: SqliteStore) -> None:
        response = client(store, StubLLM(error=True)).post("/chat", json={"question": "¿Qué compromisos hay?"})
        body = response.json()
        assert response.status_code == 200
        assert body["degraded"] is True and body["answer"] == DEGRADED_TEXT
        assert len(body["commitments"]) == 2

    def test_a_question_without_commitments_still_answers(self, tmp_path: Path) -> None:
        empty = SqliteStore(str(tmp_path / "e.db"), "owner")
        empty.save_catalog(CATALOG)
        body = client(empty, StubLLM("nada")).post("/chat", json={"question": "¿Qué hay?"}).json()
        assert body == {"answer": "nada", "degraded": False, "commitments": []}

    def test_a_request_without_question_is_rejected(self, store: SqliteStore) -> None:
        assert client(store, StubLLM()).post("/chat", json={}).status_code == 422

    def test_names_come_from_the_answer_and_the_endpoint_does_not_read_the_catalog(self, tmp_path: Path) -> None:
        class Counting(SqliteStore):
            loads = 0

            def load_catalog(self) -> Catalog | None:
                Counting.loads += 1
                return super().load_catalog()

        class Fixed:
            def answer(self, question: str) -> Answer:
                return Answer("x", [commitment(1)], degraded=False, people={"p-ana": "Name From Answer"})

        counting = Counting(str(tmp_path / "c.db"), "owner")
        settings = Settings(llm_backend="fake", reference_date=TODAY)
        body = TestClient(create_app(settings=settings, llm=StubLLM(), store=counting, answerer=Fixed())).post("/chat", json={"question": "q"}).json()
        assert body["commitments"][0]["who"] == "Name From Answer" and body["commitments"][0]["to_whom"] == "p-beto"
        assert Counting.loads == 0

    def test_an_injected_answerer_replaces_the_default(self, store: SqliteStore) -> None:
        class Fixed:
            def answer(self, question: str) -> Answer:
                return Answer(f"echo {question}", [], degraded=False)

        settings = Settings(llm_backend="fake", reference_date=TODAY)
        app_client = TestClient(create_app(settings=settings, llm=StubLLM(), store=store, answerer=Fixed()))
        assert app_client.post("/chat", json={"question": "hi"}).json()["answer"] == "echo hi"

    def test_the_chat_page_is_served_and_posts_to_chat(self, store: SqliteStore) -> None:
        page = client(store, StubLLM()).get("/")
        assert page.status_code == 200
        assert "<form" in page.text and "/chat" in page.text


class TestChatQuestionLimits:
    @pytest.mark.parametrize("question", ["", "   ", "\n\t"])
    def test_an_empty_question_is_rejected(self, store: SqliteStore, question: str) -> None:
        assert client(store, StubLLM()).post("/chat", json={"question": question}).status_code == 422

    def test_a_question_over_the_limit_is_rejected(self, store: SqliteStore) -> None:
        too_long = "a" * (MAX_QUESTION_CHARS + 1)
        assert client(store, StubLLM()).post("/chat", json={"question": too_long}).status_code == 422

    def test_a_question_at_the_limit_is_accepted_and_spaces_around_it_are_trimmed(self, store: SqliteStore) -> None:
        llm = StubLLM()
        response = client(store, llm).post("/chat", json={"question": "  " + "a" * MAX_QUESTION_CHARS + "  "})
        assert response.status_code == 200
        assert f"Question: {'a' * MAX_QUESTION_CHARS}\n" in llm.prompts[0] + "\n"


def asked_today(app_client: TestClient, llm: StubLLM) -> str:
    app_client.post("/chat", json={"question": "q"})
    return next(line for line in llm.prompts[-1].splitlines() if "Today is" in line).split("Today is ")[1][:10]


class TestChatUsesTheReferenceDate:
    def test_the_chat_uses_the_date_of_the_loaded_dataset(self, store: SqliteStore) -> None:
        store.save_reference_date(date(2026, 10, 12))
        llm = StubLLM()
        assert asked_today(TestClient(create_app(Settings(llm_backend="fake"), llm, store)), llm) == "2026-10-12"

    def test_the_environment_overrides_the_dataset(self, store: SqliteStore) -> None:
        store.save_reference_date(date(2026, 10, 12))
        llm = StubLLM()
        settings = Settings(llm_backend="fake", reference_date=date(2026, 3, 12))
        assert asked_today(TestClient(create_app(settings, llm, store)), llm) == "2026-03-12"

    def test_it_is_read_on_every_question_not_once_at_startup(self, store: SqliteStore) -> None:
        llm = StubLLM()
        app_client = TestClient(create_app(Settings(llm_backend="fake"), llm, store))
        store.save_reference_date(date(2026, 1, 1))
        assert asked_today(app_client, llm) == "2026-01-01"
        store.save_reference_date(date(2026, 1, 2))
        assert asked_today(app_client, llm) == "2026-01-02"
