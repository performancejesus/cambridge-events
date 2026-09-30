"""3. Прошедшие события (блокирующая): ни одного пункта с датой окончания раньше даты отправки."""

from __future__ import annotations

from pipeline import issue
from . import BLOCK, Finding

RULE, TITLE, LEVEL = 3, "Прошедшие события", BLOCK
SKIP_KINDS = {"venue_news", "film_release", "programme"}


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        for c in e["cands"]:
            if c.get("kind") in SKIP_KINDS or not c.get("dates"):
                continue
            end = max(issue.d(x[1] or x[0]) for x in c["dates"] if x[0])
            if end < ctx.w.issue:
                f.violations.append(f"«{e['title']}» ({e['rubric']}): закончилось {end:%d.%m} — раньше даты отправки")
                break
    return f
