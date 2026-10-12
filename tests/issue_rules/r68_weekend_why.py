"""68. «Главное на выходные» меньше 10 пунктов — в редакторской версии сказано почему (исправляющая; правка 12 после v14):
сколько кандидатов выше порога, сколько стоят в других рубриках, в каких категориях упёрлись в лимит 2 на категорию,
сколько категорий есть. build_issue.weekend_shortfall → result["weekend_why"]."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 68, "«Главное на выходные» < 10 — редактору объяснено почему", FIX


def check(ctx) -> Finding:
    from scripts.build_issue import RUBRIC_LIMITS
    f = Finding()
    why = ctx.result.get("weekend_why") or {}
    for sec in ctx.result["sections"]:
        if sec["rubric"].startswith("weekend_") and len(sec["items"]) < RUBRIC_LIMITS["weekend"][1]:
            if not (why.get(sec["rubric"]) or {}).get("ru"):
                f.violations.append(f"{sec['rubric']}: {len(sec['items'])} пунктов, а причины в редакторской версии нет")
            else:
                f.info.append(f"{sec['rubric']}: {why[sec['rubric']]['ru']}")
    return f
