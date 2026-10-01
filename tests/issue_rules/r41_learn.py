"""41. «Научиться» (исправляющая; этап 7e, п. 5): курсы и мастер-классы для взрослых — 4–6 компактных строк (меньше 3
кандидатов — рубрика не выводится); разовые занятия — в окне выпуска, курсы — со стартом в ближайшие 3 недели; не больше
2 строк от одного организатора; распроданное, детское, онлайн и вне зоны — нет; у дорогих программ (от £200) — цена,
без оценок «выгодно»; событие, уже стоящее полным пунктом, не дублируется. Строки собирает pipeline/courses.py."""

from __future__ import annotations

from datetime import date, timedelta

from . import FIX, Finding

RULE, TITLE, LEVEL = 41, "«Научиться»: 4–6 строк, ≤ 2 от организатора, курсы со стартом в 3 недели, цена у дорогих", FIX


def check(ctx) -> Finding:
    from pipeline.courses import COURSE_AHEAD_DAYS, EXPENSIVE, NOT_LEARN_RE, PER_ORG, VALUE_RE
    f = Finding()
    sec = next((s for s in ctx.result["sections"] if s["rubric"] == "learn"), None)
    items = (sec or {}).get("items") or []
    if not items:
        f.info.append("рубрики нет (меньше 3 кандидатов)")
        return f
    if not 3 <= len(items) <= 6:
        f.violations.append(f"строк {len(items)} (нужно 4–6)")
    per: dict[str, int] = {}
    full = {e for rub, it in ctx.model_items() if rub != "learn" for i in it["ids"]
            for e in (ctx.pools.candidates.get(i) or {}).get("event_ids", [])}
    for it in items:
        c = ctx.pools.candidates[it["ids"][0]]
        org = (c.get("provider") or c.get("venue") or "").lower()
        per[org] = per.get(org, 0) + 1
        d0 = date.fromisoformat(c["dates"][0][0])
        if c.get("course_kind") == "course":
            if not ctx.w.start <= d0 <= ctx.w.issue + timedelta(days=COURSE_AHEAD_DAYS):
                f.violations.append(f"«{c['title']}»: курс стартует {d0} — не в ближайшие 3 недели")
        elif not ctx.w.start <= d0 <= ctx.w.end:
            f.violations.append(f"«{c['title']}»: занятие {d0} — вне окна выпуска")
        if NOT_LEARN_RE.search(c["title"]):
            f.violations.append(f"«{c['title']}»: детское, онлайн, лекция или не занятие")
        if set(c.get("event_ids") or []) & full:
            f.violations.append(f"«{c['title']}»: уже стоит полным пунктом")
        if (c.get("price_from") or 0) >= EXPENSIVE and "£" not in (it.get("price_ru") or ""):
            f.violations.append(f"«{c['title']}»: дорогая программа без цены")
        if VALUE_RE.search(" ".join(it.get(k) or "" for k in ("title_ru", "where_ru", "price_ru", "blurb_ru"))):
            f.violations.append(f"«{c['title']}»: оценка «выгодно»")
    for org, n in per.items():
        if n > PER_ORG:
            f.violations.append(f"{org}: {n} строк (не больше {PER_ORG})")
    f.info.append(f"строк {len(items)}, организаторов {len(per)}")
    return f
