"""21. «Главное на выходные» (исправляющая; build_issue.fits + validate): за городом («до часа», «Кембриджшир, дальше
часа») — только от 8; минимум 2 из 3–4 пунктов в Кембридже или до 30 минут; «По графству» — от 5."""

from __future__ import annotations

from pipeline import issue
from . import FIX, Finding

RULE, TITLE, LEVEL = 21, "«Главное на выходные» и «По графству» — пороги зон", FIX


def check(ctx) -> Finding:
    f = Finding()
    by = {}
    for rub, it in ctx.model_items():
        c = ctx.pools.candidates.get(it["ids"][0]) or {}
        imp = issue.importance_of(ctx.pools, it)
        if rub.startswith("weekend_"):
            by.setdefault(rub, []).append(c.get("zone"))
            if c.get("zone") in ("до часа", issue.geo_COUNTY_FAR) and imp < issue.COUNTY_WEEKEND_MIN:
                f.violations.append(f"«{it['title_ru']}» ({rub}): {c.get('zone')}, оценка {imp:g} < 8")
        if rub == "county" and imp < issue.COUNTY_MIN:
            f.violations.append(f"«{it['title_ru']}» (По графству): оценка {imp:g} < 5")
    for rub, zones in by.items():
        near = sum(z in ("центр", "до 30 мин") for z in zones)
        if len(zones) >= 3 and near < 2:
            f.violations.append(f"{rub}: в Кембридже и до 30 мин — {near} из {len(zones)}")
    return f
