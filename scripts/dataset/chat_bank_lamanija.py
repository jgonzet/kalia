"""Questions of the chat bank of `data/lamanija/`. The engine and the file format: scripts/dataset/chat_bank.py and
docs/DATASET.md ("Chat bank"); the conditions it is built from and the meaning of every term: scripts/dataset/retrieval_bank.py
and docs/DATASET.md ("What each term means").

Each question says, with a condition over one commitment, what a correct answer contains (`needed`), and with kinds of
noise what else the LLM is given: the commitments a retrieval could let through (the opposite direction, the same person
with others, the next week, other projects). Only questions the LLM can decide from what its prompt shows are here: the
user's name, each commitment's people, text, due date, state and project, and today's date. It does not see the org
chart, the roles or the areas, so questions about "la gente de Arte" or "la Directora de Arte" are not here; the one about "mi jefe" is given no noise.
To add a question, append a `ChatSpec` (or `reuse` a retrieval question) and run `uv run scripts/dataset/chat_bank.py lamanija`.
"""

from datetime import date, timedelta

from scripts.dataset.chat_bank import ChatSpec, Noise
from scripts.dataset.retrieval_bank import (
    Cond,
    Context,
    Person,
    Spec,
    dated,
    due_between,
    due_on,
    everything,
    in_project,
    involves,
    no_project,
    nothing,
    overdue,
    to_whom,
    undated,
    what_has,
    who,
    with_user,
)

FAR_FUTURE = date(2099, 12, 31)


