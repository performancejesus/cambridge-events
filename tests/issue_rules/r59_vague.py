"""59. Расплывчатые пункты (исправляющая; итоги 7f: «Waterstones Book Events», «Studio Sunday», «Print Shop Open», «Rowan
Community Evening Classes», «Hot Numbers Discovery Sessions», «Guided Tour of the Pye Exhibitions»): в выпуске — только
если описание раскрывает по странице события, что конкретно будет (не меньше 6 содержательных слов сверх названия);
иначе не берём (selection.vague_reason до модели)."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 59, "Расплывчатые пункты — раскрыты по странице или не взяты", FIX


def check(ctx) -> Finding:
    from pipeline.selection import vague
    f = Finding()
    for rub, it in ctx.model_items():
        for i in it["ids"][:1]:
            c = ctx.pools.candidates.get(i) or {}
            if c.get("kind") != "event" or not vague(c):
                continue
            tw = set(re.findall(r"\w+", (it.get("title_en") or "").lower()))
            words = [x for x in re.findall(r"\w+", (it.get("blurb_en") or "").lower()) if len(x) > 3 and x not in tw]
            if len(words) < 6:
                f.violations.append(f"«{it.get('title_ru')}»: расплывчато — описание не говорит, что будет")
    return f
