"""Подборки — не события (правки после просмотра v5).

«Things to do in Cambridge for Halloween» (1 октября – 1 ноября, площадка «Various») — статья со списком. Признаки
подборки: «Things to do», «What's on», «best … events», «guide to», «top N» в названии; площадка «Various»/«разные» и
период больше 2 недель при общем названии («… events», «… activities»). Такие записи получают events.roundup = 1 и в
выпуск не идут; scripts/split_roundups.py разбирает их на отдельные события (каждое проверяется на странице
первоисточника).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date

TITLE_RE = re.compile(r"\bthings to do\b|\bwhat'?s on\b|\bbest\b.{0,40}\b(events?|things|days? out)\b|\bguide to\b|"
                      r"\btop \d+\b|\bdays? out\b.{0,20}\b(in|around|near)\b", re.I)
GENERIC_RE = re.compile(r"\b(events|activities|things)\b", re.I)
VARIOUS_RE = re.compile(r"^\s*(various|multiple|several|разные)\b", re.I)


def is_roundup(title: str, venue: str | None, start: str, end: str | None) -> bool:
    if TITLE_RE.search(title):
        return True
    span = (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days if end else 0
    return bool(VARIOUS_RE.match(venue or "")) and span > 14 and bool(GENERIC_RE.search(title))


def tag(con: sqlite3.Connection) -> dict:
    n = 0
    for e in con.execute("SELECT event_id, title, venue_name, date_start, date_end, roundup FROM events").fetchall():
        r = int(is_roundup(e["title"], e["venue_name"], e["date_start"], e["date_end"]))
        if r != (e["roundup"] or 0):
            con.execute("UPDATE events SET roundup=? WHERE event_id=?", (r, e["event_id"]))
        n += r
    return {"roundup_events": n}
