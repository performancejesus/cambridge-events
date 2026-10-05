"""Вежливый HTTP-клиент — единый слой для всех обращений к сайтам (сбор, статусы, ссылки, сверка, обогащение).

Этап 7e, «Бережный сбор» (и уточнение 01.10: сайты закрывались для нашего бота из-за частоты запросов):
- одно состояние на диске для всех скриптов и процессов — `data/http_state.db` (в git: метаданные и журнал) и тела
  страниц в `data/cache/pages/` (не в git);
- пауза между запросами к одному сайту — не меньше DELAY_SECONDS (6 с), Crawl-delay или HOST_DELAYS; соблюдается и
  между процессами (время последнего запроса к домену — в общем состоянии);
- одна и та же страница — не чаще раза в сутки (PAGE_TTL): повторное обращение в течение суток отдаётся из кэша;
- позже — условный запрос (If-None-Match / If-Modified-Since), ответ 304 — тело из кэша;
- ошибка страницы (4xx/5xx, обрыв, заглушка) — повтор не раньше чем через сутки (ERROR_TTL), без повторов в прогоне;
- 403, 429, 5xx или заглушка бот-защиты — пауза для всего домена на сутки (HOST_COOLDOWN); после неё — сначала один
  спокойный запрос к главной странице (probation): открылась — домен снова доступен, нет — ещё сутки паузы;
- предохранитель: не больше MAX_PER_HOST_DAY сетевых запросов к домену за сутки;
- журнал `request_log`: время, домен, адрес, модуль (purpose), результат — для отчёта «запросов к сайту в сутки».

Честный User-Agent, без маскировки под браузер. backend curl — для хостов, которые отказывают Python-клиенту по
отпечатку TLS при разрешающем robots.txt (*.cam.ac.uk, решение этапов 1–2).
"""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

ROOT = Path(__file__).resolve().parent.parent
STATE_DB = Path(os.environ.get("HTTP_STATE_DB") or ROOT / "data" / "http_state.db")
BODY_DIR = ROOT / "data" / "cache" / "pages"

USER_AGENT = "CambridgeEventsBot/0.1 (+https://github.com/performancejesus/cambridge-events)"
DELAY_SECONDS = 6.0               # бриф 7e: пауза 5–10 с между запросами к одному сайту
TIMEOUT = 30.0
PAGE_TTL = timedelta(hours=24)    # одна и та же страница — не чаще раза в сутки
ROBOTS_TTL = timedelta(hours=24)
ERROR_TTL = timedelta(hours=24)   # повтор после ошибки — не чаще раза в сутки
HOST_COOLDOWN = timedelta(hours=24)
MAX_PER_HOST_DAY = 250            # предохранитель: сетевых запросов к домену за сутки
CURL_SUFFIXES = (".cam.ac.uk",)
# Домены, которым нужна пауза длиннее общей: WordPress.com (429 уже при 2 с), cus.org (429 после десятка запросов),
# сайты, которые закрывались для нашего бота при частых запросах (этап 7e) — 10 с.
HOST_DELAYS = {"cambridgefoodies.me.uk": 20.0, "cus.org": 10.0, "www.junction.co.uk": 10.0,
               "cambridgeppf.org": 10.0, "www.cambridgeppf.org": 10.0, "www.visitcambridge.org": 10.0,
               "www.visitwestnorfolk.com": 10.0, "theatreroyal.org": 10.0}
