"""36. Стадия открытия (блокирующая; правки по v10): в «Новом в городе» строка с датой и описание не противоречат друг
другу — «Открылось 28 сентября» и «скоро откроется» в описании (Bridge Bagels в v10) — блок; дата «скоро откроется» не
показывается как дата открытия (прошедшая дата или дата статьи). Сборка убирает пункт с противоречием
(issue_fixes.fix_stage_conflicts); проверка — что на готовом выпуске противоречий нет."""

from __future__ import annotations

import re

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 36, "«Новое в городе»: стадия открытия не противоречит описанию", BLOCK


def check(ctx) -> Finding:
    from pipeline import issue
    from pipeline.issue_fixes import OPENED_RE, SOON_RE, stage_conflict
    f = Finding()
    n = 0
    for rub, it in ctx.model_items():
        c = ctx.pools.candidates.get(it["ids"][0]) if it.get("ids") else None
        if not c or c.get("kind") != "venue_news":
            continue
        n += 1
        why = stage_conflict(c, it)
        if why:
            f.violations.append(f"«{it['title_ru']}»: {why}")
        if c.get("stage") == "coming_soon" and c.get("date"):
            dt = issue.d(c["date"])
            shown = issue.when(c, ctx.w, "ru")
            if re.search(r"\d", shown) and (c.get("date_basis") != "stated" or dt < ctx.w.issue):
                f.violations.append(f"«{it['title_ru']}»: «{shown}» — дата не открытия (скоро откроется)")
    for e in ctx.entries("ru"):
        if e["rubric"] == "new_in_town":
            if re.match(r"(?:Недавно )?[Оо]ткрыл", e["meta"]) and SOON_RE.search(e["blurb"]):
                f.violations.append(f"«{e['title']}»: «{e['meta']}», а в описании — «скоро откроется»")
            if re.match(r"Скоро откроется|Откроется", e["meta"]) and OPENED_RE.search(e["blurb"]):
                f.violations.append(f"«{e['title']}»: «{e['meta']}», а в описании — «открылось»")
    f.info.append(f"пунктов «Новое в городе»: {n}")
    return f
