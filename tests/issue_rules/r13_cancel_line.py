"""13. Отмены — одной строкой без описания (исправляющая; делает issue.layout): что, когда, где, «отменено» /
«перенесено»."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 13, "Отмены — одной строкой", FIX


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        if e["rubric"] != "cancelled":
            continue
        if e["blurb"]:
            f.violations.append(f"«{e['title']}»: у отмены есть описание")
        if not re.search(r"отменено|перенесено", e["meta"]):
            f.violations.append(f"«{e['title']}»: в строке нет «отменено» / «перенесено»")
    return f
