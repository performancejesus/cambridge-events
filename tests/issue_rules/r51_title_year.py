"""51. Год в названии не совпадает с годом дат (исправляющая; правка 4 после v13: «Wisbech Science Centre — School
holidays (Oct 2027)» стоял на 26–30 октября 2026). Программы с таким противоречием не берутся в кандидаты (у источника
ошибка — проверить), события — в пункте не должно быть."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 51, "Год в названии = год дат пункта", FIX


def year_conflict(title: str, dates: list) -> str | None:
    years = set(re.findall(r"\b(20\d\d)\b", title or ""))
    if not years or not dates:
        return None
    have = {str(x[0])[:4] for x in dates if x and x[0]} | {str(x[1])[:4] for x in dates if x and len(x) > 1 and x[1]}
    if have and not years & have:
        return f"в названии {', '.join(sorted(years))}, даты — {', '.join(sorted(have))}"
    return None


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        for c in e["cands"]:
            why = year_conflict(e["title"], c.get("dates") or [])
            if why:
                f.violations.append(f"«{e['title']}»: {why}")
    for c in ctx.pools.candidates.values():
        if c.get("kind") == "programme":
            why = year_conflict(c.get("title"), c.get("dates") or [])
            if why:
                f.violations.append(f"программа «{c.get('provider')} — {c.get('title')}»: {why}")
    return f
