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


def _check(h: str) -> tuple:
    rp = RobotFileParser()
    status = -1
    for scheme in ("https", "http"):
        try:
            r = httpx.get(f"{scheme}://{h}/robots.txt", timeout=15, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT})
            status = r.status_code
            break
        except httpx.HTTPError:
            try:
                r = httpx.get(f"{scheme}://www.{h}/robots.txt", timeout=15, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT})
                status = r.status_code
                break
            except httpx.HTTPError:
                continue
    if status == 200:
        rp.parse(r.text.splitlines())
    elif status == 429 or status >= 500 or status == -1:
        rp.disallow_all = True      # недоступен или обрыв — полный запрет (RFC 9309, 2.3.1.4)
    else:
        rp.allow_all = True         # 4xx (в т.ч. 403) — «правил нет» (RFC 9309, 2.3.1.3)
    root = f"https://{h}/"
    blocked = [a for a in AI_AGENTS if not rp.can_fetch(a, root)] if status == 200 else []
    return h, status, int(rp.can_fetch(USER_AGENT, root)), ",".join(blocked)


def check(con: sqlite3.Connection, hosts: set[str], workers: int = 16) -> int:
    con.execute(SCHEMA)
    done = {r[0] for r in con.execute("SELECT host FROM domain_robots")}
    todo = sorted(hosts - done)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ThreadPoolExecutor(workers) as ex:
        for h, status, ok, blocked in ex.map(_check, todo):
            con.execute("INSERT OR REPLACE INTO domain_robots VALUES (?,?,?,?,?)", (h, status, ok, blocked, now))
    con.commit()
    return len(todo)


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
