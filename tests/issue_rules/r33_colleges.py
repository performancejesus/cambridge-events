"""33. «В колледжах» (исправляющая): рубрика убрана решением редактора 11.10 (этап 7g) — лекции колледжей идут в «Лекции
и встречи», выставки колледжей — в «Музеи, выставки и усадьбы». Проверка: рубрики «В колледжах» в выпуске нет; событие
колледжа не стоит в выпуске дважды; службы и evensong в выпуск не идут."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 33, "«В колледжах» убрана: события колледжей — в тематических рубриках, без служб и дублей", FIX


def check(ctx) -> Finding:
    from pipeline.colleges import SKIP_RE, college_of
    f = Finding()
    seen: dict[int, str] = {}
    n = 0
    for rub, it in ctx.model_items():
        if rub == "colleges":
            f.violations.append(f"«{it.get('title_ru')}»: рубрика «В колледжах» убрана (11.10)")
        for i in it["ids"]:
            c = ctx.pools.candidates.get(i) or {}
            if c.get("kind") != "event" or not college_of(c):
                continue
            n += 1
            if SKIP_RE.search(c.get("title") or ""):
                f.violations.append(f"«{c.get('title')}»: служба / evensong — не для выпуска")
            for e in c.get("event_ids") or []:
                if e in seen and seen[e] != rub:
                    f.violations.append(f"«{c.get('title')}»: дважды — {seen[e]} и {rub}")
                seen[e] = rub
    f.info.append(f"событий колледжей в выпуске: {n}")
    return f
