"""22. Разнообразие (исправляющая; build_issue.weekdays_rules, check_kids, mandatory): не больше 2 пунктов с одной
площадки в рубрике (в «С детьми» — 1, пока есть другие); в «На неделе» — хотя бы один театр или танец, если есть
кандидат ≥ 4."""

from __future__ import annotations

from pipeline.normalize import norm_venue
from . import FIX, Finding

RULE, TITLE, LEVEL = 22, "Разнообразие площадок; театр в «На неделе»", FIX


def check(ctx) -> Finding:
    from scripts.build_issue import fits, is_compact
    f = Finding()
    used = {i for _, it in ctx.model_items() for i in it["ids"]}
    for sec in ctx.result["sections"]:
        rub = sec["rubric"]
        if rub in ("theme", "new_in_town", "cancelled", "cinema") or rub.startswith("weekend_"):
            continue
        venues = [norm_venue((ctx.pools.candidates.get(it["ids"][0]) or {}).get("venue") or "") for it in sec["items"]
                  if not is_compact(it, ctx.pools)]
        venues = [v for v in venues if v]
        limit = 1 if rub == "kids" else 2
        for v in sorted(set(venues)):
            if venues.count(v) > limit:
                others = [c for cid, c in ctx.pools.candidates.items() if cid not in used and fits(rub, c, ctx.w)
                          and norm_venue(c.get("venue") or "") not in venues and cid[0] == "E"]
                if rub != "kids" or others:
                    f.violations.append(f"{rub}: {venues.count(v)} пункта с площадки {v}")
    wk = [it for sec in ctx.result["sections"] if sec["rubric"] == "weekdays" for it in sec["items"]]
    if wk and not any((ctx.pools.candidates.get(i) or {}).get("theatre") for it in wk for i in it["ids"]):
        th = [c for cid, c in ctx.pools.candidates.items() if c.get("theatre") and c["kind"] == "event"
              and fits("weekdays", c, ctx.w) and (c.get("importance") or 0) >= 4 and cid not in used]
        if th:
            f.violations.append(f"«На неделе»: нет театра или танца, кандидаты были ({th[0]['title']})")
    return f
