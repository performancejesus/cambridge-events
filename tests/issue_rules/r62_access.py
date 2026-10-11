"""62. Доступ к детским программам (исправляющая; правка 7 после v13): лагеря «только для детей сотрудников и студентов
университета» (Sport Cambridge, University Playscheme) и «только для учеников одной школы» — restricted: ни в выпуске, ни на
странице каникул (в базе хранятся); HAF-клубы для семей с правом на бесплатное питание — показываем с пометкой."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 62, "Каникулы: университетские и «для учеников школы» — не показываем; HAF — с пометкой", FIX


def check(ctx) -> Finding:
    from pipeline import issue
    f = Finding()
    for c in ctx.pools.candidates.values():
        if c.get("kind") == "programme" and c.get("audience") in ("university", "school_pupils"):
            f.violations.append(f"«{c.get('provider')} — {c.get('title')}»: {c['audience']} — в кандидатах")
    for e in ctx.entries("ru"):
        if e["rubric"] != "holidays":
            continue
        if re.search(r"сотрудников и студентов университета|учеников этой школы", e["meta"]):
            f.violations.append(f"«{e['title']}»: ограниченный доступ в письме")
        for c in e["cands"]:
            if c.get("audience") == "eligible" and issue.AUDIENCE["eligible"]["ru"] not in e["meta"]:
                f.violations.append(f"«{e['title']}»: HAF без пометки «{issue.AUDIENCE['eligible']['ru']}»")
    page = ctx.out_dir / issue.kids_page_name("all", None, "ru")
    if page.exists() and re.search(r"только для детей сотрудников и студентов университета|только для учеников этой школы",
                                   page.read_text()):
        f.violations.append(f"{page.name}: программа с ограниченным доступом на странице каникул")
    return f