COOLDOWN_STATUSES = {403, 429, 503, 502, 504, 520, 521, 522, 523, 524}
CHALLENGE_RE = re.compile(r"just a moment|cf-chl|checking your browser|attention required|captcha|are you a robot|"
                          r"access denied|request unsuccessful|incapsula|radware|perfdrive|enable javascript and cookies|"
                          r"request is being verified|sucuri|please wait while", re.I)

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY, host TEXT, status INTEGER, etag TEXT, last_modified TEXT,
    fetched_at TEXT,          -- последний сетевой запрос
    ok_at TEXT,               -- последний успешный ответ (тело в кэше)
    error_at TEXT, error TEXT,
    body_sha TEXT, final_url TEXT
);
CREATE TABLE IF NOT EXISTS hosts (
    host TEXT PRIMARY KEY,
    last_request REAL,        -- time.time() последнего сетевого запроса (общая пауза для всех процессов)
    cooldown_until TEXT, cooldown_reason TEXT, cooldown_since TEXT,
    probation INTEGER DEFAULT 0,   -- после паузы: сначала один запрос к главной
    robots_status INTEGER, robots_text TEXT, robots_at TEXT
);
CREATE TABLE IF NOT EXISTS request_log (
    ts TEXT NOT NULL, host TEXT NOT NULL, url TEXT, purpose TEXT,
    result TEXT NOT NULL,     -- network | not_modified | cache | skip_cooldown | skip_error | skip_budget | robots | disallowed
    status INTEGER, bytes INTEGER
);
CREATE INDEX IF NOT EXISTS request_log_host ON request_log(host, ts);
"""


class Disallowed(Exception):
    """URL запрещён robots.txt."""


class FetchError(Exception):
    pass


class Deferred(FetchError):
    """Запрос не сделан по правилам бережного сбора (пауза домена, ошибка меньше суток назад, лимит за сутки)."""


class Response:
    def __init__(self, url: str, status: int, content: bytes, headers: dict[str, str], from_cache: bool = False):
        self.url, self.status, self.content, self.headers, self.from_cache = url, status, content, headers, from_cache

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self):
        import json
        return json.loads(self.content)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def is_challenge(status: int, body: bytes) -> bool:
    """Заглушка бот-защиты: 202 (Skiddle, Sucuri) или короткий видимый текст со словами проверки."""
    if status == 202:
        return True
    head = body[:200000].decode("utf-8", "replace")
    if not CHALLENGE_RE.search(head):
        return False
    visible = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", head)
    visible = re.sub(r"<[^>]+>", " ", visible)
    return len(visible.split()) < 80 and bool(CHALLENGE_RE.search(visible))


def state(path: Path | None = None) -> sqlite3.Connection:
    path = path or STATE_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=120, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.executescript(STATE_SCHEMA)
    return con


def cooldown(host: str, reason: str, hours: float = 24, con: sqlite3.Connection | None = None) -> None:
    """Пауза для домена (вручную — для доменов, которые уже закрылись для бота)."""
    con = con or state()
    now = _now()
    con.execute("""INSERT INTO hosts(host, cooldown_until, cooldown_reason, cooldown_since, probation) VALUES (?,?,?,?,1)
        ON CONFLICT(host) DO UPDATE SET cooldown_until=excluded.cooldown_until, cooldown_reason=excluded.cooldown_reason,
        cooldown_since=coalesce(hosts.cooldown_since, excluded.cooldown_since), probation=1""",
                (host, _iso(now + timedelta(hours=hours)), reason, _iso(now)))


class PoliteClient:
    def __init__(self, curl_hosts: set[str] | None = None, delay: float = DELAY_SECONDS, purpose: str | None = None):
        self.delay = max(delay, DELAY_SECONDS)
        self.curl_hosts = curl_hosts or set()
        self.purpose = purpose or Path(sys.argv[0] or "python").stem
        self._client = httpx.Client(http2=True, follow_redirects=True, timeout=TIMEOUT,
                                    headers={"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"})
        self._robots: dict[str, RobotFileParser] = {}
        self.robots_status: dict[str, int] = {}   # код ответа robots.txt по хосту (для отчётов и «Не разобрано»)
        self.requests = 0                          # сетевые запросы этого клиента
        self.stats = {"network": 0, "not_modified": 0, "cache": 0, "deferred": 0}
        self.db = state()
        BODY_DIR.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self._client.close()

    # --- журнал и состояние ---
    def _log(self, host: str, url: str, result: str, status: int | None = None, size: int | None = None) -> None:
        self.db.execute("INSERT INTO request_log VALUES (?,?,?,?,?,?,?)",
                        (_iso(_now()), host, url, self.purpose, result, status, size))

    def _host_row(self, host: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM hosts WHERE host=?", (host,)).fetchone()

    def _check_host(self, host: str, url: str, probation: bool = True) -> None:
        """Пауза домена и суточный лимит. После паузы — сначала один запрос к главной (probation)."""
        row = self._host_row(host)
        now = _now()
        if row and row["cooldown_until"] and row["cooldown_until"] > _iso(now):
            self._log(host, url, "skip_cooldown")
            self.stats["deferred"] += 1
            raise Deferred(f"{host}: пауза до {row['cooldown_until']} ({row['cooldown_reason']})")
        day = self.db.execute("SELECT count(*) FROM request_log WHERE host=? AND result IN ('network','not_modified','robots') "
                              "AND ts >= ?", (host, _iso(now - timedelta(hours=24)))).fetchone()[0]
        if day >= MAX_PER_HOST_DAY:
            self._log(host, url, "skip_budget")
            self.stats["deferred"] += 1
            raise Deferred(f"{host}: лимит {MAX_PER_HOST_DAY} запросов в сутки")
        if probation and row and row["probation"]:
            p = urlparse(url)
            root = f"{p.scheme}://{p.netloc}/"
            if url != root and self.allowed(root):
                r = self._network(root, host)   # один спокойный запрос к главной
                if r.status != 200 or is_challenge(r.status, r.content):
                    self._set_cooldown(host, f"после паузы главная: {r.status}{' заглушка' if r.status == 200 else ''}")
                    raise Deferred(f"{host}: после паузы главная не открылась ({r.status})")
            self.db.execute("UPDATE hosts SET probation=0, cooldown_since=NULL WHERE host=?", (host,))

    def _set_cooldown(self, host: str, reason: str) -> None:
        cooldown(host, reason, HOST_COOLDOWN.total_seconds() / 3600, self.db)

    def _wait(self, host: str, robots: RobotFileParser | None) -> None:
        """Пауза между запросами к домену — общая для всех процессов (время последнего запроса в состоянии)."""
        cd = float((robots.crawl_delay(USER_AGENT) if robots else None) or 0)
        delay = max(self.delay, HOST_DELAYS.get(host, 0.0), cd)
        while True:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT last_request FROM hosts WHERE host=?", (host,)).fetchone()
            wait = delay - (time.time() - ((row and row[0]) or 0))
            if wait <= 0:
                self.db.execute("INSERT INTO hosts(host, last_request) VALUES (?,?) ON CONFLICT(host) DO UPDATE "
                                "SET last_request=excluded.last_request", (host, time.time()))
                self.db.execute("COMMIT")
                return
            self.db.execute("COMMIT")
            time.sleep(min(wait, delay))

    # --- robots.txt (кэш на сутки, общий для всех процессов) ---
    def _robots_for(self, url: str) -> RobotFileParser:
        p = urlparse(url)
        base, host = f"{p.scheme}://{p.netloc}", p.netloc
        if base in self._robots:
            return self._robots[base]
        rp = RobotFileParser()
        row = self._host_row(host)
        if row and row["robots_at"] and row["robots_at"] > _iso(_now() - ROBOTS_TTL) and row["robots_status"] is not None:
            status, text = row["robots_status"], row["robots_text"] or ""
        else:
            self._check_host(host, base + "/robots.txt", probation=False)
            self._wait(host, None)
            try:
                r = self._fetch_raw(base + "/robots.txt", {})
                status, text = r.status, (r.text if r.status == 200 else "")
            except FetchError:   # обрыв соединения, TLS — полный запрет (RFC 9309, 2.3.1.4)
                status, text = -1, ""
            self.requests += 1
            self._log(host, base + "/robots.txt", "robots", status)
            self.db.execute("""INSERT INTO hosts(host, robots_status, robots_text, robots_at) VALUES (?,?,?,?)
                ON CONFLICT(host) DO UPDATE SET robots_status=excluded.robots_status, robots_text=excluded.robots_text,
                robots_at=excluded.robots_at""", (host, status, text, _iso(_now())))
            if status == 429 or status >= 500 or status == -1:   # прогон 7e+: обрыв на robots.txt — тоже пауза домена
                self._set_cooldown(host, f"robots.txt: {'обрыв соединения' if status == -1 else status}")
        if status == 200:
            rp.parse(text.splitlines())
        elif status == 429 or status >= 500 or status == -1:
            rp.disallow_all = True  # сервер недоступен — считаем, что запрещено (RFC 9309, 2.3.1.4)
        else:
            # RFC 9309, 2.3.1.3: 4xx на robots.txt (в т.ч. 401/403) — «правил нет», страницы можно загружать.
            # Если сама страница отвечает 403 или заглушкой — это защита от ботов: не обходим, лист «Не разобрано».
            rp.allow_all = True
        self.robots_status[base] = status
        self._robots[base] = rp
        return rp

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(USER_AGENT, url)

    # --- сеть ---
    def _fetch_raw(self, url: str, headers: dict[str, str]) -> Response:
        host = urlparse(url).netloc
        try:
            if host in self.curl_hosts or host.endswith(CURL_SUFFIXES):
                return self._curl(url, headers)
            r = self._client.get(url, headers=headers)
            return Response(str(r.url), r.status_code, r.content, {k.lower(): v for k, v in r.headers.items()})
        except httpx.HTTPError as e:
            raise FetchError(f"{type(e).__name__}: {e}") from e

    def _curl(self, url: str, headers: dict[str, str]) -> Response:
        with tempfile.NamedTemporaryFile() as hdr:
            cmd = ["curl", "-sS", "-L", "--max-time", str(int(TIMEOUT)), "-A", USER_AGENT, "-D", hdr.name,
                   "-H", "Accept-Language: en-GB,en;q=0.8", "-w", "\n%{http_code} %{url_effective}"]
            for k, v in headers.items():
                cmd += ["-H", f"{k}: {v}"]
            out = subprocess.run(cmd + [url], capture_output=True, check=False)
            if out.returncode != 0:
                raise FetchError(f"curl: {out.stderr.decode(errors='replace').strip()}")
            raw_headers = Path(hdr.name).read_text(errors="replace").split("\r\n\r\n")
        body, _, meta = out.stdout.rpartition(b"\n")
        status, _, final = meta.decode().partition(" ")
        last = [b for b in raw_headers if b.strip()][-1:] or [""]
        hd = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in last[0].splitlines()[1:]) if k}
        return Response(final, int(status), body, hd)

    def _network(self, url: str, host: str, cond: dict[str, str] | None = None) -> Response:
        robots = self._robots.get(f"{urlparse(url).scheme}://{host}")
        self._wait(host, robots)
        self.requests += 1
        try:
            r = self._fetch_raw(url, cond or {})
        except FetchError as e:
            self._log(host, url, "network", -1)
            self.stats["network"] += 1
            self._page_error(url, host, -1, str(e)[:200])
            if re.search(r"ConnectError|ConnectTimeout|RemoteProtocolError|ReadTimeout|reset|curl", str(e)):
                self._set_cooldown(host, f"обрыв соединения: {str(e)[:80]}")
            raise
        self.stats["not_modified" if r.status == 304 else "network"] += 1
        self._log(host, url, "not_modified" if r.status == 304 else "network", r.status, len(r.content))
        return r

    def _page_error(self, url: str, host: str, status: int, err: str) -> None:
        now = _iso(_now())
        self.db.execute("""INSERT INTO pages(url, host, status, fetched_at, error_at, error) VALUES (?,?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET status=excluded.status, fetched_at=excluded.fetched_at,
            error_at=excluded.error_at, error=excluded.error""", (url, host, status, now, now, err))

    @staticmethod
    def _body_path(url: str) -> Path:
        return BODY_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".gz")

    def _cached(self, url: str, row: sqlite3.Row, host: str) -> Response | None:
        path = self._body_path(url)
        if not path.exists():
            return None
        return Response(row["final_url"] or url, 200, gzip.decompress(path.read_bytes()), {"x-cache": "hit"},
                        from_cache=True)

    def fetch(self, url: str) -> Response:
        """Запрос по всем правилам бережного сбора. Возвращает ответ с любым кодом (из кэша — 200).
        Бросает Disallowed (robots.txt), Deferred (пауза домена, ошибка < суток назад, лимит), FetchError (сеть)."""
        if not self.allowed(url):
            self._log(urlparse(url).netloc, url, "disallowed")
            raise Disallowed(url)
        host = urlparse(url).netloc
        now = _now()
        row = self.db.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()
        if row and row["ok_at"] and row["ok_at"] > _iso(now - PAGE_TTL) and not (row["error_at"] and row["error_at"] > row["ok_at"]):
            cached = self._cached(url, row, host)
            if cached:
                self._log(host, url, "cache", 200)
                self.stats["cache"] += 1
                return cached
        if row and row["error_at"] and row["error_at"] > _iso(now - ERROR_TTL) and (not row["ok_at"] or row["error_at"] > row["ok_at"]):
            self._log(host, url, "skip_error", row["status"])
            self.stats["deferred"] += 1
            raise Deferred(f"{url}: ошибка {row['status']} меньше суток назад ({row['error_at']}); повтор — завтра")
        self._check_host(host, url)
        cond = {}
        if row and row["ok_at"] and self._body_path(url).exists():
            if row["etag"]:
                cond["If-None-Match"] = row["etag"]
            if row["last_modified"]:
                cond["If-Modified-Since"] = row["last_modified"]
        r = self._network(url, host, cond)
        if r.status == 304 and row:
            self.db.execute("UPDATE pages SET fetched_at=?, ok_at=?, status=200 WHERE url=?", (_iso(now), _iso(now), url))
            cached = self._cached(url, row, host)
            if cached:
                return cached
        if r.status == 200 and not is_challenge(r.status, r.content):
            self._body_path(url).write_bytes(gzip.compress(r.content))
            self.db.execute("""INSERT INTO pages(url, host, status, etag, last_modified, fetched_at, ok_at, error_at, error,
                body_sha, final_url) VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?) ON CONFLICT(url) DO UPDATE SET
                status=200, etag=excluded.etag, last_modified=excluded.last_modified, fetched_at=excluded.fetched_at,
                ok_at=excluded.ok_at, error_at=NULL, error=NULL, body_sha=excluded.body_sha, final_url=excluded.final_url""",
                            (url, host, 200, r.headers.get("etag"), r.headers.get("last-modified"), _iso(now), _iso(now),
                             hashlib.sha1(r.content).hexdigest(), r.url))
            return r
        challenge = r.status in (200, 202) and is_challenge(r.status, r.content)
        self._page_error(url, host, r.status, "заглушка бот-защиты" if challenge else f"HTTP {r.status}")
        # 202 (Skiddle отвечает так ботам на отдельные страницы событий, списки при этом открываются) — ошибка только
        # этой страницы; пауза всего домена — на 403 / 429 / 5xx / обрыв и на настоящую заглушку проверки (200)
        if (challenge and r.status != 202) or r.status in COOLDOWN_STATUSES:
            self._set_cooldown(host, f"{'заглушка бот-защиты' if challenge else 'HTTP ' + str(r.status)} на {url[:120]}")
        return r

    def get(self, url: str) -> Response:
        """GET по правилам бережного сбора; не 200 или заглушка — FetchError (повтор не раньше чем через сутки)."""
        r = self.fetch(url)
        if r.status != 200 or (not r.from_cache and is_challenge(r.status, r.content)):
            raise FetchError(f"HTTP {r.status}{' bot challenge (заглушка бот-защиты)' if r.status in (200, 202) else ''} {url}")
        return r

    # совместимость: прежний низкоуровневый вызов теперь идёт через все правила
    def _raw_get(self, url: str) -> Response:
        return self.fetch(url)


def last_modified_ok(value: str | None) -> bool:
    try:
        return bool(value and parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return False
