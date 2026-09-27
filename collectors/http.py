"""Вежливый HTTP-клиент: robots.txt, пауза между запросами к хосту, бэк-офф на 429.

- честный User-Agent, без маскировки под браузер;
- пауза не меньше DELAY_SECONDS или Crawl-delay из robots.txt;
- на 429/503 — ожидание Retry-After (или 30/60/120 с) и не больше трёх попыток;
- backend="curl" — тот же запрос через curl (для хостов, которые отказывают Python-клиенту
  по отпечатку TLS, при этом robots.txt разрешает доступ; см. решение по этапу 1).
"""

from __future__ import annotations

import subprocess
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "CambridgeEventsBot/0.1 (+https://github.com/performancejesus/cambridge-events)"
DELAY_SECONDS = 2.0
TIMEOUT = 30.0
BACKOFF = (30, 60, 120)
# Хосты, которые отвечают 429 уже при паузе в 2 с (WordPress.com): своя, более длинная пауза.
HOST_DELAYS = {"cambridgefoodies.me.uk": 20.0}


class Disallowed(Exception):
    """URL запрещён robots.txt."""


class FetchError(Exception):
    pass


class Response:
    def __init__(self, url: str, status: int, content: bytes, headers: dict[str, str]):
        self.url, self.status, self.content, self.headers = url, status, content, headers

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self):
        import json
        return json.loads(self.content)


class PoliteClient:
    def __init__(self, curl_hosts: set[str] | None = None, delay: float = DELAY_SECONDS):
        self.delay = delay
        self.curl_hosts = curl_hosts or set()
        self._client = httpx.Client(http2=True, follow_redirects=True, timeout=TIMEOUT,
                                    headers={"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"})
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser] = {}
        self.requests = 0

    def close(self) -> None:
        self._client.close()

    # --- robots.txt ---
    def _robots_for(self, url: str) -> RobotFileParser:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            r = self._raw_get(base + "/robots.txt")
            for pause in BACKOFF[:2]:  # 429/5xx на robots.txt — повторить позже (RFC 9309)
                if r.status != 429 and r.status < 500:
                    break
                time.sleep(pause)
                r = self._raw_get(base + "/robots.txt")
            if r.status == 200:
                rp.parse(r.text.splitlines())
            elif r.status in (401, 403, 429) or r.status >= 500:
                rp.disallow_all = True  # правила неизвестны — считаем, что запрещено
            else:
                rp.allow_all = True  # 404 и т.п.: robots.txt нет
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        return self._robots_for(url).can_fetch(USER_AGENT, url)

    # --- запросы ---
    def _wait(self, host: str) -> None:
        rp = self._robots.get(f"https://{host}") or self._robots.get(f"http://{host}")
        delay = max(self.delay, HOST_DELAYS.get(host, 0.0), float((rp.crawl_delay(USER_AGENT) if rp else None) or 0))
        wait = delay - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)

    def _raw_get(self, url: str) -> Response:
        host = urlparse(url).netloc
        self._wait(host)
        try:
            self.requests += 1
            if host in self.curl_hosts:
                return self._curl(url)
            r = self._client.get(url)
            return Response(str(r.url), r.status_code, r.content, dict(r.headers))
        except httpx.HTTPError as e:
            raise FetchError(f"{type(e).__name__}: {e}") from e
        finally:
            self._last[host] = time.monotonic()

    def _curl(self, url: str) -> Response:
        out = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", str(int(TIMEOUT)), "-A", USER_AGENT,
             "-H", "Accept-Language: en-GB,en;q=0.8", "-w", "\n%{http_code} %{url_effective}", url],
            capture_output=True, check=False)
        if out.returncode != 0:
            raise FetchError(f"curl: {out.stderr.decode(errors='replace').strip()}")
        body, _, meta = out.stdout.rpartition(b"\n")
        status, _, final = meta.decode().partition(" ")
        return Response(final, int(status), body, {})

    def get(self, url: str) -> Response:
        """GET с проверкой robots.txt и бэк-оффом на 429/503. Бросает Disallowed / FetchError."""
        if not self.allowed(url):
            raise Disallowed(url)
        for attempt in range(len(BACKOFF) + 1):
            try:
                r = self._raw_get(url)
            except FetchError:
                if attempt:  # сетевой сбой — один повтор через 10 с
                    raise
                time.sleep(10)
                r = self._raw_get(url)
            if r.status not in (429, 503) or attempt == len(BACKOFF):
                break
            retry_after = r.headers.get("retry-after", "")
            time.sleep(int(retry_after) if retry_after.isdigit() else BACKOFF[attempt])
        if r.status != 200:
            raise FetchError(f"HTTP {r.status} {url}")
        return r
