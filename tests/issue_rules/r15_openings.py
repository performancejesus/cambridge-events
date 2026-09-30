"""15. Открытия (исправляющая; делает issue.when): дата открытия = дата статьи → «открылось в <месяц>» / «недавно
открылось», без точного дня."""

from __future__ import annotations

import re

from pipeline import issue
from . import FIX, Finding

RULE, TITLE, LEVEL = 15, "Открытия: дата статьи — не дата открытия", FIX
DAY = re.compile(r"\b\d{1,2} (?:" + "|".join(issue.MONTHS_RU) + r")\b")


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        c = e["cands"][0] if e["cands"] else {}
        if c.get("kind") == "venue_news" and c.get("date_basis") == "publication_date" and DAY.search(e["meta"]):
            f.violations.append(f"«{e['title']}»: точная дата у открытия, известного только по дате статьи ({e['meta']})")
    return f
