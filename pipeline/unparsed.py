"""Лист «Не разобрано» (бриф, «Мои правки после просмотра v5»): источники и страницы, которые не удалось собрать.

Таблица unparsed_sources: ID, URL, тип проблемы, с какой даты, что теряем, что делать, дата последней проверки.
Перепроверка — раз в неделю (scripts/recheck_blocked.py); сайт открылся — запись получает статус resolved.

Проверка одной страницы (probe): robots.txt по RFC 9309 (4xx — «правил нет», 429/5xx/обрыв — запрет), затем одна
загрузка страницы честным User-Agent. 403, заглушка или проверка от бот-защиты — не обходим, это «Не разобрано».
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

SCHEMA = """CREATE TABLE IF NOT EXISTS unparsed_sources (
    key        TEXT PRIMARY KEY,      -- ID источника или провайдера (S020, P:cambridgekidsclub.com)
    name       TEXT,
    url        TEXT,
    problem    TEXT,                  -- http_403 | bot_challenge | tls | connection | js_only | ai_disallow | no_dates | robots_disallow | server_error
    detail     TEXT,
    since      TEXT,                  -- с какой даты проблема
    losing     TEXT,                  -- что теряем (примеры событий или программ)
    action     TEXT,                  -- перепроверить позже / найти поиском / проверить вручную / запросить у организатора
    status     TEXT,                  -- open | resolved
    last_checked TEXT
)"""
PROBLEM_RU = {"http_403": "страница отвечает 403", "bot_challenge": "заглушка или проверка бот-защиты",
              "tls": "ошибка TLS", "connection": "обрыв соединения", "js_only": "страница только на скриптах",
              "ai_disallow": "ИИ-запрет в robots.txt", "no_dates": "нет дат в HTML",
              "robots_disallow": "robots.txt запрещает", "server_error": "сервер отвечает 5xx",
              "http_other": "страница отвечает ошибкой"}
CHALLENGE_RE = re.compile(r"just a moment|cf-chl|checking your browser|attention required|captcha|are you a robot|"
                          r"access denied|request unsuccessful|incapsula|radware|perfdrive|enable javascript and cookies|"
                          r"request is being verified|sucuri",   # этап 7b: сайты колледжей за Sucuri
                          re.I)


def init(con: sqlite3.Connection) -> None:
    con.execute(SCHEMA)


def probe(http, url: str) -> tuple[str, str, str]:
    """(result, detail, text): result — ok | один из типов проблем. Одна загрузка страницы, без обхода защиты."""
    from collectors.http import Deferred, Disallowed, FetchError, Response
    from pipeline.extract import strip_html
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    try:
        allowed = http.allowed(url)
    except Deferred as e:   # этап 7e: домен на паузе или ошибка меньше суток назад — не проблема сайта, а наше правило
        return "deferred", str(e)[:160], ""
    except FetchError as e:
        return "connection", f"robots.txt: {e}"[:160], ""
    rstat = http.robots_status.get(base)
    if not allowed:
        kind = "robots_disallow" if rstat == 200 else ("connection" if rstat == -1 else "server_error")
        return kind, f"robots.txt: HTTP {rstat}", ""
    note = f"robots.txt: HTTP {rstat}" + (" (4xx — правил нет, RFC 9309)" if rstat and 400 <= rstat < 500 else "")
    try:
        r = http.fetch(url)
    except Deferred as e:
        return "deferred", f"{note}; {e}"[:200], ""
    except FetchError as e:
        msg = str(e)
        kind = "tls" if re.search(r"ssl|tls|certificate", msg, re.I) else "connection"
        return kind, f"{note}; {msg}"[:200], ""
    if r.status == 403:
        return ("bot_challenge" if CHALLENGE_RE.search(r.text[:20000]) else "http_403"), f"{note}; страница: 403", ""
    if r.status >= 500:
        return "server_error", f"{note}; страница: {r.status}", ""
    if r.status >= 400:
        return "http_other", f"{note}; страница: {r.status}", ""
    text = strip_html(r.text)
    if r.status == 202 or (CHALLENGE_RE.search(r.text[:20000]) and len(text) < 3000):
        return "bot_challenge", f"{note}; страница: {r.status}, заглушка", ""
    visible = re.sub(r"\s+", " ", re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", r.text))
    visible = re.sub(r"<[^>]+>", " ", visible)
    if len(visible.split()) < 60 and CHALLENGE_RE.search(visible):   # этап 7d: Sucuri — текст заглушки после 20 КБ стилей
        return "bot_challenge", f"{note}; страница {r.status}, заглушка «{' '.join(visible.split())[:80]}»", ""
    if len(visible.split()) < 60:
        return "js_only", f"{note}; страница {r.status}, видимого текста {len(visible.split())} слов", ""
    return "ok", f"{note}; страница: {r.status}", text


def record(con: sqlite3.Connection, key: str, name: str, url: str, problem: str, detail: str, losing: str,
           action: str) -> None:
    init(con)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = con.execute("SELECT since, problem FROM unparsed_sources WHERE key=?", (key,)).fetchone()
    since = row[0] if row and row[1] == problem else now[:10]
    con.execute("INSERT OR REPLACE INTO unparsed_sources VALUES (?,?,?,?,?,?,?,?,?,?)",
                (key, name, url, problem, detail, since, losing, action, "open", now))


def resolve(con: sqlite3.Connection, key: str, detail: str) -> None:
    init(con)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("UPDATE unparsed_sources SET status='resolved', detail=?, last_checked=? WHERE key=?", (detail, now, key))
