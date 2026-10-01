"""47. «Новое в городе» вне Кембриджа — городок в заголовке строки (исправляющая; этап 7e, правки по v11 и правило v5:
David Lloyd St Neots — город был только в строке с адресом). Заголовок: «Название — Сент-Нитс, до часа»."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 47, "«Новое в городе» вне Кембриджа — городок в заголовке строки", FIX


def check(ctx) -> Finding:
    from pipeline.issue import TOWN_RU, news_town
    f = Finding()
    for e in ctx.entries("ru"):
        c = e["cands"][0] if e["cands"] else {}
        if c.get("kind") != "venue_news" or re.search(r"\bCambridge\b", c.get("address") or ""):
            continue
        town = news_town(c)
        if not town:
            f.warnings.append(f"«{e['title']}»: город не определён по адресу")
            continue
        if f" — {TOWN_RU.get(town, town)}" not in e["title"]:
            f.violations.append(f"«{e['title']}»: нет городка ({TOWN_RU.get(town, town)}) в заголовке")
    return f
