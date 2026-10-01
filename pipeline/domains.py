"""Этап 6b: домены из результатов поиска — robots.txt (наш бот, ИИ-агенты Anthropic) и связь с реестром источников.

domain_robots: один запрос robots.txt на хост; bot_allowed — открыт ли корень сайта для CambridgeEventsBot,
ai_blocked — каким агентам Anthropic закрыт (пусто — запрета нет). Используется, чтобы (1) не передавать в модель
сниппеты сайтов с ИИ-запретом, (2) решить, можно ли добавить сайт в реестр как обычный источник.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import openpyxl

from collectors.http import USER_AGENT
from .ai_policy import AI_AGENTS
from .db import ROOT

REGISTRY = ROOT / "data" / "cambridge_event_sources_v0.6.xlsx"
SCHEMA = """CREATE TABLE IF NOT EXISTS domain_robots (
    host        TEXT PRIMARY KEY,
    status      INTEGER,          -- код ответа robots.txt (-1 — сеть/TLS)
    bot_allowed INTEGER,          -- корень сайта открыт для CambridgeEventsBot
    ai_blocked  TEXT,             -- агенты Anthropic, которым закрыт корень (через запятую)
    checked_at  TEXT
)"""


def host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _check(h: str, http) -> tuple | None:
    """Этап 7e: robots.txt — через общий слой бережных запросов (кэш на сутки, пауза домена, журнал), а не напрямую.
    Домен на паузе — None (проверим в другой день)."""
    from collectors.http import Deferred
    status = -1
    rp = None
    for base in (f"https://{h}", f"https://www.{h}"):
        try:
            rp = http._robots_for(base + "/")
            status = http.robots_status.get(base, -1)
        except Deferred:
            return None
        if status != -1:
            break
    root = f"https://{h}/"
    blocked = [a for a in AI_AGENTS if not rp.can_fetch(a, root)] if status == 200 and rp else []
    return h, status, int(bool(rp) and rp.can_fetch(USER_AGENT, root)), ",".join(blocked)


def check(con: sqlite3.Connection, hosts: set[str], workers: int = 1) -> int:
    """robots.txt новых доменов — последовательно, через общий слой (раньше — 16 потоков напрямую)."""
    from collectors.http import PoliteClient
    con.execute(SCHEMA)
    done = {r[0] for r in con.execute("SELECT host FROM domain_robots")}
    todo = sorted(hosts - done)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    http = PoliteClient(purpose="domains_robots")
    n = 0
    try:
        for h in todo:
            res = _check(h, http)
            if res:
                con.execute("INSERT OR REPLACE INTO domain_robots VALUES (?,?,?,?,?)", (*res, now))
                n += 1
    finally:
        http.close()
    con.commit()
    return n


def robots(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    con.execute(SCHEMA)
    return {r["host"]: r for r in con.execute("SELECT * FROM domain_robots")}


def registry_hosts(con: sqlite3.Connection) -> dict[str, list[str]]:
    """Хост → ID источников реестра (URL и endpoint из реестра + ссылки сырых записей источника)."""
    out: dict[str, set[str]] = {}
    wb = openpyxl.load_workbook(REGISTRY, read_only=True)
    rows = list(wb["Источники"].iter_rows(values_only=True))
    head = rows[0]
    iu, ie, iid = head.index("URL"), head.index("Endpoint для сбора"), head.index("ID")
    for r in rows[1:]:
        for u in (r[iu], r[ie]):
            if u and str(u).startswith("http"):
                out.setdefault(host(str(u)), set()).add(r[iid])
    for sid, url in con.execute("SELECT DISTINCT source_id, url FROM raw_items WHERE url LIKE 'http%'"):
        if host(url):
            out.setdefault(host(url), set()).add(sid)
    return {h: sorted(v) for h, v in out.items()}


def registry_status(con: sqlite3.Connection) -> dict[str, str]:
    """ID источника → решение из реестра (подключён / не нужен / закрыт …), колонка «Способ сбора» + заметки."""
    wb = openpyxl.load_workbook(REGISTRY, read_only=True)
    rows = list(wb["Источники"].iter_rows(values_only=True))
    head = rows[0]
    return {r[head.index("ID")]: f"{r[head.index('Источник')]}" for r in rows[1:] if r[head.index("ID")]}
