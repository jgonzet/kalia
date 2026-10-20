"""Check that the judge of the chat (`scripts/chat_judge.py`) tells apart the ways an answer can go wrong.

    uv run scripts/check_chat_judge.py

It needs no dataset and no LLM: it uses a made-up company defined here, with the traps the judge has to survive (two people
who share a surname, a title before a name, a particle inside a name, a commitment with no date), and judges answers
written by hand for it. One is perfect and the others have one thing changed each (a commitment left out, a person changed,
the direction inverted, a date changed, a commitment invented, one that was not needed, a paraphrase, an empty answer). It
exits 1 if the judge does not see exactly what was changed. Like `check_bank_sensitivity.py`, it shows what the numbers of
`scripts/evaluate_chat.py` can and cannot notice, so a change of the judge is checked here before its numbers are read.
The CI runs it. The small checks of its parts (dates, names, lines) are in `tests/test_chat_judge.py`.
"""

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_judge import Item, Judgement, judge  # noqa: E402

YEAR = 2026
USER = "u"
NAMES = {
    "u": "Ana Ruiz",  # the user
    "b": "Bruno Vega",
    "l": "Lucía Pérez",  # shares a surname with the next one
    "m": "Marta Pérez",
    "s": "Profesor Soto",  # a title before the name
    "v": "Víctor Van Der Berg",  # particles in the name
}
MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

NEEDED = [
    Item("n1", "b", "u", "enviar el informe mensual de ventas", date(2026, 10, 14), True),
    Item("n2", "u", "b", "organizar la reunión de planificación trimestral", date(2026, 10, 20), True),
    Item("n3", "b", "u", "definir el presupuesto del próximo semestre", None, True),
    Item("n4", "u", "l", "revisar el diseño de la pantalla inicial", date(2026, 10, 16), True),
]
NOISE = [
    Item("x1", "l", "m", "actualizar la documentación del servicio", date(2026, 10, 22), False),
    Item("x2", "s", "u", "preparar la demo para los clientes", date(2026, 10, 15), False),
    Item("x3", "v", "b", "migrar la base de datos de clientes", date(2026, 10, 30), False),
]
ITEMS = NEEDED + NOISE
INVENTED = "- Bruno Vega -> Ana Ruiz: revisar el contrato del proveedor externo, 2026-10-30"


@dataclass(frozen=True)
class Case:
    name: str
    answer: str
    missing: int = 0  # needed commitments not in the answer
    noise: int = 0  # commitments that were not needed and are in the answer
    wrong_people: int = 0
    wrong_due: int = 0
    invented: int = 0


def line(item: Item, who: str | None = None, to_whom: str | None = None, due: str | None = None) -> str:
    """One bullet in the format the prompt asks for, with any part of it replaceable."""
    when = due if due is not None else (item.due.isoformat() if item.due else "sin fecha")
    return f"- {who or NAMES[item.who]} -> {to_whom or NAMES[item.to_whom]}: {item.what}, {when}"


def prose(item: Item) -> str:
    """The commitment in running prose: the user as "yo" and "vos", the date written out."""
    who = "yo" if item.who == USER else NAMES[item.who]
    to_whom = "vos" if item.to_whom == USER else NAMES[item.to_whom]
    when = f"el {item.due.day} de {MONTH_NAMES[item.due.month - 1]}" if item.due else "sin fecha"
    return f"- {who} -> {to_whom}: {item.what}, {when}"


def replace(target: Item, new: str) -> str:
    """The perfect answer with the line of one commitment replaced."""
    return "\n".join(new if item is target else line(item) for item in NEEDED)


def cases() -> list[Case]:
    perfect = [line(i) for i in NEEDED]
    dated, undated = NEEDED[0], NEEDED[2]
    return [
        Case("perfect", "\n".join(perfect)),
        Case("one commitment left out", "\n".join(perfect[1:]), missing=1),
        Case("a person changed", replace(dated, line(dated, who=NAMES["l"])), wrong_people=1),
        Case("direction inverted", replace(dated, line(dated, who=NAMES["u"], to_whom=NAMES["b"])), wrong_people=1),
        Case("a date changed", replace(dated, line(dated, due="2026-12-24")), wrong_due=1),
        Case("a date given to an undated commitment", replace(undated, line(undated, due="2026-12-24")), wrong_due=1),
        Case("a commitment invented", "\n".join(perfect + [INVENTED]), invented=1),
        Case("a commitment not needed", "\n".join(perfect + [line(NOISE[0])]), noise=1),
        Case("with headers and prose around", "Estos son tus compromisos:\n\nVentas\n" + "\n".join(perfect) + "\n\nAvisame si necesitás algo más."),
        Case("paraphrased", "\n".join(f"* {NAMES[i.who]} le debe a {NAMES[i.to_whom]}: {i.what} (para el {i.due or 'sin fecha'})" for i in NEEDED)),
        Case("shortened, still most of the words", replace(NEEDED[1], line(NEEDED[1]).replace("la reunión de planificación trimestral", "la reunión trimestral"))),
        Case("worded so differently that it is not found", replace(NEEDED[1], line(NEEDED[1]).replace("organizar la reunión de planificación trimestral", "armar la reunión")), missing=1, invented=1),  # the known limit: it counts as left out and as invented
        Case("date written out and the user as 'yo'", "\n".join(prose(i) for i in NEEDED)),
        Case("a surname shared by two people: the other one", replace(NEEDED[3], line(NEEDED[3], to_whom=NAMES["m"])), wrong_people=1),
        Case("a surname shared by two people: only the surname", replace(NEEDED[3], line(NEEDED[3], to_whom="Pérez"))),
        Case("a title before a name", "\n".join(perfect + [line(NOISE[1], who="Soto")]), noise=1),
        Case("a name with particles", "\n".join(perfect + [line(NOISE[2], who="Víctor Van Der Berg")]), noise=1),
        Case("empty answer", "", missing=len(NEEDED)),
        Case("says there is nothing", "No encontré compromisos que respondan tu pregunta.", missing=len(NEEDED)),
    ]


def seen(j: Judgement) -> dict[str, int]:
    return {
        "missing": len(j.needed_missing),
        "noise": len(j.noise_present),
        "wrong_people": len(j.wrong_people),
        "wrong_due": len(j.wrong_due),
        "invented": len(j.invented),
    }


def main() -> int:
    failures = 0
    print(f"{'case':<50}{'missing':>8}{'noise':>6}{'people':>7}{'due':>5}{'invented':>9}")
    for case in cases():
        result = seen(judge(case.answer, ITEMS, NAMES, USER, YEAR))
        want = {"missing": case.missing, "noise": case.noise, "wrong_people": case.wrong_people, "wrong_due": case.wrong_due, "invented": case.invented}
        ok = result == want
        failures += not ok
        print(f"{case.name:<50}{result['missing']:>8}{result['noise']:>6}{result['wrong_people']:>7}{result['wrong_due']:>5}{result['invented']:>9}  {'ok' if ok else f'FAIL (expected {want})'}")
    print("\nall cases seen as expected" if not failures else f"\n{failures} case(s) not seen as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
