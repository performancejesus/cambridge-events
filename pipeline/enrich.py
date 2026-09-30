"""Правки по черновику v5: если в данных нет фактов или цены — одна загрузка страницы события у первоисточника.

event_pages: event_id → текст страницы события (видимый, без скриптов; фрагмент вокруг названия) и цена со страницы.
Страницы газет и сайтов с ИИ-запретом не загружаем (флаг respect_ai_disallow здесь ни при чём: это не наш источник
фактов, а дополнительная загрузка). Страница уже загружена — повторно не запрашиваем (обновление раз в 7 дней).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from . import domains

SCHEMA = """CREATE TABLE IF NOT EXISTS event_pages (
    event_id INTEGER PRIMARY KEY, url TEXT, fetched_at TEXT, status TEXT, text TEXT, price TEXT
)"""
NEWS_HOSTS = {"cambridge-news.co.uk", "cambridgeindependent.co.uk", "peterboroughtoday.co.uk", "huntspost.co.uk",
              "cambstimes.co.uk", "wisbechstandard.co.uk", "elystandard.co.uk"}
PRICE_RE = re.compile(r"£\s?\d+(?:\.\d{2})?(?:\s*(?:-|–|to)\s*£?\s?\d+(?:\.\d{2})?)?")
FREE_RE = re.compile(r"\b(free (entry|admission|event|of charge)|admission (is )?free|entry (is )?free|"
                     # этап 7c (правки по v9: лекция St John's — «The lecture is free and open to all»)
                     r"(?:is|are) free and open to (?:all|everyone|the public)|free,? (?:public )?(?:lecture|talk|recital) )", re.I)


def init(con: sqlite3.Connection) -> None:
    con.execute(SCHEMA)


def facts(con: sqlite3.Connection, event_id: int) -> dict | None:
    init(con)
    r = con.execute("SELECT * FROM event_pages WHERE event_id=?", (event_id,)).fetchone()
    return dict(r) if r and r["status"] == "ok" else None


def fetch(con: sqlite3.Connection, http, event_id: int, url: str, title: str) -> dict | None:
    """Одна загрузка страницы события: фрагмент текста вокруг названия (≤ 900 знаков) и цена."""
    from collectors.http import Disallowed, FetchError
    from collectors.llmlist import visible_text
    init(con)
    row = con.execute("SELECT * FROM event_pages WHERE event_id=?", (event_id,)).fetchone()
    fresh = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    if row and row["fetched_at"] >= fresh:
        return dict(row) if row["status"] == "ok" else None
    h = domains.host(url or "")
    rb = domains.robots(con).get(h)
    status, text, price = "ok", None, None
    if not url or h in NEWS_HOSTS or (rb and rb["ai_blocked"]):
        status = "skipped"
    else:
        try:
            body, _ = visible_text(http.get(url).text)
            body = re.sub(r"(?:\| )+", "| ", body)
            words = [w for w in re.findall(r"[a-z]{4,}", title.lower())]
            low = body.lower()
            i = next((low.find(w) for w in sorted(words, key=len, reverse=True) if low.find(w) >= 0), 0)
            text = body[max(0, i - 100):i + 900]
            m = PRICE_RE.search(body[max(0, i - 300):i + 3000])
            price = m.group(0) if m else ("Free" if FREE_RE.search(body[:6000]) else None)
        except (Disallowed, FetchError, Exception) as e:  # noqa: BLE001
            status, text = "error", str(e)[:120]
    con.execute("INSERT OR REPLACE INTO event_pages VALUES (?,?,?,?,?,?)",
                (event_id, url, datetime.now(timezone.utc).isoformat(timespec="seconds"), status, text, price))
    con.commit()
    return facts(con, event_id)
