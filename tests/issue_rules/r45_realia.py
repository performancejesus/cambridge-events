"""45. Культурные реалии (исправляющая; этап 7e, правки по v11): Father Christmas ≠ «Дед Мороз» (Father Christmas или
«Санта»); pantomime — «пантомима (рождественское семейное шоу)», Bonfire Night — с пояснением при первом упоминании.
Глоссарий — pipeline/glossary.py (тот же для выпуска и «Каникул»); исправляет issue_fixes.fix_realia."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 45, "Культурные реалии: Father Christmas, panto, Bonfire Night — без подмены", FIX


def check(ctx) -> Finding:
    from pipeline.glossary import REALIA_EXPLAIN
    f = Finding()
    for where, text in ctx.texts("ru"):
        if re.search(r"\bДед(?:ушк\w*)?\w* Мороз\w*", text):
            f.violations.append(f"«{where}»: «Дед Мороз» вместо Father Christmas / «Санта»")
    for rub, it in ctx.model_items():
        src = " ".join(str(c.get(k) or "") for i in it["ids"] if i in ctx.pools.candidates
                       for c in [ctx.pools.candidates[i]] for k in ("title", "summary"))
        b = it.get("blurb_ru") or ""
        for src_rx, word_rx, expl in REALIA_EXPLAIN:
            if re.search(src_rx, src, re.I) and re.search(word_rx, b, re.I) and expl not in b:
                f.violations.append(f"«{it['title_ru']}»: нет пояснения «{expl}»")
    return f
