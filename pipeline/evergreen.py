"""«Вечнозелёные» предложения (решение после этапа 6): постоянные продукты для туристов — квесты, «experiences»,
murder mystery, городские игры, экскурсии — источники (Visit Cambridge) отдают их как события с датой начала
в 2024–2025 годах. Это не события: events.evergreen = 1, в выпуск не идут. Выставки сюда не относятся.

Правило: название похоже на такой продукт И событие длительное (началось больше 30 дней назад или идёт больше
60 дней). Регулярные серии библиотек («recurring series») — отдельная пометка, не evergreen.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta

EVERGREEN_RE = re.compile(
    r"\b(experience|murder mystery|escape (room|game)|treasure hunt|scavenger hunt|city (game|exploration)|"
    r"exploration game|heist|quest|puzzle hunt|self[- ]guided|walking tour|ghost (tour|walk)|punt(ing)? tour|"
    r"bus tour|segway|sightseeing)\b", re.I)
EXHIBITION_RE = re.compile(r"\bexhibition|\bdisplay\b", re.I)


def tag(con: sqlite3.Connection) -> dict:
    today = date.today()
    old = (today - timedelta(days=30)).isoformat()
    n = 0
    for e in con.execute("SELECT event_id, title, date_start, date_end, evergreen FROM events").fetchall():
        start, end = e["date_start"], e["date_end"] or e["date_start"]
        long_ = start < old or (date.fromisoformat(end) - date.fromisoformat(start)).days > 60
        flag = int(bool(long_ and EVERGREEN_RE.search(e["title"]) and not EXHIBITION_RE.search(e["title"])))
        if flag != (e["evergreen"] or 0):
            con.execute("UPDATE events SET evergreen=? WHERE event_id=?", (flag, e["event_id"]))
        n += flag
    return {"evergreen_events": n}


def regular_series(con: sqlite3.Connection, event_id: int) -> bool:
    """Регулярная серия (Rhymetime, Storytime): коллектор пометил категорией «recurring series»."""
    return any("recurring series" in json.loads(c or "[]")
               for (c,) in con.execute("SELECT categories FROM raw_items WHERE event_id=?", (event_id,)))
