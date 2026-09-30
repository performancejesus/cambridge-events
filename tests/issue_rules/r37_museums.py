"""37. «В музеях и усадьбах» (исправляющая; этап 7d, pipeline/museums.py): 4–6 компактных строк, когда кандидатов хватает;
не больше 2 строк от одного места; без регулярных занятий (parkrun, еженедельные прогулки) и служебных событий; выставка —
только в первую неделю открытия; не дубль полного пункта; в строке — дата, место, цена или «по входному билету»."""

from __future__ import annotations

from datetime import timedelta

from . import FIX, Finding

RULE, TITLE, LEVEL = 37, "«В музеях и усадьбах»: 4–6 строк, ≤ 2 от места, без регулярных занятий и дублей", FIX


def check(ctx) -> Finding:
    from pipeline import issue
    from pipeline.museums import LINES_MAX, LINES_MIN, NEW_EXHIBITION_DAYS, PER_PLACE, SKIP_RE, candidates, kind_of, place_of
    f = Finding()
    lines = [it for rub, it in ctx.model_items() if rub == "museums"]
    full_events = {e for rub, it in ctx.model_items() if rub != "museums" for i in it["ids"]
                   for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    per = {}
    for it in lines:
        c = ctx.pools.candidates.get(it["ids"][0]) or {}
        place = place_of(c)
        per[place] = per.get(place, 0) + 1
        if not place:
            f.violations.append(f"«{c.get('title')}»: не музей и не усадьба из списка мест")
        if SKIP_RE.search(c.get("title") or "") or c.get("regular_series"):
            f.violations.append(f"«{c.get('title')}»: регулярное или служебное занятие")
        if set(c.get("event_ids") or []) & full_events:
            f.violations.append(f"«{c.get('title')}»: уже есть полным пунктом")
        if not it.get("price_ru"):
            f.violations.append(f"«{c.get('title')}»: нет цены, «бесплатно» или «по входному билету»")
        if kind_of(c) == "exhibition" and c.get("dates"):
            first = min(issue.d(x[0]) for x in c["dates"])
            if first < ctx.w.issue - timedelta(days=NEW_EXHIBITION_DAYS):
                f.violations.append(f"«{c.get('title')}»: выставка открылась {first} — не новая")
    for place, n in per.items():
        if n > PER_PLACE:
            f.violations.append(f"{place}: {n} строки (не больше {PER_PLACE})")
    if len(lines) > LINES_MAX:
        f.violations.append(f"строк {len(lines)} — больше {LINES_MAX}")
    avail = len(candidates(ctx.pools, full_events, ctx.w))
    if not lines and avail >= LINES_MIN:
        f.violations.append(f"рубрики нет, хотя кандидатов {avail}")
    f.info.append(f"строк {len(lines)}, кандидатов {avail}, мест {len(per)}")
    return f
