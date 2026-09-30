"""38. Кинотеатры округи (исправляющая; этап 7d, «собирать шире, публиковать уже»): показы кинотеатров зоны (S182 —
Wisbech, St Ives, King's Lynn, Peterborough, Haverhill) попадают в выпуск, только если их нет в Кембридже (Light, Arts
Picturehouse): фестивали, спецпоказы, трансляции. Обычный прокат округи — только в базе (regional_showings, с городом)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 38, "Кино округи — только то, чего нет в Кембридже", FIX


def check(ctx) -> Finding:
    from pipeline.issue import REGIONAL_CINEMA, REGIONAL_IN_CAMBRIDGE, _in_cambridge_cinemas
    f = Finding()
    n = 0
    for rub, it in ctx.model_items():
        for i in it["ids"]:
            c = ctx.pools.candidates.get(i) or {}
            if not c.get("sources") or not set(c["sources"]) <= REGIONAL_CINEMA:
                continue
            n += 1
            if _in_cambridge_cinemas(ctx.con, c["title"], ctx.w):
                f.violations.append(f"«{c['title']}» ({c.get('city')}): идёт и в Кембридже")
    dropped = len(ctx.pools.excluded.get(REGIONAL_IN_CAMBRIDGE, []))
    f.info.append(f"показов округи в выпуске {n}, снято как идущих в Кембридже {dropped}")
    return f
