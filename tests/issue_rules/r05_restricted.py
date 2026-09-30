"""5. Доступ restricted (блокирующая): не в выпуске (кроме детских программ с пометкой) и никогда в «Успейте».
Заодно: события «только для членов» (members) — с пометкой в строке с датой."""

from __future__ import annotations

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 5, "Доступ restricted — не в выпуске, никогда в «Успейте»", BLOCK
HURRY = ("Успейте записаться", "Hurry")


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        for c in e["cands"]:
            prog = c.get("kind") == "programme"
            restricted = c.get("access") == "restricted" or (prog and c.get("audience") not in (None, "", "public"))
            if not restricted:
                if c.get("access") == "members" and "только для членов" not in e["meta"]:
                    f.violations.append(f"«{e['title']}»: только для членов — нет пометки в строке с датой")
                continue
            if e["rubric"] == "tickets" or e["group"].startswith(HURRY):
                f.violations.append(f"«{e['title']}»: ограниченный доступ в «Успейте»")
            elif not prog:
                f.violations.append(f"«{e['title']}» ({e['rubric']}): доступ restricted — не для читателей")
            elif not any(x in e["meta"] for x in ("только для", "для семей с правом")):
                f.violations.append(f"«{e['title']}»: программа с ограничением без пометки")
    return f
