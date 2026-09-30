"""Этап 7c (правки по v9): таблица verified_facts — проверенные факты для тем недели и ежегодных событий.

Факт: о ком или о чём (subject + синонимы, в том числе кириллицей и в падежах), вид (birth_date, death_date, founded,
first, last, only, league, other), значение, формулировка, источник, кто проверил и когда. Заносит редактор (файл
data/verified_facts.json → таблица при каждой сборке) или сборщик: утверждение «первый / последний / единственный»,
которое сверка нашла в тексте источника пункта, записывается с источником = страница пункта и checked_by = «сборщик».

Проверка выпуска (tests/issue_rules/r01_verified_facts.py) сверяет с таблицей утверждения о днях рождения, юбилеях
(«исполнилось бы», «в этом месяце / году», «N-летие»), «впервые / последний / единственный» и годах основания.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from .db import ROOT

SEED = ROOT / "data" / "verified_facts.json"
SCHEMA = """CREATE TABLE IF NOT EXISTS verified_facts (
    fact_id    INTEGER PRIMARY KEY,
    subject    TEXT NOT NULL,
    aliases    TEXT,              -- JSON: синонимы и падежные формы («Барретт», «Барретту», «Syd»)
    kind       TEXT NOT NULL,     -- birth_date | death_date | founded | first | last | only | league | other
    value      TEXT NOT NULL,     -- 1946-01-06 | 1972 | League Two (2026/27) | …
    statement  TEXT,              -- формулировка факта
    source     TEXT NOT NULL,     -- ссылка на источник
    checked_by TEXT NOT NULL,     -- редактор | сборщик: текст источника | …
    checked_at TEXT NOT NULL,
    UNIQUE (subject, kind, value)
)"""


def init(con: sqlite3.Connection) -> None:
    con.execute(SCHEMA)
    if SEED.exists():
        for f in json.loads(SEED.read_text())["facts"]:
            con.execute("""INSERT INTO verified_facts(subject, aliases, kind, value, statement, source, checked_by, checked_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(subject, kind, value) DO UPDATE SET aliases=excluded.aliases,
                statement=excluded.statement, source=excluded.source, checked_by=excluded.checked_by,
                checked_at=excluded.checked_at""",
                        (f["subject"], json.dumps(f.get("aliases", []), ensure_ascii=False), f["kind"], f["value"],
                         f.get("statement"), f["source"], f["checked_by"], f["checked_at"]))
    con.commit()


def all_facts(con: sqlite3.Connection) -> list[dict]:
    init(con)
    out = []
    for r in con.execute("SELECT * FROM verified_facts"):
        x = dict(r) if isinstance(r, sqlite3.Row) else dict(zip([c[0] for c in con.execute("SELECT * FROM verified_facts LIMIT 0").description], r))
        x["aliases"] = json.loads(x["aliases"] or "[]")
        out.append(x)
    return out


def mentions(fact: dict, text: str) -> bool:
    """Субъект факта назван в тексте (имя или любой синоним как отдельное слово, без учёта регистра)."""
    names = [fact["subject"]] + fact["aliases"]
    return any(re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text, re.I) for n in names if n)


def add(con: sqlite3.Connection, subject: str, kind: str, value: str, statement: str, source: str,
        checked_by: str, aliases: list[str] | None = None) -> None:
    init(con)
    con.execute("""INSERT OR IGNORE INTO verified_facts(subject, aliases, kind, value, statement, source, checked_by,
        checked_at) VALUES (?,?,?,?,?,?,?,?)""", (subject, json.dumps(aliases or [], ensure_ascii=False), kind, value,
                                                   statement, source, checked_by,
                                                   datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
