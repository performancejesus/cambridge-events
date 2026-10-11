"""61. Состав рубрик (исправляющая; новый состав 11.10): порядок — тема, «Главное», «На неделе», «В кино», «Лекции и
встречи», «Музеи, выставки и усадьбы», «Научиться», «Спорт», «Фестивали», «Волонтёрство», «Каникулы», «С детьми»,
«Новое в городе»; убраны «В колледжах», «Выставки», «Бесплатно», «За городом», «Новые анонсы»; «Успейте купить»,
«Отменено», «По графству», «Не подошло» — только в редакторской версии. Анонсы — строками «Объявлено» (не больше 3 на
рубрику)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 61, "Состав рубрик 11.10: убранные не выводятся, редакторские — не в письме", FIX


def check(ctx) -> Finding:
    from pipeline import issue
    from pipeline.lines import ANNOUNCE_MAX
    f = Finding()
    L = ctx.layout("ru")
    order = [s["rubric"] for s in L["sections"]]
    for rub in order:
        if rub in issue.REMOVED_RUBRICS:
            f.violations.append(f"рубрика «{issue.RUBRIC_TITLES['ru'].get(rub, rub)}» убрана, а в письме есть")
        if rub in issue.EDITOR_ONLY:
            f.violations.append(f"«{issue.RUBRIC_TITLES['ru'].get(rub, rub)}» — только для редактора, а в письме есть")
    want = [r for r in ctx.w.rubrics() if r in order]
    if order != want:
        f.violations.append(f"порядок рубрик: {order} (нужно {want})")
    html = ctx.html.get("reader_ru") or ""
    for t in ("Новые анонсы", "За городом (до часа)", "В колледжах", "Успейте купить билеты", "По графству"):
        if f"<h2>{t}" in html:
            f.violations.append(f"в читательской версии — рубрика «{t}»")
    for sec in L["sections"]:
        n = sum(1 for g in sec["groups"] if g["title"] == "Объявлено" for _ in g["items"])
        if n > ANNOUNCE_MAX:
            f.violations.append(f"«{sec['title']}»: строк «Объявлено» {n} (не больше {ANNOUNCE_MAX})")
    f.info.append("рубрики письма: " + ", ".join(order))
    return f
