"""57. «Новое в городе» (исправляющая; новый состав 11.10): только открытия и «скоро откроется»; без закрытий, заправок,
медцентров, похоронных и подобных, без безымянных «новая пиццерия»; повтор — при «скоро откроется» и ещё раз при
открытии, дальше не повторяется (отправленные выпуски, history.shown_places). Фильтр — selection.news_reason."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 57, "«Новое в городе»: только открытия, без закрытий и служебных мест, без повторов", FIX


def check(ctx) -> Finding:
    from pipeline import history
    from pipeline.selection import news_reason, norm_place
    f = Finding()
    shown = history.shown_places(ctx.con, ctx.w.issue)
    for rub, it in ctx.model_items():
        if rub != "new_in_town":
            continue
        c = ctx.pools.candidates.get(it["ids"][0]) or {}
        why = news_reason({"title": c.get("title"), "stage": c.get("stage"), "category": c.get("type")})
        if why:
            f.violations.append(f"«{c.get('title')}»: {why}")
        st = shown.get(norm_place(c.get("title")), set())
        if (c.get("stage") or "") in st or (st and c.get("stage") != "opened"):
            f.violations.append(f"«{c.get('title')}»: уже выходило ({', '.join(sorted(st))})")
    return f
