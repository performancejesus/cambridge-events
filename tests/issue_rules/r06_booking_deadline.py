"""6. Дедлайн записи прошёл (блокирующая): такая программа не в письме (на полной странице — «запись закрыта»)."""

from __future__ import annotations

from pipeline import issue
from . import BLOCK, Finding

RULE, TITLE, LEVEL = 6, "Дедлайн записи прошёл — программа не в письме", BLOCK


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        for c in e["cands"]:
            if c.get("kind") == "programme" and issue.booking_closed(c, ctx.w):
                f.violations.append(f"«{e['title']}»: запись закрыта ({c.get('booking_deadline')})")
    return f
