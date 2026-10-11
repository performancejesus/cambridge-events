"""24. «Успейте купить» — только с сигналом срочности со страницы (этап 7g: рубрика только в редакторской версии);
обязательные ежегодные события с подтверждённой датой (Mill Road Winter Fair, Cambridge Half Marathon 2027 и т.п.) —
в выпуске: строкой «Объявлено» в тематической рубрике или в календаре «Фестивали» (исправляющая; pipeline/lines.py,
pipeline/festivals.py; ответ 06.10 — Half Marathon 2027 в рубрику)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 24, "«Успейте купить» — с сигналом; ежегодные анонсы — «Объявлено» или «Фестивали»", FIX


def check(ctx) -> Finding:
    f = Finding()
    placed_ev = set()
    for rub, it in ctx.model_items():
        for i in it["ids"]:
            c = ctx.pools.candidates.get(i) or {}
            placed_ev |= set(c.get("event_ids") or [])
            if rub == "tickets" and not (c.get("urgency") or c.get("page_urgency")):
                f.violations.append(f"«{it['title_ru']}»: в «Успейте купить» без сигнала срочности")
    for cid, c in ctx.pools.candidates.items():
        if c["kind"] == "announcement" and "ежегодного" in (c.get("evidence") or "") and (c.get("importance") or 0) >= 6 \
                and not set(c["event_ids"]) & placed_ev:
            f.violations.append(f"«{c['title']}»: ежегодное событие с подтверждённой датой не в выпуске "
                                f"(ни строкой «Объявлено», ни в «Фестивалях»)")
    return f
