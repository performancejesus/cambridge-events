"""50. Одно место дважды в рубрике (исправляющая; правка 2 после v13: «The Arbury Social» и «Arbury Social» в «Новом в
городе»). Название места нормализуется (артикль, пунктуация, «Cambridge», «café»…) и сверяется вместе с адресом.
Склейка — issue._venue_news и selection.norm_place."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 50, "Одно место дважды в рубрике («Новое в городе» и другие)", FIX


def check(ctx) -> Finding:
    from pipeline.selection import norm_place
    f = Finding()
    for rub in {r for r, _ in ctx.model_items()}:
        seen: dict[str, str] = {}
        for r, it in ctx.model_items():
            if r != rub or not it["ids"]:
                continue
            c = ctx.pools.candidates.get(it["ids"][0]) or {}
            if c.get("kind") != "venue_news":
                continue
            key = norm_place(c.get("title"))
            if key in seen:
                f.violations.append(f"{rub}: «{seen[key]}» и «{c.get('title')}» — одно место")
            seen[key] = c.get("title")
    return f
