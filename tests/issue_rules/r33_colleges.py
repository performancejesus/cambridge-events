"""33. «В колледжах» (исправляющая; рубрика решена 30.09, pipeline/colleges.py): 3–6 компактных строк, когда кандидатов
хватает; не больше 2 строк от одного колледжа; не службы и не evensong, не ADC / Footlights, не Kettle's Yard и музеи;
не дубль полного пункта; в строке — дата, колледж и площадка, цена или «бесплатно»."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 33, "«В колледжах»: 3–6 строк, ≤ 2 от колледжа, без служб и дублей", FIX


def check(ctx) -> Finding:
    from pipeline.colleges import NOT_HERE_VENUE_RE, SKIP_RE, candidates, college_of
    f = Finding()
    lines = [it for rub, it in ctx.model_items() if rub == "colleges"]
    full_events = {e for rub, it in ctx.model_items() if rub != "colleges" for i in it["ids"]
                   for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    per = {}
    for it in lines:
        c = ctx.pools.candidates.get(it["ids"][0]) or {}
        col = college_of(c)
        per[col] = per.get(col, 0) + 1
        if SKIP_RE.search(c.get("title") or "") or NOT_HERE_VENUE_RE.search(c.get("venue") or ""):
            f.violations.append(f"«{c.get('title')}»: служба / ADC / музей — не для этой рубрики")
        if set(c.get("event_ids") or []) & full_events:
            f.violations.append(f"«{c.get('title')}»: уже есть полным пунктом")
        if not it.get("price_ru"):
            f.violations.append(f"«{c.get('title')}»: нет цены или «бесплатно»")
    for col, n in per.items():
        if n > 2:
            f.violations.append(f"{col}: {n} строки (не больше 2)")
    if len(lines) > 6:
        f.violations.append(f"строк {len(lines)} — больше 6")
    avail = len(candidates(ctx.pools, full_events))
    if not lines and avail >= 3:
        f.violations.append(f"рубрики нет, хотя кандидатов {avail}")
    f.info.append(f"строк {len(lines)}, кандидатов {avail}")
    return f
