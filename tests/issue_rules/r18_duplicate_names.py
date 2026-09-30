"""18. Дубли имён (исправляющая): «Также в программе: X», когда X уже назван в тексте (в том числе кириллицей:
«Джозефин Кроули Куинн» = Josephine Crawley Quinn), — удалить. build_issue.check_v4_rules дописывает только тех, кого
нет в тексте ни латиницей, ни кириллицей."""

from __future__ import annotations

import re

from . import FIX, Finding
from .common import name_in_text

RULE, TITLE, LEVEL = 18, "Дубли имён («Также в программе: X», когда X уже в тексте)", FIX
TAIL = re.compile(r"\s*(?:Также в программе|Also on the bill):\s*([^.]+)\.?\s*$")


def check(ctx) -> Finding:
    f = Finding()
    for rub, it in ctx.model_items():
        for fld, tf in (("blurb_ru", "title_ru"), ("blurb_en", "title_en")):
            b = it.get(fld) or ""
            m = TAIL.search(b)
            if not m:
                continue
            rest = f"{it.get(tf) or ''} {b[:m.start()]}"
            for n in [x.strip() for x in m.group(1).split(",")]:
                if name_in_text(n, rest):
                    f.violations.append(f"«{it['title_ru']}»: {n} уже назван в тексте")
    return f
