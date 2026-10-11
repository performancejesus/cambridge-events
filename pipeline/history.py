"""Правки по v8: повторы между выпусками (Simply Red, Olly Murs, Beer Festival, «Новое в городе» — те же, что в v6–v7).

История выпусков — таблица issue_items: что вошло в каждый собранный выпуск (дата отправки, версия, рубрика, id
кандидата, события). При сборке следующего выпуска (дата отправки позже) уже показанное не повторяется:
  - событие (E…), показанное раньше как событие, — не повторяем;
  - анонс или старт продаж (A…/T…), показанный раньше, — не повторяем как анонс; когда событие наступит, оно может
    выйти как событие окна (E…) — это новый повод;
  - отмена (C…) — всегда новый повод, если отмены в прошлых выпусках не было;
  - открытие (V…) — не повторяем.
Выпуски с той же датой отправки (v8 и v9 — версии одного выпуска) друг друга не исключают.

Прогон 7e+ (05.10): у записи есть статус `status` — `draft` (черновик, не отправлялся) или `sent` (отправлен).
Черновики не считаются ни для правила «не повторять 4 недели», ни для «Новых анонсов» и строк секций: v5–v12 — черновики
(не отправлялись). Новая сборка пишется как `draft`; после отправки — `mark_sent(дата, версия)`
(`python scripts/mark_sent.py --issue 2026-10-08 --version v13`).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

SCHEMA = """CREATE TABLE IF NOT EXISTS issue_items (
    issue_date TEXT, version TEXT, rubric TEXT, cand_id TEXT, kind TEXT, event_id INTEGER, title TEXT, recorded_at TEXT,
    status TEXT DEFAULT 'draft',
    PRIMARY KEY (issue_date, version, cand_id, event_id)
)"""
LOOKBACK_DAYS = 28
SENT = "status = 'sent'"   # условие для запросов: только отправленные выпуски


def init(con: sqlite3.Connection) -> None:
    con.execute(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(issue_items)")}
    if "status" not in cols:   # прогон 7e+ (снимок базы — до)
        con.execute("ALTER TABLE issue_items ADD COLUMN status TEXT DEFAULT 'draft'")
        con.execute("UPDATE issue_items SET status='draft'")
        con.commit()
    if "detail" not in cols:   # этап 7g: стадия «Нового в городе» и название места (повтор: «скоро» → «открылось»)
        con.execute("ALTER TABLE issue_items ADD COLUMN detail TEXT")
        con.commit()
    con.execute("""CREATE TABLE IF NOT EXISTS issue_themes (issue_date TEXT, version TEXT, title_en TEXT, title_ru TEXT,
        event_ids TEXT, status TEXT DEFAULT 'draft', recorded_at TEXT, PRIMARY KEY (issue_date, version))""")


def mark_sent(con: sqlite3.Connection, issue_date: str, version: str) -> int:
    """Выпуск отправлен: его пункты начинают учитываться в правиле повторов и в отсчёте «Новых анонсов»."""
    init(con)
    n = con.execute("UPDATE issue_items SET status='sent' WHERE issue_date=? AND version=?", (issue_date, version)).rowcount
    con.execute("UPDATE issue_themes SET status='sent' WHERE issue_date=? AND version=?", (issue_date, version))
    con.commit()
    return n


THEME_WEEKS = 8   # правка 11 после v13: тему не повторять 8 недель (только отправленные выпуски)


def record_theme(con: sqlite3.Connection, issue_date: str, version: str, title_en: str, title_ru: str,
                 event_ids: list[int], status: str = "draft") -> None:
    init(con)
    con.execute("INSERT OR REPLACE INTO issue_themes VALUES (?,?,?,?,?,?,?)",
                (issue_date, version, title_en, title_ru, json.dumps(sorted(set(event_ids))), status,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()


def recent_themes(con: sqlite3.Connection, issue: date, weeks: int = THEME_WEEKS) -> list[dict]:
    """Темы отправленных выпусков за `weeks` недель до даты отправки (черновики не считаются)."""
    init(con)
    since = (issue - timedelta(weeks=weeks)).isoformat()
    return [{"issue_date": r[0], "title_en": r[1], "title_ru": r[2], "event_ids": json.loads(r[3] or "[]")}
            for r in con.execute("""SELECT issue_date, title_en, title_ru, event_ids FROM issue_themes WHERE status='sent'
                                    AND issue_date < ? AND issue_date >= ?""", (issue.isoformat(), since))]


def shown_places(con: sqlite3.Connection, issue: date) -> dict[str, set[str]]:
    """«Новое в городе» в отправленных выпусках: название места (norm_place) → стадии, в которых оно уже выходило."""
    init(con)
    out: dict[str, set[str]] = {}
    for (det,) in con.execute(f"SELECT detail FROM issue_items WHERE kind='V' AND {SENT} AND issue_date < ? "
                              "AND detail IS NOT NULL", (issue.isoformat(),)):
        stage, _, name = det.partition("|")
        out.setdefault(name, set()).add(stage)
    return out


def last_sent(con: sqlite3.Connection, before: date) -> str | None:
    """Дата последнего отправленного выпуска до даты отправки (None — отправленных не было)."""
    init(con)
    return con.execute(f"SELECT max(issue_date) FROM issue_items WHERE {SENT} AND issue_date < ?",
                       (before.isoformat(),)).fetchone()[0]


def record(con: sqlite3.Connection, issue_date: str, version: str, result: dict, candidates: dict,
           status: str = "draft") -> int:
    """Записать пункты собранного выпуска (заменяет прежнюю запись той же даты и версии); по умолчанию — черновик."""
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
                detail = None
                if cid.startswith("V"):
                    from .selection import norm_place
                    detail = f"{c.get('stage') or ''}|{norm_place(c.get('title'))}"
                for e in evs if key is None else [key]:
                    con.execute("""INSERT OR REPLACE INTO issue_items(issue_date, version, rubric, cand_id, kind, event_id,
                        title, recorded_at, status, detail) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                (issue_date, version, sec["rubric"], cid, cid[:1], e, it.get("title_en"), now, status, detail))
                    n += 1
    con.commit()
    return n


def shown_before(con: sqlite3.Connection, issue: date) -> dict[str, dict[int, str]]:
    """Вид кандидата (E/A/T/C/V) → {событие или id открытия: дата выпуска} за LOOKBACK_DAYS до даты отправки.
    Только отправленные выпуски (черновики — нет, прогон 7e+)."""
    init(con)
    out: dict[str, dict[int, str]] = {}
    for r in con.execute(f"""SELECT kind, event_id, max(issue_date) FROM issue_items WHERE issue_date < ? AND issue_date >= ?
                            AND event_id IS NOT NULL AND {SENT} GROUP BY kind, event_id""",
                         (issue.isoformat(), (issue - timedelta(days=LOOKBACK_DAYS)).isoformat())):
        out.setdefault(r[0], {})[r[1]] = r[2]
    return out
