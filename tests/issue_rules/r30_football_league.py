"""30. Лига клуба — только из данных сайта клуба или verified_facts (исправляющая; правки по v9: «матч Лиги Two» у
Cambridge United — лига сезона 2026/27 из знаний модели). Упоминание лиги без подтверждения убирается из описания."""

from __future__ import annotations

import re

from pipeline import verified_facts
from . import FIX, Finding

RULE, TITLE, LEVEL = 30, "Лига футбольного клуба — только подтверждённая", FIX
LEAGUE_RE = re.compile(r"\b(?:Sky Bet )?(?:League (?:One|Two|1|2)|Championship|Premier League|National League(?: North| South)?)\b|"
                       r"\bЛиг[аиеуой]+\s+(?:One|Two|1|2|Один|Два)\b|\bЧемпионшип\w*|\bПремьер-лиг\w*|\bНациональн\w+ лиг\w*|"
                       r"\bпервой лиги\b|\bвторой лиги\b", re.I)
FOOTBALL = {"S018", "S123", "S019", "S154"}


def confirmed(ctx, cands, text: str) -> bool:
    data = " ".join(" ".join(str(c.get(k) or "") for k in ("title", "summary", "categories")) for c in cands)
    # page_facts не считаем: на странице клуба «League Two | League One» — меню фильтра турниров, а не турнир матча
    facts = [x for x in verified_facts.all_facts(ctx.con) if x["kind"] == "league"]
    for m in LEAGUE_RE.finditer(text):
        lg = m.group(0)
        en = re.sub(r"Лиг\w+\s+", "League ", lg)
        if en.lower() in data.lower() or any(verified_facts.mentions(x, " ".join(c.get("title") or "" for c in cands))
                                             and x["value"].lower().startswith(en.lower()) for x in facts):
            continue
        return False
    return True


def check(ctx) -> Finding:
    f = Finding()
    for rub, it in ctx.model_items():
        cands = [ctx.pools.candidates.get(i) or {} for i in it["ids"]]
        if not any(FOOTBALL & set(c.get("sources") or []) for c in cands):
            continue
        for lang in ("ru", "en"):
            t = f"{it.get(f'title_{lang}') or ''} {it.get(f'blurb_{lang}') or ''}"
            if LEAGUE_RE.search(t) and not confirmed(ctx, cands, t):
                f.violations.append(f"«{it['title_ru']}» ({lang}): лига «{LEAGUE_RE.search(t).group(0)}» не подтверждена")
    return f
