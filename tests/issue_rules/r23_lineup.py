"""23. Состав участников (исправляющая; build_issue.check_v4_rules): все названные участники из склеенных записей
(до 4–5 имён) названы в тексте пункта — латиницей или кириллицей."""

from __future__ import annotations

from . import FIX, Finding
from .common import name_in_text

RULE, TITLE, LEVEL = 23, "Состав участников — полностью", FIX


def check(ctx) -> Finding:
    f = Finding()
    for rub, it in ctx.model_items():
        names = []
        for i in it["ids"]:
            c = ctx.pools.candidates.get(i) or {}
            if {"S018", "S123"} & set(c.get("sources") or []):
                continue
            names += [n for n in c.get("lineup", []) if n not in names]
        for lang in ("en", "ru"):
            text = f"{it.get(f'title_{lang}') or ''} {it.get(f'blurb_{lang}') or ''}"
            miss = [n for n in names[:5] if not name_in_text(n, text)]
            if miss:
                f.violations.append(f"«{it['title_ru']}» ({lang}): не названы {', '.join(miss)}")
    return f
