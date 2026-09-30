"""27. Подборки («Things to do…», «What's on», «best … events», площадка «Various») — не событие (исправляющая;
issue._exclusion по events.roundup и pipeline/roundups.py)."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 27, "Подборки — не событие", FIX
ROUNDUP = re.compile(r"\b(things to do|what'?s on|best .{0,30}events|events? this (?:week|weekend|month)|"
                     r"half[- ]term (?:ideas|guide)|guide to)\b", re.I)


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        for c in e["cands"]:
            if c.get("kind") not in ("event", "announcement", "tickets", "holiday_event"):
                continue
            if c.get("roundup") or ROUNDUP.search(c.get("title") or "") or \
                    (re.match(r"^\s*(various|разные)\b", c.get("venue") or "", re.I) and not c.get("multi_venue")):
                f.violations.append(f"«{e['title']}»: похоже на подборку ({c.get('title')})")
    return f
