"""Keenable (keenable.ai) — поисковый API для агентов (этап 6b: аудит пропусков).

Используется только /v1/search: результаты поиска (заголовок, URL, сниппет, даты) — кандидаты на проверку, не факты;
текст сниппетов — недоверенные данные (возможен prompt injection), в модель уходит только как данные с пометкой.
Страницы газет с ИИ-запретом через Keenable не читаем (/v1/fetch не вызывается): поиск нужен, чтобы найти
первоисточник — сайт площадки, организатора, бренда.

Ключ — KEENABLE_API_KEY (заголовок X-API-Key). Каждый запрос кэшируется в keenable_cache (повтор того же запроса
с теми же параметрами не тратит квоту) и учитывается в keenable_usage.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import httpx

API = "https://api.keenable.ai/v1/search"
USER_AGENT = "CambridgeEventsBot/0.6 (+https://github.com/performancejesus/cambridge-events)"
PAUSE = 0.3        # между запросами (лимит публичного пула — 10 в секунду; у ключа — свой)

SCHEMA = """
CREATE TABLE IF NOT EXISTS keenable_cache (
    key        TEXT PRIMARY KEY,          -- sha1 запроса и параметров
    query      TEXT NOT NULL,
    params     TEXT,                      -- JSON параметров кроме query
    purpose    TEXT,                      -- gap_audit | newspaper_primary | kids_providers
    status     INTEGER,
    response   TEXT,                      -- JSON ответа (results: title, url, snippet, published_at, acquired_at)
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS keenable_usage (
    called_at  TEXT NOT NULL,
    purpose    TEXT,
    query      TEXT,
    status     INTEGER,
    results    INTEGER,
    ms         INTEGER
);
"""


def init(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _key(query: str, params: dict) -> str:
    return hashlib.sha1(json.dumps([query, params], sort_keys=True).encode()).hexdigest()


class Keenable:
    def __init__(self, con: sqlite3.Connection):
        init(con)
        self.con = con
        self.key = os.environ["KEENABLE_API_KEY"]
        self.http = httpx.Client(timeout=60, headers={"X-API-Key": self.key, "User-Agent": USER_AGENT,
                                                      "Content-Type": "application/json"})
        self.calls = 0          # запросов к API в этом запуске (без кэша)
        self.cached = 0

    def search(self, query: str, purpose: str, **params) -> list[dict]:
        """Результаты поиска; повтор из кэша. Ошибка API (не 200) — пустой список, код ответа в keenable_usage."""
        params = {"max_results": 10, "snippet_max_length": 500} | params
        k = _key(query, params)
        row = self.con.execute("SELECT status, response FROM keenable_cache WHERE key=?", (k,)).fetchone()
        if row and row[0] == 200:
            self.cached += 1
            return json.loads(row[1]).get("results", [])
        t0 = time.monotonic()
        status, body = 0, {}
        for attempt in range(3):
            try:
                r = self.http.post(API, json={"query": query} | params)
                status = r.status_code
                body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            except httpx.HTTPError as e:
                status, body = -1, {"error": str(e)}
            if status not in (429, 500, 502, 503, 504, -1):
                break
            time.sleep(5 * (attempt + 1))
        self.calls += 1
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        results = body.get("results", []) if status == 200 else []
        self.con.execute("INSERT INTO keenable_usage VALUES (?,?,?,?,?,?)",
                         (now, purpose, query, status, len(results), int((time.monotonic() - t0) * 1000)))
        self.con.execute("INSERT OR REPLACE INTO keenable_cache VALUES (?,?,?,?,?,?,?)",
                         (k, query, json.dumps(params), purpose, status, json.dumps(body, ensure_ascii=False), now))
        self.con.commit()
        time.sleep(PAUSE)
        return results


def usage(con: sqlite3.Connection) -> dict:
    init(con)
    rows = con.execute("""SELECT purpose, count(*), sum(status=200), sum(results), avg(ms) FROM keenable_usage
                          GROUP BY purpose""").fetchall()
    return {r[0]: {"requests": r[1], "ok": r[2], "results": r[3], "avg_ms": round(r[4] or 0)} for r in rows}
