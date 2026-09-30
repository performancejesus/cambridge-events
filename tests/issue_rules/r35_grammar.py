"""35. Грамматика русских текстов (исправляющая; правки по v10: «с развлечениями, еде и фейерверком»): все русские
тексты выпуска — вступления, описания, строки «Каникул» — вычитываются одним запросом к Haiku (только падежи и
согласование, issue_fixes.fix_grammar); исправления — в «Для редактора». Проверка: вычитка выполнена, исправления
попали в итоговый текст; правки, где модель поменяла больше окончаний, не приняты — редактору."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 35, "Грамматика русских текстов (падежи, согласование) — вычитка", FIX


def check(ctx) -> Finding:
    f = Finding()
    g = ctx.result.get("grammar")
    if not g:
        f.skipped = "вычитка не выполнялась (сборка без постобработки)"
        return f
    if g.get("skipped"):
        f.skipped = g["skipped"]
        return f
    for x in g.get("rejected", []):
        f.warnings.append(f"{x['where']}: правка не принята автоматически — {'; '.join(x['fixes'])[:200]}")
    html = ctx.html.get("reader_ru") or ""
    for x in g.get("fixed", []):
        for fx in x["fixes"]:
            if "→" in fx:
                old, new = (p.strip(" «»\"") for p in fx.split("→", 1))
                if html and old and new and old != new and old in html and new not in html:
                    f.violations.append(f"{x['where']}: «{old}» осталось в тексте")
    f.info.append(f"текстов вычитано {g.get('checked', 0)}, исправлено {len(g.get('fixed', []))}, "
                  f"не принято {len(g.get('rejected', []))}")
    return f
