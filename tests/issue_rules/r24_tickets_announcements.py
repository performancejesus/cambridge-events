"""24. «Успейте купить» — только с сигналом срочности со страницы; «Новые анонсы» — обязательные ежегодные события с
подтверждённой датой (Mill Road Winter Fair и т.п.) (исправляющая; build_issue.fits и mandatory)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 24, "«Успейте купить» — с сигналом; ежегодные — в «Новых анонсах»", FIX


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
            f.violations.append(f"«{c['title']}»: ежегодное событие с подтверждённой датой не в «Новых анонсах»")
    return f
