"""60. Пояснять незнакомое и переводить смысл (исправляющая; итоги 7f «Карточка события»): организации (MIND), практики и
виды спорта (Reiki, Wing Chun, Escrima, walking football, cricket nets), форматы (parkrun) — с пояснением в паре слов;
ошибки перевода (cohousing, visual impairment, «тренировки у сетки», hand-rolled bagels, Commercial ≠ «коммерческие
мероприятия») — исправлены. Исправляют issue_fixes.fix_explain и fix_translation."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 60, "Незнакомое — с пояснением, перевод — по смыслу", FIX


def check(ctx) -> Finding:
    from pipeline.issue_fixes import TRANSLATION_FIXES, _cands, unexplained
    f = Finding()
    for rub, it in ctx.model_items():
        if it.get("line"):
            continue
        src = " ".join(str(c.get(k) or "") for c in _cands(ctx.pools, it) for k in ("title", "summary"))
        for term, expl in unexplained(it, src):
            f.violations.append(f"«{it.get('title_ru')}»: «{term}» без пояснения ({expl})")
        b = it.get("blurb_ru") or ""
        for rx, good, need in TRANSLATION_FIXES:
            m = rx.search(b)
            if m and good not in b and (not need or need.search(f"{it.get('title_en')} {it.get('blurb_en')}")):
                f.violations.append(f"«{it.get('title_ru')}»: перевод — «{m.group(0)}» → «{good}»")
    return f
