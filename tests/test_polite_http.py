"""Этап 7e: общий слой бережных запросов (collectors/http.py) — на локальном сервере, без обращений к реальным сайтам."""

from __future__ import annotations

import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

HITS: list[tuple[str, str | None]] = []
MODE = {"blocked": False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS.append((self.path, self.headers.get("If-None-Match")))
        if self.path == "/robots.txt":
            body = b"User-agent: *\nDisallow: /private\n"
            self.send_response(200)
        elif MODE["blocked"] and self.path != "/":
            body = b"<html><body>Access denied. Please wait while your request is being verified (Sucuri)</body></html>"
            self.send_response(200)
        elif self.path == "/page":
            if self.headers.get("If-None-Match") == '"v1"':
                self.send_response(304)
                self.end_headers()
                return
            body = b"<html><body>" + b"event text " * 100 + b"</body></html>"
            self.send_response(200)
            self.send_header("ETag", '"v1"')
        elif self.path == "/missing":
            body = b"not found"
            self.send_response(404)
        elif self.path == "/forbidden":
            body = b"forbidden"
            self.send_response(403)
        else:
            body = b"<html><body>" + b"home page " * 100 + b"</body></html>"
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from collectors import http
    monkeypatch.setattr(http, "STATE_DB", tmp_path / "state.db")
    monkeypatch.setattr(http, "BODY_DIR", tmp_path / "pages")
    monkeypatch.setattr(http, "DELAY_SECONDS", 0.0)
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    HITS.clear()
    MODE["blocked"] = False
    c = http.PoliteClient(delay=0.0, purpose="test")
    c._client = __import__("httpx").Client(follow_redirects=True, trust_env=False, headers={"User-Agent": http.USER_AGENT})
    yield c, f"http://127.0.0.1:{srv.server_port}", http
    c.close()
    srv.shutdown()


def _age(c, url: str, hours: float) -> None:
    """Сдвинуть время последнего ответа и ошибки страницы в прошлое (имитация следующего дня)."""
    for col in ("ok_at", "error_at", "fetched_at"):
        c.db.execute(f"UPDATE pages SET {col} = replace(datetime({col}, ?), ' ', 'T') || '+00:00' "
                     f"WHERE url=? AND {col} IS NOT NULL", (f"-{hours} hours", url))


def test_page_once_a_day_then_conditional(client):
    c, base, http = client
    r1 = c.get(base + "/page")
    r2 = c.get(base + "/page")
    assert r1.status == 200 and r2.from_cache
    assert [p for p, _ in HITS] == ["/robots.txt", "/page"]          # второй раз — из кэша, без запроса
    _age(c, base + "/page", 25)
    r3 = c.get(base + "/page")
    assert HITS[-1] == ("/page", '"v1"') and r3.from_cache and b"event text" in r3.content   # 304 → тело из кэша
    results = [r[0] for r in c.db.execute("SELECT result FROM request_log ORDER BY rowid")]
    assert results == ["robots", "network", "cache", "not_modified"], results


def test_error_retry_not_before_a_day(client):
    c, base, http = client
    with pytest.raises(http.FetchError):
        c.get(base + "/missing")
    with pytest.raises(http.Deferred):
        c.get(base + "/missing")
    assert [p for p, _ in HITS].count("/missing") == 1
    _age(c, base + "/missing", 25)
    with pytest.raises(http.FetchError):
        c.get(base + "/missing")
    assert [p for p, _ in HITS].count("/missing") == 2


def test_robots_respected(client):
    c, base, http = client
    with pytest.raises(http.Disallowed):
        c.get(base + "/private")
    assert "/private" not in [p for p, _ in HITS]


def test_block_pauses_whole_host_then_homepage_first(client):
    c, base, http = client
    MODE["blocked"] = True
    with pytest.raises(http.FetchError):
        c.get(base + "/events")               # заглушка Sucuri → пауза всего домена
    with pytest.raises(http.Deferred):
        c.get(base + "/other")                # другой адрес того же домена — не запрашивается
    assert "/other" not in [p for p, _ in HITS]
    host = base.split("//")[1]
    c.db.execute("UPDATE hosts SET cooldown_until='2000-01-01T00:00:00+00:00' WHERE host=?", (host,))
    MODE["blocked"] = False
    n = len(HITS)
    c.get(base + "/page")
    assert [p for p, _ in HITS[n:]] == ["/", "/page"]   # после паузы — сначала главная
    assert c.db.execute("SELECT probation FROM hosts WHERE host=?", (host,)).fetchone()[0] == 0


def test_forbidden_pauses_host(client):
    c, base, http = client
    with pytest.raises(http.FetchError):
        c.get(base + "/forbidden")
    with pytest.raises(http.Deferred):
        c.get(base + "/page")
