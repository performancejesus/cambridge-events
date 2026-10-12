"""67. Оформление строк (исправляющая; правка 9 после v14): зона один раз («(до 30 мин) · до 30 мин»); год в диапазоне
дат один раз («15 января 2027 – 17 января 2027» → «15–17 января 2027»); служебное в тексте — название источника
(«(Cambridge Independent)» в строке Folk Festival); «хоккей» в детских секциях — «хоккей на траве». Исправляют
issue.polish_layout и glossary.hockey_ru."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 67, "Оформление: зона и год один раз, без названий источников, «хоккей на траве»", FIX


def check(ctx) -> Finding:
    from pipeline.issue import SOURCE_PAREN_RE, YEAR_TWICE_RE, ZONE_TWICE_RE
    f = Finding()
    for lang in ("ru", "en"):
        for e in ctx.entries(lang):
            text = f"{e['title']} · {e['meta']} · {e['blurb']}"
            if ZONE_TWICE_RE.search(e["meta"]):
                f.violations.append(f"«{e['title']}» ({lang}): зона дважды — {e['meta'][:70]}")
            if any(rx.search(text) for rx, _ in YEAR_TWICE_RE):
                f.violations.append(f"«{e['title']}» ({lang}): год в диапазоне дат дважды")
            if SOURCE_PAREN_RE.search(text):
                f.violations.append(f"«{e['title']}» ({lang}): служебное — название источника в тексте")
            if lang == "ru" and e["rubric"] in ("kids", "holidays") and \
                    re.search(r"\b[Хх]оккей\w*\b(?!\s+на\s+(?:траве|льду))", e["title"]):
                f.violations.append(f"«{e['title']}»: «хоккей» — в Британии это хоккей на траве")
    return f
