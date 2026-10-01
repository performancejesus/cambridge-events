"""46. Роли участников — только из источника (исправляющая; этап 7e, правки по v11: «на разогреве Soft Machine», хотя в
источнике оба названы среди исполнителей). «Хедлайнер», «на разогреве», «special guest» — только если так в данных
события (описания всех склеенных записей и несклеенных дублей). Исправляет issue_fixes.fix_roles (Haiku)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 46, "Роли и порядок участников («хедлайнер», «на разогреве») — только из источника", FIX


def check(ctx) -> Finding:
    from pipeline.issue_fixes import unsupported_roles
    f = Finding()
    for it, words in unsupported_roles(ctx.result, ctx.pools):
        f.violations.append(f"«{it['title_ru']}»: {words} — в данных так не сказано")
    return f
