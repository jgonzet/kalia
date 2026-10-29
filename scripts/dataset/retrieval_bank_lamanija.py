"""Questions of the retrieval bank of `data/lamanija/`. The engine and the rules of every term: scripts/dataset/retrieval_bank.py
and docs/DATASET.md ("Retrieval bank").

Each question says, with a condition over one commitment, what a correct answer contains. The questions are written as a
user would type them, not to match what the retriever understands today. To add one, append a `Spec` here (the angle it
covers goes in the coverage table of docs/DATASET.md) and run `uv run scripts/dataset/retrieval_bank.py lamanija`.
"""

from datetime import date, timedelta

from scripts.dataset.retrieval_bank import (
    Context,
    Spec,
    any_of,
    between,
    dated,
    due_between,
    due_on,
    everything,
    in_project,
    no_project,
    nothing,
    overdue,
    to_whom,
    undated,
    what_has,
    who,
    with_user,
)


def specs(ctx: Context) -> list[Spec]:
    """Return the questions of the bank, in the order of the file."""
    user, boss, today = ctx.user, ctx.boss, ctx.today
    smithers, burns = ctx.person("Smithers"), ctx.person("Burns")
    skinner, marge, helen = ctx.person("Skinner"), ctx.person("Marge"), ctx.person("Lovejoy")
    manjula, milhouse, edna = ctx.person("Nahasapeemapetilon"), ctx.person("Van Houten"), ctx.person("Krabappel")
    frink, patty, selma = ctx.person("Frink"), ctx.person("Patty"), ctx.person("Selma")
    project = lambda name: in_project(ctx.projects, name)  # noqa: E731

    week = due_between(today, today + timedelta(days=6))
    next_week = due_between(today + timedelta(days=7), today + timedelta(days=13))
    month = due_between(today, ctx.month_end)
    friday = ctx.next_weekday(4)

    return [
        # -- person: how a person is named in the question
        Spec("person-surname", "person", "¿Qué compromisos tengo con Skinner?", with_user(user, skinner)),
        Spec("person-first-name", "person", "¿Qué compromisos tengo con Helen?", with_user(user, helen)),
        Spec("person-full-name", "person", "¿Qué compromisos tengo con Manjula Nahasapeemapetilon?", with_user(user, manjula)),
        Spec("person-lowercase", "person", "compromisos con milhouse", with_user(user, milhouse)),
        Spec("person-typo", "person", "¿Qué compromisos tengo con Krabapel?", with_user(user, edna)),
        Spec("person-by-role", "person", "¿Qué compromisos tengo con la Directora de Arte?", with_user(user, marge)),
        Spec("person-conversational", "person", "Che, cuando puedas, ¿me decís qué compromisos tengo con Marge?", with_user(user, marge)),
        Spec("person-ambiguous", "person", "¿Qué compromisos tengo con Bouvier?", any_of([with_user(user, patty), with_user(user, selma)], "")),
        Spec("person-two", "person", "¿Qué compromisos tengo con Edna o con Frink?", any_of([with_user(user, edna), with_user(user, frink)], "")),
        Spec("person-name-part-is-a-word", "person", "¿Qué compromisos van a vencer esta semana?", week),
        Spec("person-unknown", "person", "¿Qué compromisos tengo con Ned Flanders?", nothing("Ned Flanders is not in the catalog")),
        # -- direction: who promised and who received
        Spec("direction-user-promised", "direction", "¿Qué le prometí a Smithers?", who(user) & to_whom(smithers)),
        Spec("direction-user-received", "direction", "¿Qué me prometió Smithers?", who(smithers) & to_whom(user)),
        Spec("direction-promiser-any", "direction", "¿Qué prometió Frink?", who(frink)),
        Spec("direction-promiser-any-dated", "direction", "¿Qué compromisos con fecha prometió Frink?", who(frink) & dated()),
        Spec("direction-promiser-any-my-demo", "direction", "¿Qué prometió Frink para mi demo?", who(frink)),
        Spec("direction-promiser-any-request", "direction", "¿Me podés decir qué prometió Frink?", who(frink)),
        Spec("direction-recipient-any", "direction", "¿Qué le prometieron a Burns?", to_whom(burns)),
        Spec("direction-involves", "direction", "¿Qué compromisos abiertos involucran a Skinner?", who(skinner) | to_whom(skinner)),
        Spec("direction-involves-first-person", "direction", "¿Qué compromisos tengo abiertos que involucren a Skinner?", who(skinner) | to_whom(skinner)),
        Spec("direction-between-others", "direction", "¿Qué compromisos hay entre Frink y Manjula?", between(frink, manjula)),
        Spec("direction-directed-others", "direction", "¿Qué le prometió Skinner a Burns?", who(skinner) & to_whom(burns)),
        Spec("direction-mine", "direction", "¿Qué tengo que hacer yo?", who(user)),
        Spec("direction-owed-to-me", "direction", "¿Qué me deben?", to_whom(user)),
        # -- hierarchy: people reached through the org chart
        Spec("hierarchy-boss-promised", "hierarchy", "¿Qué le prometí a mi jefe?", who(user) & to_whom(boss)),
        Spec("hierarchy-boss-received", "hierarchy", "¿Qué me prometió mi jefe?", who(boss) & to_whom(user)),
        Spec("hierarchy-boss-synonym", "hierarchy", "¿Qué compromisos tengo con mi superior?", with_user(user, boss)),
        Spec("hierarchy-boss-of-boss", "hierarchy", "¿Qué compromisos tengo con el jefe de mi jefe?", with_user(user, ctx.manager_of(boss))),
        Spec("hierarchy-boss-of-other", "hierarchy", "¿Qué prometió el jefe de Edna?", who(ctx.manager_of(edna))),
        Spec("hierarchy-peers", "hierarchy", "¿Qué compromisos tengo con mis pares?", any_of([with_user(user, p) for p in ctx.peers()], "")),
        Spec(
            "hierarchy-reports-none",
            "hierarchy",
            "¿Qué compromisos tengo con la gente que me reporta?",
            any_of([with_user(user, p) for p in ctx.reports()], "the user has no direct reports"),
        ),
        # -- date: periods, single days and the absence of a date
        Spec("date-today", "date", "¿Qué vence hoy?", due_on(today)),
        Spec("date-tomorrow", "date", "¿Qué vence mañana?", due_on(today + timedelta(days=1))),
        Spec("date-viene-is-not-next-week", "date", "¿Qué viene esta semana?", week),
        Spec("date-next-week", "date", "¿Qué vence la semana que viene?", next_week),
        Spec("date-last-week", "date", "¿Qué venció la semana pasada?", due_between(today - timedelta(days=7), today - timedelta(days=1))),
        Spec("date-month", "date", "¿Qué vence este mes?", month),
        Spec("date-overdue", "date", "¿Qué compromisos están vencidos?", overdue(today)),
        Spec("date-undated", "date", "¿Qué compromisos no tienen fecha?", undated()),
        Spec("date-weekday", "date", "¿Qué vence el viernes?", due_on(friday)),
        Spec("date-absolute", "date", "¿Qué vence el 20 de octubre?", due_on(date(today.year, 10, 20))),
        Spec("date-range", "date", "¿Qué vence entre el 14 y el 16 de octubre?", due_between(date(today.year, 10, 14), date(today.year, 10, 16))),
        Spec("date-empty-day", "date", "¿Qué vence el 17 de octubre?", due_on(date(today.year, 10, 17))),
        # -- project: a project named fully, partly or not at all
        Spec("project-name", "project", "¿Qué compromisos hay del proyecto Jimboland?", project("Jimboland")),
        Spec("project-partial-name", "project", "¿Qué hay pendiente de Motocrotos?", project("Motocrotos Adventures")),
        Spec("project-none", "project", "¿Qué compromisos no pertenecen a ningún proyecto?", no_project()),
        Spec("project-unknown", "project", "¿Qué compromisos hay del proyecto Springfield Mall?", nothing("no project is called Springfield Mall")),
        # -- combination: two or three filters in one question
        Spec("combination-person-week", "combination", "¿Qué tengo esta semana con Smithers?", with_user(user, smithers) & week),
        Spec("combination-person-project", "combination", "¿Qué compromisos tengo con Frink del proyecto Motocrotos?", with_user(user, frink) & project("Motocrotos Adventures")),
        Spec(
            "combination-person-project-week",
            "combination",
            "¿Qué hay esta semana con Smithers del proyecto Turrokiller?",
            with_user(user, smithers) & week & project("Turrokiller"),
        ),
        Spec("combination-direction-date", "combination", "¿Qué me deben para mañana?", to_whom(user) & due_on(today + timedelta(days=1))),
        Spec(
            "combination-direction-person-weekday",
            "combination",
            "¿Qué le prometí a Smithers para el viernes?",
            who(user) & to_whom(smithers) & due_on(friday),
        ),
        Spec("combination-boss-direction-week", "combination", "¿Qué le debo a mi jefe esta semana?", who(user) & to_whom(boss) & week),
        Spec("combination-overdue-person", "combination", "¿Qué compromisos vencidos tengo con Patty?", with_user(user, patty) & overdue(today)),
        Spec("combination-undated-person", "combination", "¿Qué compromisos sin fecha tengo con Smithers?", with_user(user, smithers) & undated()),
        Spec("combination-project-month", "combination", "¿Qué vence este mes en Choripixels?", project("Choripixels") & month),
        # -- group: a set of people named by area
        Spec("group-with-area", "group", "¿Qué compromisos tengo con la gente de Arte?", any_of([with_user(user, p) for p in ctx.area("Arte")], "")),
        Spec("group-promised-area", "group", "¿Qué prometió el área de Programación?", any_of([who(p) for p in ctx.area("Programación")], "")),
        # -- topic: what the commitment is about, judged by the words of `what`
        Spec("topic-budget", "topic", "¿Qué compromisos hay sobre presupuesto?", what_has("presupuesto", "costo")),
        Spec("topic-bugs", "topic", "¿Qué compromisos hay sobre bugs?", what_has("bug", "crash")),
        Spec("topic-person-festival", "topic", "¿Qué tengo con Smithers sobre el festival?", with_user(user, smithers) & what_has("festival")),
        # -- open: questions that do not narrow anything
        Spec("open-how-is-everything", "open", "¿Cómo viene todo?", everything()),
        Spec("open-whats-going-on", "open", "¿Qué está pasando en el estudio?", everything()),
    ]
