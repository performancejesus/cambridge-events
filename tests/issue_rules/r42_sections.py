"""42. «Секции: идёт набор» (исправляющая; этап 7e, п. 6): в подразделе «С детьми» — только регулярные секции с
объявленным набором (recruiting = open) или стартом новой группы в 3 недели; 2 строки, а в начале триместра и перед
каникулами — до 4; одна и та же секция — не чаще раза в 8 недель; не больше одной строки от провайдера; только открытые
для всех и в зоне выпуска. Взрослые новички (walking football и т. п.) — в «Спорт → Поучаствовать», до 2 строк.
Строки собирает pipeline/sections.py."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 42, "«Секции: идёт набор»: только с набором, 2–4 строки, раз в 8 недель, открытые для всех", FIX


def check(ctx) -> Finding:
    from pipeline.sections import busy_season, shown_recently
    f = Finding()
    lines = [(rub, it) for rub, it in ctx.model_items() if it.get("section_line")]
    adult = [(rub, it) for rub, it in ctx.model_items() if it.get("adult_line")]
    limit = 4 if busy_season(ctx.w) else 2
    if len(lines) > limit:
        f.violations.append(f"секций {len(lines)} (лимит {limit})")
    recent = shown_recently(ctx.con, ctx.w)
    orgs = []
    for rub, it in lines:
        c = ctx.pools.candidates[it["ids"][0]]
        if rub != "kids":
            f.violations.append(f"«{c['title']}»: секция не в «С детьми» ({rub})")
        if c.get("recruiting") != "open" and not c.get("starts"):
            f.violations.append(f"«{c['title']}»: набор не объявлен ({c.get('recruiting')})")
        if (c.get("audience") or "public") != "public":
            f.violations.append(f"«{c['title']}»: доступ только для своих")
        if it["ids"][0] in recent:
            f.violations.append(f"«{c['title']}»: уже было {recent[it['ids'][0]]} (раз в 8 недель)")
        orgs.append(c.get("provider"))
    if len(orgs) != len(set(orgs)):
        f.violations.append("две строки от одного провайдера")
    if len(adult) > 2:
        f.violations.append(f"строк для взрослых новичков {len(adult)} (до 2)")
    for rub, it in adult:
        if rub != "sport":
            f.violations.append(f"«{it['title_ru']}»: взрослые новички — не в «Спорте» ({rub})")
    f.info.append(f"секций {len(lines)} (лимит {limit}), взрослых строк {len(adult)}")
    return f
