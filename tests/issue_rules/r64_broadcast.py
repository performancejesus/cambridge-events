"""64. Трансляции в кино: труппа — по префиксу серии (исправляющая; правка 5 после v14). «RBO 26-27: Macbeth (MET Opera)»:
RBO — Royal Ballet and Opera (Лондон), не Metropolitan Opera; площадку трансляции не выводить из слова «Opera» в названии.
Исправляет issue_fixes.fix_broadcast (pipeline/broadcast.py)."""

from __future__ import annotations

from . import FIX, Finding

RULE, TITLE, LEVEL = 64, "Трансляции: труппа по префиксу серии (RBO ≠ MET)", FIX


def check(ctx) -> Finding:
    from pipeline import broadcast
    from pipeline.issue_fixes import _cands
    f = Finding()
    for rub, it in ctx.model_items():
        title = next((c.get("title") for c in _cands(ctx.pools, it)), None) or it.get("title_en")
        if not broadcast.series_of(title):
            continue
        for k in ("title_en", "title_ru", "blurb_en", "blurb_ru", "why_en", "why_ru"):
            wrong = broadcast.wrong_mentions(title, it.get(k)) or (
                [it[k]] if k.startswith("title") and broadcast.clean_title(it.get(k)) != it.get(k) else [])
            if wrong:
                f.violations.append(f"«{it.get('title_ru')}»: {k} — другая труппа «{wrong[0][:60]}»")
    return f
