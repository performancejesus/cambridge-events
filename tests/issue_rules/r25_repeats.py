"""25. Повторы (исправляющая; issue._drop_repeats): показанное в выпусках за 4 недели (история issue_items, даты отправки
раньше этой) не повторяется без нового повода (анонс → событие наступило; новая отмена)."""

from __future__ import annotations

from pipeline import history
from . import FIX, Finding

RULE, TITLE, LEVEL = 25, "Повторы между выпусками (issue_items, 4 недели)", FIX


def check(ctx) -> Finding:
    f = Finding()
    seen = history.shown_before(ctx.con, ctx.w.issue)
    for rub, it in ctx.model_items():
        for i in it["ids"]:
            c = ctx.pools.candidates.get(i) or {}
            k = i[:1]
            keys = [c.get("news_id")] if k == "V" else c.get("event_ids") or []
            kinds = "AT" if k in "AT" else k
            prev = [seen.get(x, {}).get(e) for x in kinds for e in keys]
            prev = [p for p in prev if p]
            if prev:
                f.violations.append(f"«{it['title_ru']}»: уже было в выпуске от {max(prev)}")
    f.info.append(f"выпусков в истории за 4 недели до {ctx.w.issue}: "
                  f"{len({d for v in seen.values() for d in v.values()})}")
    return f
