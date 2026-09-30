"""19. Заголовки без приписок статуса и даты (исправляющая): «Simply Red … — билеты уже в продаже», «Fireworks Night —
5 ноября» — статус и дата стоят в строке с датой, в заголовке их не дублируем (build_issue.strip_title_tails)."""

from __future__ import annotations

import re

from pipeline import issue
from . import FIX, Finding

RULE, TITLE, LEVEL = 19, "Заголовки без приписок статуса и даты", FIX
MON = "|".join(issue.MONTHS_RU + ["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                  "october", "november", "december"] + [m.lower() for m in issue.MONTHS_EN])
TAIL_RE = re.compile(
    r"\s*(?:[—–-]|:)\s*(?:билеты\b.*|tickets?\b.*|(?:уже )?в продаже\b.*|(?:now )?on sale\b.*|продажа\b.*|"
    r"скоро\b.*|coming soon|now open|открыл\w*|отмен\w*|cancelled|перенес\w*|postponed|распродан\w*|sold out|"
    r"мало билетов|few tickets left|анонс\w*|announced|"
    rf"(?:пн|вт|ср|чт|пт|сб|вс|mon|tue|wed|thu|fri|sat|sun)?,?\s*\d{{1,2}}(?:\s*[–-]\s*\d{{1,2}})?\s+(?:{MON})(?:\s+\d{{4}})?|"
    rf"(?:{MON})\s+\d{{1,2}}(?:,?\s+\d{{4}})?)$", re.I)
PAREN_RE = re.compile(r"\s*\((?:билеты в продаже|уже в продаже|on sale|sold out|распродано|отменено|cancelled|"
                      r"скоро открытие|coming soon)\)\s*$", re.I)


def strip_tail(title: str) -> str:
    t = PAREN_RE.sub("", title)
    m = TAIL_RE.search(t)
    if m and m.start() > 3:
        t = t[:m.start()]
    return t.strip()


def check(ctx) -> Finding:
    f = Finding()
    for rub, it in ctx.model_items():
        if it.get("also"):
            continue
        for lang in ("ru", "en"):
            t = it.get(f"title_{lang}") or ""
            if strip_tail(t) != t.strip():
                f.violations.append(f"«{t}»")
    return f
