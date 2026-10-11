"""35. Грамматика русских текстов (исправляющая; правки по v10: «с развлечениями, еде и фейерверком»): все русские
тексты выпуска — вступления, описания, строки «Каникул» — вычитываются одним запросом к Haiku (только падежи и
согласование, issue_fixes.fix_grammar); исправления — в «Для редактора». Проверка: вычитка выполнена, исправления
попали в итоговый текст; правки, где модель поменяла больше окончаний, не приняты — редактору.

Прогон 7e+ (решение 01.10, «Режиссёр Director Roddy Bogawa»): английское слово, дублирующее соседнее русское, —
без модели (issue_fixes.en_dupes / fix_en_dupes); проверка 8 ловит только смешанные буквы внутри слова.
Этап 7g: английские заглушки («(not specified)», TBC, N/A, unknown — правка 3), смешанные названия лиг («Лиги One» →
«Первой лиги (League One)» — правка 6), нарицательные английские слова внутри русской фразы (Greenland, archery —
итоги 7f; исправляет issue_fixes.fix_stray_english)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 35, "Грамматика русских текстов (падежи, согласование) — вычитка", FIX


def check(ctx) -> Finding:
    from pipeline.issue_fixes import en_dupes
    f = Finding()
    for where, text in ctx.texts("ru"):   # английское слово-дубль рядом с русским — без модели, всегда
        for ru, en in en_dupes(text):
            f.violations.append(f"«{where}»: английское слово-дубль «{ru} {en}»")
    from pipeline.issue_fixes import issue_names, mixed_leagues, placeholders, stray_english
    names = issue_names(ctx.pools)
    for rub, it in ctx.model_items():
        for fld in ("title_ru", "blurb_ru", "where_ru", "price_ru", "meta_ru", "why_ru", "blurb_en", "title_en", "why_en"):
            t = it.get(fld) or ""
            if not isinstance(t, str):
                continue
            for p in placeholders(t):
                f.violations.append(f"«{it.get('title_ru')}»: английская заглушка «{p}» ({fld})")
            if fld.endswith("_ru"):
                for m in mixed_leagues(t):
                    f.violations.append(f"«{it.get('title_ru')}»: смешанное название лиги «{m}»")
                if fld in ("blurb_ru", "why_ru"):
                    for wd in stray_english(t, names + " " + (it.get("title_en") or "")):
                        f.warnings.append(f"«{it.get('title_ru')}»: английское слово в русской фразе — «{wd}»")
    if ctx.result.get("en_dupes_fixed"):
        f.info.append(f"английских слов-дублей убрано: {len(ctx.result['en_dupes_fixed'])}")
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
