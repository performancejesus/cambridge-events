"""34. Cambridge Union (исправляющая; этап 7c, п. 3a): события «только для членов» не идут полными пунктами — одна
компактная строка «В Cambridge Union на этой неделе (для членов клуба): …» с гостями из termcard; открытые для всех —
обычными пунктами; кандидаты из статей Varsity без подтверждения termcard или cus.org — не в письме."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 34, "Cambridge Union: члены — одной строкой, открытые — пунктами", FIX


def check(ctx) -> Finding:
    f = Finding()
    n_line = 0
    for rub, it in ctx.model_items():
        if it.get("union"):
            n_line += 1
            if "для членов клуба" not in (it.get("title_ru") or ""):
                f.violations.append("строка Union без пометки «для членов клуба»")
            continue
        for i in it["ids"]:
            c = ctx.pools.candidates.get(i) or {}
            if "S049" in (c.get("sources") or []) and c.get("access") == "members" and not it.get("line"):
                f.violations.append(f"«{it['title_ru']}»: событие Union только для членов — полным пунктом")
    if n_line > 1:
        f.violations.append(f"строк Union: {n_line} (нужна одна)")
    f.info.append(f"строка Union: {'есть' if n_line else 'нет'}")
    return f
