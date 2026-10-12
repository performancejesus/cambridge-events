"""66. Фестиваль, который идёт в окне выпуска, — карточкой (исправляющая; правка 8 после v14): Cambridge Film Festival
(22 октября – 1 ноября) стоял только строкой в «Фестивалях». Такой фестиваль — полная карточка в «Главном на выходные»
(при любой оценке, вне лимита категорий) или в теме недели; строка календаря для него не нужна. Отбор —
issue.running_festivals, build_issue.mandatory."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 66, "Фестиваль в окне выпуска — карточкой, не строкой календаря", FIX


def check(ctx) -> Finding:
    f = Finding()
    running = getattr(ctx.pools, "running_festivals", {}) or {}
    cards = {i for rub, it in ctx.model_items() if not it.get("line") for i in it["ids"]}
    card_events = {e for i in cards for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    for rec, cid in running.items():
        c = ctx.pools.candidates.get(cid) or {}
        if cid in cards or set(c.get("event_ids", [])) & card_events:
            continue
        f.violations.append(f"«{c.get('title')}»: идёт в окне выпуска, а карточки нет (только строка «Фестивалей»)")
    return f
