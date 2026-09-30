"""28. Пропуск с оценкой не ниже выбранного — с причиной (исправляющая; build_issue.fill_reasons — один короткий
запрос к модели за причинами)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 28, "Пропуски с оценкой не ниже выбранного — с причиной", FIX


def check(ctx) -> Finding:
    f = Finding()
    if ctx.lists is None:
        f.skipped = "списки редакторской версии не построены"
        return f
    for x in ctx.missing_reasons:
        f.violations.append(x)
    return f
