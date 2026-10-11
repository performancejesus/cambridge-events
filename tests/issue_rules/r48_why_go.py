"""48. «Почему стоит пойти» (исправляющая; итоги 7f, карточка события): одна фраза под полной карточкой — только
конкретный факт из источника (впервые / в последний раз / традиции N лет / только здесь / бесплатно / детям от N лет /
кто выступает); без рекламных общих слов; нет факта — строки нет; в компактных строках не бывает. Сверка с источником —
в проверках 2 и 43 (фраза входит в текст пункта). Исправляет issue_fixes.fix_why_go."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 48, "«Почему стоит пойти»: конкретный факт из источника, без рекламы", FIX


def check(ctx) -> Finding:
    from pipeline.issue_fixes import why_problem
    f = Finding()
    n = cards = 0
    for rub, it in ctx.model_items():
        if it.get("line"):
            if it.get("why_ru") or it.get("why_en"):
                f.violations.append(f"«{it.get('title_ru')}»: «Почему стоит пойти» в компактной строке")
            continue
        cards += 1
        if it.get("why_ru"):
            n += 1
            p = why_problem(it)
            if p:
                f.violations.append(f"«{it.get('title_ru')}»: {p} — «{it['why_ru'][:80]}»")
    f.info.append(f"«Почему стоит пойти» у {n} из {cards} карточек")
    return f
