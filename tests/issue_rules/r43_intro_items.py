"""43. Вступление — только о том, что есть в выпуске (блокирующая; этап 7e, правки по v11: «тыквенные грядки и открытые
сады в окрестных деревнях» — ни тыкв, ни садов в выпуске нет). Каждое упоминание во вступлении и во вступлении темы
должно соответствовать пункту выпуска. Сборка сначала переписывает вступление (issue_fixes.fix_intro), проверка
сверяет ещё раз (Haiku, кэш text_fixes); без API — не проверялась."""

from __future__ import annotations

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 43, "Вступление — только о том, что есть в выпуске", BLOCK


def check(ctx) -> Finding:
    import os
    from pipeline.issue_fixes import intro_unsupported
    f = Finding()
    client = None
    if os.environ.get("EVENTS_ANTHROPIC_KEY") and ctx.options.get("api", True):
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    bad, _ = intro_unsupported(client, ctx.result, ctx.pools, ctx.w, ctx.con)
    if bad is None:
        f.skipped = "нет ключа API — сверка вступления не выполнялась"
        return f
    for x in bad:
        f.violations.append(f"{'вступление' if x['where'] == 'intro' else 'вступление темы'} ({x['lang']}): "
                            f"«{x['phrase']}» — {x['why']}")
    f.info.append("упоминаний вне выпуска: " + str(len(bad)))
    return f
