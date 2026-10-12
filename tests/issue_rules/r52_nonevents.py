"""52. Не события и частые регулярные — не в выпуске (исправляющая; правка 8 после v13 и правила отбора 7f): парковка,
страховка билета, пожертвования, подарочные карты, членство; дни открытых дверей школ и колледжей; бизнес-программы и
конференции; коворкинг; пункты приёма (E-waste — только у музея); дейтинг — никогда; ежедневные экскурсии, еженедельные
прогулки, библиотечные занятия, отдельные забеги parkrun; мероприятия школы для своих (правка 10 после v14: организатор —
школа). Фильтр — pipeline/selection.py до модели."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 52, "Не события и частые регулярные — не в выпуске", FIX


def check(ctx) -> Finding:
    from pipeline.page_times import cached_text
    from pipeline.selection import SCHOOL_RE, frequent_regular, nonevent_reason, school_event_reason
    f = Finding()
    for rub, it in ctx.model_items():
        if it.get("parkrun_line"):
            continue
        for i in it["ids"]:
            c = ctx.pools.candidates.get(i) or {}
            if c.get("kind") not in ("event", "announcement", "tickets"):
                continue
            why = nonevent_reason(c.get("title") or "", None, c.get("venue")) or frequent_regular(c) or (
                school_event_reason(c.get("title") or "", c.get("venue"), cached_text(c.get("url")))
                if SCHOOL_RE.search(c.get("venue") or "") else None)
            if why:
                f.violations.append(f"«{c.get('title')}» ({rub}): {why}")
    n = sum(len(v) for k, v in ctx.pools.excluded.items() if k.startswith(("не событие", "частое регулярное", "parkrun")))
    f.info.append(f"отсеяно до отбора: {n}")
    return f
