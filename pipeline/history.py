"""Правки по v8: повторы между выпусками (Simply Red, Olly Murs, Beer Festival, «Новое в городе» — те же, что в v6–v7).

История выпусков — таблица issue_items: что вошло в каждый собранный выпуск (дата отправки, версия, рубрика, id
кандидата, события). При сборке следующего выпуска (дата отправки позже) уже показанное не повторяется:
  - событие (E…), показанное раньше как событие, — не повторяем;
  - анонс или старт продаж (A…/T…), показанный раньше, — не повторяем как анонс; когда событие наступит, оно может
    выйти как событие окна (E…) — это новый повод;
  - отмена (C…) — всегда новый повод, если отмены в прошлых выпусках не было;
  - открытие (V…) — не повторяем.
Выпуски с той же датой отправки (v8 и v9 — версии одного выпуска) друг друга не исключают.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

SCHEMA = """CREATE TABLE IF NOT EXISTS issue_items (
    issue_date TEXT, version TEXT, rubric TEXT, cand_id TEXT, kind TEXT, event_id INTEGER, title TEXT, recorded_at TEXT,
    PRIMARY KEY (issue_date, version, cand_id, event_id)
)"""
LOOKBACK_DAYS = 28


def init(con: sqlite3.Connection) -> None:
    con.execute(SCHEMA)


def record(con: sqlite3.Connection, issue_date: str, version: str, result: dict, candidates: dict) -> int:
    """Записать пункты собранного выпуска (заменяет прежнюю запись той же даты и версии)."""
    init(con)
    con.execute("DELETE FROM issue_items WHERE issue_date=? AND version=?", (issue_date, version))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for sec in result["sections"]:
        for it in sec["items"]:
            for cid in it["ids"]:
                c = candidates.get(cid) or {}
                evs = c.get("event_ids") or [None]
                key = c.get("news_id") if cid.startswith("V") else None
                for e in evs if key is None else [key]:
                    con.execute("INSERT OR REPLACE INTO issue_items VALUES (?,?,?,?,?,?,?,?)",
                                (issue_date, version, sec["rubric"], cid, cid[:1], e, it.get("title_en"), now))
                    n += 1
    con.commit()
    return n


def shown_before(con: sqlite3.Connection, issue: date) -> dict[str, dict[int, str]]:
    """Вид кандидата (E/A/T/C/V) → {событие или id открытия: дата выпуска} за LOOKBACK_DAYS до даты отправки."""
    init(con)
    out: dict[str, dict[int, str]] = {}
    for r in con.execute("""SELECT kind, event_id, max(issue_date) FROM issue_items WHERE issue_date < ? AND issue_date >= ?
                            AND event_id IS NOT NULL GROUP BY kind, event_id""",
                         (issue.isoformat(), (issue - timedelta(days=LOOKBACK_DAYS)).isoformat())):
        out.setdefault(r[0], {})[r[1]] = r[2]
    return out