def specs(ctx: Context, retrieval: dict[tuple[str, str], Spec]) -> list[ChatSpec]:
    """Return the questions of the bank, in the order of the file."""
    user, today = ctx.user, ctx.today
    smithers, burns, skinner = ctx.person("Smithers"), ctx.person("Burns"), ctx.person("Skinner")
    helen, manjula, milhouse = ctx.person("Lovejoy"), ctx.person("Nahasapeemapetilon"), ctx.person("Milhouse")
    edna, frink, patty, selma = ctx.person("Krabappel"), ctx.person("Frink"), ctx.person("Patty"), ctx.person("Selma")
    project = lambda name: in_project(ctx.projects, name)  # noqa: E731

    week = due_between(today, today + timedelta(days=6))
    next_week = due_between(today + timedelta(days=7), today + timedelta(days=13))
    month = due_between(today, ctx.month_end)
    pending = due_between(today, FAR_FUTURE)
    friday, monday = ctx.next_weekday(4), ctx.next_weekday(0)
    day = lambda n: due_on(date(today.year, 10, n))  # noqa: E731

    def reuse(retrieval_id: str, *noise: Noise, category: str | None = None, size: int | None = 8) -> ChatSpec:
        """A question of the retrieval bank (its version v1), with the same condition and the noise given here."""
        s = retrieval[(retrieval_id, "v1")]
        return ChatSpec(s.id, category or s.category, s.question, s.cond, noise, noise_size=size)

    def new(spec_id: str, category: str, question: str, needed: Cond, *noise: Noise, size: int | None = 8) -> ChatSpec:
        return ChatSpec(spec_id, category, question, needed, noise, noise_size=size)

    def other_people(p: Person) -> Noise:
        return Noise(f"{p.name} con otras personas", involves(p))

    def user_with_others() -> Noise:
        return Noise("yo con otras personas", who(user) | to_whom(user))

    anything_else = Noise("compromisos de otras personas y otros temas", everything())
    unneeded_undated = Noise("compromisos sin fecha", undated())
    overdue_noise = Noise("compromisos atrasados", overdue(today))

    return [
        # -- direction: who promised and who received; the opposite direction is the usual noise
        reuse(
            "direction-user-promised",
            Noise("sentido contrario: Smithers me prometió a mí", who(smithers) & to_whom(user)),
            other_people(smithers),
            Noise("lo que prometí a otras personas", who(user)),
        ),
        reuse(
            "direction-user-received",
            Noise("sentido contrario: yo le prometí a Smithers", who(user) & to_whom(smithers)),
            Noise("lo que Smithers prometió a otras personas", who(smithers)),
            Noise("lo que otras personas me prometieron", to_whom(user)),
        ),
        reuse("direction-promiser-any", Noise("lo que le prometieron a Frink", to_whom(frink)), anything_else),
        reuse(
            "direction-promiser-any-dated",
            Noise("lo que Frink prometió sin fecha", who(frink) & undated()),
            Noise("lo que le prometieron a Frink", to_whom(frink)),
            anything_else,
        ),
        reuse("direction-recipient-any", Noise("lo que Burns prometió", who(burns)), anything_else),
        reuse("direction-involves", Noise("el mismo proyecto, sin Skinner", project("Choripixels")), anything_else),
        reuse("direction-between-others", other_people(frink), other_people(manjula)),
        reuse(
            "direction-directed-others",
            Noise("sentido contrario: Burns a Skinner", who(burns) & to_whom(skinner)),
            Noise("lo que Skinner prometió a otras personas", who(skinner)),
            other_people(burns),
        ),
        reuse("direction-mine", Noise("lo que me prometieron", to_whom(user)), anything_else),
        reuse("direction-owed-to-me", Noise("lo que yo prometí", who(user)), anything_else),
        new(
            "direction-both-ways-with-dates",
            "direction",
            "¿Qué compromisos tengo con Smithers, en ambos sentidos, y para cuándo?",
            with_user(user, smithers),
            other_people(smithers),
            user_with_others(),
        ),
        # -- person: how a person is named; the noise is that person with others and the user with others
        reuse("person-surname", other_people(skinner), user_with_others()),
        reuse("person-first-name", other_people(helen), user_with_others()),
        reuse("person-lowercase", other_people(milhouse), user_with_others()),
        reuse("person-typo", other_people(edna), user_with_others()),
        reuse(
            "person-ambiguous",
            Noise("Patty o Selma con otras personas", (involves(patty) | involves(selma))),
            user_with_others(),
        ),
        reuse("person-two", Noise("Edna o Frink con otras personas", (involves(edna) | involves(frink))), user_with_others()),
        # -- date: periods, single days and the absence of a date; the noise is the neighbouring period
        reuse("date-today", Noise("mañana", due_on(today + timedelta(days=1))), overdue_noise, unneeded_undated),
        reuse("date-tomorrow", Noise("hoy", due_on(today)), Noise("pasado mañana", due_on(today + timedelta(days=2))), overdue_noise),
        reuse("date-viene-is-not-next-week", Noise("la semana que viene", next_week), overdue_noise, unneeded_undated),
        reuse(
            "date-next-week",
            Noise("esta semana", week),
            Noise("dos semanas más adelante", due_between(today + timedelta(days=14), today + timedelta(days=20))),
            unneeded_undated,
        ),
        reuse(
            "date-last-week",
            Noise("esta semana", week),
            Noise("antes de la semana pasada", due_between(today - timedelta(days=30), today - timedelta(days=8))),
            unneeded_undated,
        ),
        reuse(
            "date-month",
            Noise("el mes que viene", due_between(ctx.month_end + timedelta(days=1), ctx.month_end + timedelta(days=60))),
            Noise("atrasados de meses anteriores", due_between(date(2000, 1, 1), today.replace(day=1) - timedelta(days=1))),
            unneeded_undated,
        ),
        reuse("date-overdue", Noise("compromisos de hoy en adelante", pending), unneeded_undated),
        reuse("date-undated", Noise("compromisos con fecha", dated())),
        reuse(
            "date-weekday",
            Noise("el día anterior", due_on(friday - timedelta(days=1))),
            Noise("el día siguiente", due_on(friday + timedelta(days=1))),
            overdue_noise,
        ),
        reuse("date-range", Noise("el día anterior", day(13)), Noise("el día siguiente", day(17)), overdue_noise),
        new(
            "date-absolute-busy-day",
            "date",
            "¿Qué vence el 13 de octubre?",
            day(13),
            Noise("el día anterior", day(12)),
            Noise("el día siguiente", day(14)),
            overdue_noise,
        ),
        new(
            "date-weekday-same-as-today",
            "date",
            "¿Qué vence el lunes?",
            due_on(monday),
            Noise("hoy, que también es lunes", due_on(today)),
            Noise("el martes siguiente", due_on(monday + timedelta(days=1))),
            Noise("el viernes anterior", due_on(monday - timedelta(days=3))),
        ),
        # -- hierarchy: only the acceptance question about the boss, with no noise. The LLM does not see the org chart, so it
        # cannot tell the boss's commitments from others: it is given exactly what the retrieval brings for "mi jefe"
        # (it resolves the boss) and the question measures whether the answer leaves any of them out.
        new(
            "hierarchy-boss-with",
            "hierarchy",
            "¿Qué compromisos tengo con mi jefe?",
            with_user(user, ctx.boss),
            size=0,
        ),
        # -- state: overdue, open and undated, as the prompt marks them
        new(
            "state-open-includes-overdue",
            "state",
            "¿Qué compromisos abiertos tengo con Patty?",
            with_user(user, patty),
            other_people(patty),
            user_with_others(),
        ),
        new(
            "state-overdue-mine",
            "state",
            "¿Qué compromisos atrasados tengo yo?",
            who(user) & overdue(today),
            Noise("lo que prometí y todavía no vence", who(user) & pending),
            Noise("lo que me prometieron y está atrasado", to_whom(user) & overdue(today)),
        ),
        new(
            "state-undated-owed",
            "state",
            "¿Qué compromisos sin fecha me deben?",
            to_whom(user) & undated(),
            Noise("lo que me deben con fecha", to_whom(user) & dated()),
            Noise("lo que yo prometí sin fecha", who(user) & undated()),
        ),
        # -- project: a project named fully, partly or not at all
        reuse("project-name", Noise("otros proyectos", everything()), Noise("sin proyecto", no_project())),
        reuse("project-partial-name", Noise("otros proyectos", everything()), Noise("sin proyecto", no_project())),
        reuse("project-none", Noise("compromisos de algún proyecto", everything())),
        # -- combination: two or three filters in one question; the noise meets all but one of them
        reuse(
            "combination-person-week",
            Noise("Smithers, otra semana", with_user(user, smithers)),
            Noise("esta semana, otras personas", week),
        ),
        reuse(
            "combination-person-project",
            Noise("Frink, otros proyectos", with_user(user, frink)),
            Noise("el mismo proyecto, otras personas", project("Motocrotos Adventures")),
        ),
        reuse(
            "combination-person-project-week",
            Noise("Smithers y el proyecto, otras semanas", with_user(user, smithers) & project("Turrokiller")),
            Noise("Smithers y la semana, otro proyecto", with_user(user, smithers) & week),
            Noise("el proyecto y la semana, otras personas", project("Turrokiller") & week),
        ),
        reuse(
            "combination-direction-date",
            Noise("me deben, otra fecha", to_whom(user)),
            Noise("mañana, otras direcciones", due_on(today + timedelta(days=1))),
        ),
        reuse(
            "combination-direction-person-weekday",
            Noise("lo que le prometí a Smithers, otro día", who(user) & to_whom(smithers)),
            Noise("sentido contrario", who(smithers) & to_whom(user)),
            Noise("el mismo día, otras personas", due_on(friday)),
        ),
        reuse(
            "combination-overdue-person",
            Noise("Patty, todavía no vence", with_user(user, patty)),
            Noise("atrasados, otras personas", overdue(today)),
        ),
        reuse(
            "combination-undated-person",
            Noise("Smithers, con fecha", with_user(user, smithers)),
            Noise("sin fecha, otras personas", undated()),
        ),
        reuse(
            "combination-project-month",
            Noise("el proyecto, otro mes", project("Choripixels")),
            Noise("este mes, otros proyectos", month),
        ),
        new(
            "combination-received-project",
            "combination",
            "¿Qué me prometieron en Turrokiller?",
            to_whom(user) & project("Turrokiller"),
            Noise("lo que prometí en Turrokiller", who(user) & project("Turrokiller")),
            Noise("lo que me prometieron en otros proyectos", to_whom(user)),
            Noise("el proyecto, otras personas", project("Turrokiller")),
        ),
        # -- topic: what the commitment is about, judged by the words of `what`
        reuse(
            "topic-budget",
            Noise("Burns y Smithers hablando de otros temas", involves(burns) | involves(smithers)),
            anything_else,
        ),
        reuse("topic-bugs", Noise("QA hablando de otros temas", involves(milhouse)), anything_else),
        reuse("topic-person-festival", Noise("Smithers sin el tema", with_user(user, smithers)), Noise("el tema, otras personas", what_has("festival"))),
        new(
            "topic-demo",
            "topic",
            "¿Qué compromisos hay sobre la demo?",
            what_has("demo"),
            Noise("el mismo proyecto, otros temas", project("Turrokiller")),
            anything_else,
        ),
        # -- open: a question that narrows nothing, so everything is needed
        reuse("open-how-is-everything", size=0),
        # -- none: nothing matches and the other commitments are only noise; the right answer says so
        reuse("person-unknown", anything_else, category="none"),
        reuse("project-unknown", anything_else, category="none"),
        reuse(
            "date-empty-day",
            Noise("el día anterior", day(16)),
            Noise("el día siguiente", day(18)),
            category="none",
        ),
        new(
            "none-direction-pair",
            "none",
            "¿Qué le prometió Burns a Patty?",
            who(burns) & to_whom(patty),
            Noise("lo que Burns prometió a otras personas", who(burns)),
            Noise("lo que le prometieron a Patty", to_whom(patty)),
        ),
        # -- volume: one question with a growing list, to see how the answer falls as the list grows
        new(
            "volume-promised-no-noise",
            "volume",
            "¿Qué le prometí a Smithers?",
            who(user) & to_whom(smithers),
            Noise("compromisos que no corresponden", everything()),
            size=0,
        ),
        new(
            "volume-promised-25",
            "volume",
            "¿Qué le prometí a Smithers?",
            who(user) & to_whom(smithers),
            Noise("compromisos que no corresponden", everything()),
            size=25,
        ),
        new(
            "volume-promised-all",
            "volume",
            "¿Qué le prometí a Smithers?",
            who(user) & to_whom(smithers),
            Noise("compromisos que no corresponden", everything()),
            size=None,
        ),
        new(
            "volume-few-needed-all",
            "volume",
            "¿Qué compromisos tengo con Helen?",
            with_user(user, helen),
            Noise("compromisos que no corresponden", everything()),
            size=None,
        ),
        # -- language: the same questions in other wordings; the answer is judged by its content
        new(
            "language-english-promised",
            "language",
            "What did I promise Smithers?",
            who(user) & to_whom(smithers),
            Noise("sentido contrario: Smithers me prometió a mí", who(smithers) & to_whom(user)),
            other_people(smithers),
        ),
        new(
            "language-english-week",
            "language",
            "What is due this week?",
            week,
            Noise("la semana que viene", next_week),
            overdue_noise,
            unneeded_undated,
        ),
        new(
            "language-no-accents",
            "language",
            "que le prometi a smithers",
            who(user) & to_whom(smithers),
            Noise("sentido contrario: Smithers me prometió a mí", who(smithers) & to_whom(user)),
            other_people(smithers),
        ),
        new(
            "language-colloquial",
            "language",
            "che, pasame lo que me prometió Milhouse",
            who(milhouse) & to_whom(user),
            Noise("sentido contrario: yo le prometí a Milhouse", who(user) & to_whom(milhouse)),
            Noise("lo que Milhouse prometió a otras personas", who(milhouse)),
            anything_else,
        ),
        # -- unanswerable: the list cannot answer; the right answer says so and lists no commitment as if it did
        new(
            "unanswerable-org-chart",
            "unanswerable",
            "¿Quién es el jefe de Edna?",
            nothing("the list has no org chart"),
            other_people(edna),
            anything_else,
        ),
        new(
            "unanswerable-meeting-content",
            "unanswerable",
            "¿De qué se habló en la reunión de Choripixels?",
            nothing("the list has commitments, not what was said"),
            Noise("el proyecto", project("Choripixels")),
            anything_else,
        ),
    ]
