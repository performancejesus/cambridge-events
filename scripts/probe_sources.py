"""Этап 1: проверка источников приоритета 1.

Для каждого кандидатного URL из data/p1_candidates.json:
  - проверяет robots.txt (страницы, запрещённые для нашего User-Agent, не запрашиваются);
  - запрашивает страницу и фиксирует HTTP-статус и конечный URL после редиректов;
  - ищет способы сбора: RSS/Atom (<link rel=alternate>, /feed), iCal (.ics, webcal, ?ical=1),
    JSON-LD schema.org/Event, признаки API (WordPress REST, The Events Calendar), и т.п.

Результат: data/probe_results.json. Между запросами к одному хосту — пауза.

Запуск: python scripts/probe_sources.py [S001 S047 ...]
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from icalendar import Calendar
from selectolax.parser import HTMLParser

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "p1_candidates.json"
OUT = ROOT / "data" / "probe_results.json"

USER_AGENT = "CambridgeEventsBot/0.1 (+https://github.com/performancejesus/cambridge-events)"
DELAY_SECONDS = 2.0
TIMEOUT = 25.0

EVENT_TYPES = {
    "Event", "BusinessEvent", "ChildrensEvent", "ComedyEvent", "CourseInstance", "DanceEvent",
    "DeliveryEvent", "EducationEvent", "ExhibitionEvent", "Festival", "FoodEvent", "Hackathon",
    "LiteraryEvent", "MusicEvent", "PublicationEvent", "SaleEvent", "ScreeningEvent",
    "SocialEvent", "SportsEvent", "TheaterEvent", "VisualArtsEvent", "EventSeries",
}

_last_hit: dict[str, float] = {}
_robots: dict[str, RobotFileParser | None] = {}
_robots_blocked: set[str] = set()  # хосты, отдавшие 401/403 на сам robots.txt


def polite_get(client: httpx.Client, url: str) -> httpx.Response:
    host = urlparse(url).netloc
    wait = DELAY_SECONDS - (time.monotonic() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    try:
        return client.get(url)
    finally:
        _last_hit[host] = time.monotonic()


def robots_for(client: httpx.Client, url: str) -> RobotFileParser | None:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = RobotFileParser()
        try:
            r = polite_get(client, base + "/robots.txt")
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            elif r.status_code in (401, 403):
                rp.disallow_all = True
                _robots_blocked.add(base)
            else:
                rp.allow_all = True
            _robots[base] = rp
        except httpx.HTTPError:
            _robots[base] = None
    return _robots[base]


def jsonld_types(tree: HTMLParser) -> tuple[list[str], int]:
    """Возвращает (все @type из JSON-LD, число объектов-событий)."""
    types: list[str] = []
    events = 0

    def walk(node):
        nonlocal events
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            ts = t if isinstance(t, list) else [t] if t else []
            for x in ts:
                types.append(str(x))
                if str(x) in EVENT_TYPES:
                    events += 1
            for k, v in node.items():
                if k != "@context":
                    walk(v)

    for s in tree.css('script[type="application/ld+json"]'):
        try:
            walk(json.loads(s.text(strip=True) or "null"))
        except json.JSONDecodeError:
            types.append("<invalid JSON-LD>")
    return sorted(set(types)), events


def html_signals(base_url: str, html: str) -> dict:
    tree = HTMLParser(html)
    sig: dict = {}
    feeds = []
    for link in tree.css('link[rel="alternate"]'):
        t = (link.attributes.get("type") or "").lower()
        href = link.attributes.get("href")
        if href and any(k in t for k in ("rss", "atom", "calendar", "json")):
            feeds.append({"type": t, "url": urljoin(base_url, href)})
    sig["alternate_links"] = feeds

    ical, rssish = set(), set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        low = href.lower()
        if low.startswith("webcal:") or ".ics" in low or "ical=" in low or "/ical" in low or "outlook-ical" in low:
            ical.add(urljoin(base_url, href))
        elif re.search(r"(/feed/?$|/rss|\.rss$|\.xml$|format=rss)", low):
            rssish.add(urljoin(base_url, href))
    sig["ical_links"] = sorted(ical)[:10]
    sig["feed_links_in_page"] = sorted(rssish)[:10]

    types, n_events = jsonld_types(tree)
    sig["jsonld_types"] = types
    sig["jsonld_events"] = n_events
    sig["microdata_event"] = bool(tree.css('[itemtype*="schema.org/"][itemtype*="Event"]'))

    gen = tree.css_first('meta[name="generator"]')
    sig["generator"] = gen.attributes.get("content") if gen else None
    sig["wordpress"] = "wp-content" in html or "wp-json" in html
    sig["tribe_events"] = "tribe-events" in html or "tribe_events" in html
    sig["wp_json"] = next((urljoin(base_url, l.attributes.get("href", "")) for l in tree.css('link[rel="https://api.w.org/"]')), None)
    sig["mentions"] = sorted({m for m in ("eventbrite", "ticketsolve", "spektrix", "seetickets", "ticketmaster", "skiddle", "ents24", "fatsoma", "ecal", "gigantic", "tessitura", "audience republic", "ticketsource") if m in html.lower()})
    title = tree.css_first("title")
    sig["title"] = title.text(strip=True)[:120] if title else None
    return sig


def classify_body(url: str, resp: httpx.Response) -> dict:
    ct = resp.headers.get("content-type", "").lower()
    body = resp.content
    info: dict = {"content_type": ct}
    text_head = body[:2000].decode("utf-8", "ignore").lstrip()
    if "calendar" in ct or text_head.startswith("BEGIN:VCALENDAR"):
        try:
            cal = Calendar.from_ical(body)
            info["kind"] = "ical"
            info["ical_events"] = len(cal.walk("VEVENT"))
        except Exception as e:  # noqa: BLE001
            info["kind"] = "ical?"
            info["error"] = str(e)[:200]
    elif "json" in ct:
        info["kind"] = "json"
        try:
            data = resp.json()
            if isinstance(data, dict):
                info["json_keys"] = list(data)[:15]
                if isinstance(data.get("events"), list):
                    info["json_events"] = len(data["events"])
            elif isinstance(data, list):
                info["json_items"] = len(data)
        except ValueError:
            pass
    elif any(k in ct for k in ("xml", "rss", "atom")) or text_head.startswith("<?xml") or text_head.startswith("<rss"):
        fp = feedparser.parse(body)
        if fp.entries or fp.feed.get("title"):
            info["kind"] = "feed"
            info["feed_title"] = fp.feed.get("title")
            info["feed_entries"] = len(fp.entries)
            info["feed_latest"] = fp.entries[0].get("published") if fp.entries else None
        else:
            info["kind"] = "xml"
    elif "html" in ct:
        info["kind"] = "html"
        info.update(html_signals(str(resp.url), resp.text))
    else:
        info["kind"] = "other"
    return info


def probe_url(client: httpx.Client, url: str) -> dict:
    res: dict = {"url": url}
    rp = robots_for(client, url)
    if rp is None:
        res["robots"] = "недоступен"
    else:
        allowed = rp.can_fetch(USER_AGENT, url)
        res["robots"] = "разрешено" if allowed else "запрещено"
        if not allowed and f"{urlparse(url).scheme}://{urlparse(url).netloc}" in _robots_blocked:
            res["robots"] = "robots.txt: 403"  # сервер отказал нашему клиенту, а не запретил путь
        if not allowed:
            return res
    try:
        r = polite_get(client, url)
    except httpx.HTTPError as e:
        res["error"] = f"{type(e).__name__}: {e}"[:300]
        return res
    res["status"] = r.status_code
    res["final_url"] = str(r.url)
    if r.status_code == 200:
        res.update(classify_body(str(r.url), r))
    return res


def main(ids: list[str]) -> None:
    candidates = {k: v for k, v in json.loads(CANDIDATES.read_text()).items() if not k.startswith("_")}
    results = json.loads(OUT.read_text()) if OUT.exists() and ids else {}
    todo = ids or list(candidates)
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"},
                      follow_redirects=True, timeout=TIMEOUT, http2=True) as client:
        for sid in todo:
            urls = candidates.get(sid, [])
            print(f"{sid}: {len(urls)} URL", file=sys.stderr)
            results[sid] = {
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "urls": [probe_url(client, u) for u in urls],
            }
            OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Готово: {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
