"""16. Время детских событий с 22:00 до 6:00 (исправляющая; делает issue.kid_time): сверка со страницей, иначе время
не показывается."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 16, "Детские события ночью — сверка времени", FIX
NIGHT = re.compile(r",\s*(2[2-3]|0[0-5]):\d\d\b")


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        if any(c.get("kids_tag") for c in e["cands"]) and NIGHT.search(e["meta"]):
            f.violations.append(f"«{e['title']}»: {e['meta'].split(' · ')[0]}")
    return f
