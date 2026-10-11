"""55. Разнообразие и «Главное» (исправляющая; итоги 7f и ранжирование 11.10): «Главное на выходные» — до 10 событий,
не больше 2 одной категории (kids, museum, concert, comedy, theatre, sport, traditions, talk…); в остальных рубриках —
не больше 2 пунктов одного подвида (фотография, керамика, органные концерты…). Детские и музейные события в «Главном» —
приоритет редакции (счёт — в info)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 55, "Разнообразие: «Главное» ≤ 10 и ≤ 2 на категорию; ≤ 2 одного подвида в рубрике", FIX


def check(ctx) -> Finding:
    from scripts.build_issue import SUBTYPE_MAX, WEEKEND_PER_CATEGORY, subtype
    f = Finding()
    info = []
    by_rub: dict[str, list[dict]] = {}
    for rub, it in ctx.model_items():
        if it["ids"] and not it.get("line") and it["ids"][0] in ctx.pools.candidates:
            by_rub.setdefault(rub, []).append(ctx.pools.candidates[it["ids"][0]] | {"_t": it.get("title_ru")})
    for rub, cs in by_rub.items():
        if rub.startswith("weekend_"):
            if len(cs) > 10:
                f.violations.append(f"{rub}: {len(cs)} пунктов — больше 10")
            cats: dict[str, int] = {}
            for c in cs:
                cats[c.get("category") or "other"] = cats.get(c.get("category") or "other", 0) + 1
            for cat, n in cats.items():
                if n > WEEKEND_PER_CATEGORY and cat != "other" and not all(c.get("quirky") for c in cs if c.get("category") == cat):
                    f.violations.append(f"{rub}: {n} пунктов категории «{cat}» (не больше {WEEKEND_PER_CATEGORY})")
            info.append(f"{rub}: детских {cats.get('kids', 0)}, музейных {cats.get('museum', 0)} из {len(cs)}")
        elif rub not in ("theme", "cinema", "new_in_town"):
            sub: dict[str, int] = {}
            for c in cs:
                s = subtype(c)
                sub[s] = sub.get(s, 0) + 1
            for s, n in sub.items():
                if n > SUBTYPE_MAX and s not in ("other", "concert", "theatre"):
                    f.violations.append(f"{rub}: {n} пунктов подвида «{s}» (не больше {SUBTYPE_MAX})")
    f.info += info
    return f
