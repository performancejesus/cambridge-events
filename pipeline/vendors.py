"""Этап 6d (оценка монетизации): продавец билетов события — по ссылкам со страницы события.

Продавец — не страница площадки, а тот, кто продаёт билет: Ticketmaster, See Tickets, Eventbrite, Skiddle, … или
собственная касса площадки (Spektrix, Ticketsolve и т.п.). Порядок:
  1. URL события или одного из его источников сам на домене продавца → продавец;
  2. страница события (одна загрузка, robots.txt соблюдается, без модели) → ссылки на домены продавцов и признаки
     кассовых систем в HTML (spektrix, ticketsolve, …); ссылка «Book/Buy tickets» на тот же сайт → «своя касса»;
  3. иначе — «не определён».
Таблица ticket_vendors: event_id, vendor, vendor_host, method, page_url, checked_at.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

SCHEMA = """CREATE TABLE IF NOT EXISTS ticket_vendors (
    event_id INTEGER PRIMARY KEY, vendor TEXT, vendor_host TEXT, method TEXT, page_url TEXT, checked_at TEXT
)"""
# домен → продавец (порядок важен: более специфичные — раньше)
VENDORS = [
    ("ticketmaster.", "Ticketmaster"), ("seetickets.", "See Tickets"), ("eventbrite.", "Eventbrite"),
    ("skiddle.com", "Skiddle"), ("wegottickets.com", "WeGotTickets"), ("dice.fm", "DICE"), ("fatsoma.com", "Fatsoma"),
    ("ticketsource.co.uk", "TicketSource"), ("tickettailor.com", "Ticket Tailor"), ("buytickets.at", "Ticket Tailor"),
    ("axs.com", "AXS"), ("gigantic.com", "Gigantic"), ("ticketweb.", "TicketWeb"), ("universe.com", "Universe"),
    ("billetto.", "Billetto"), ("eventim.", "Eventim"), ("fixr.co", "FIXR"), ("ticketline.co.uk", "Ticketline"),
    ("trybooking.com", "TryBooking"), ("ents24.com", "Ents24 (агрегатор)"), ("stubhub.", "StubHub (перепродажа)"),
    ("viagogo.", "viagogo (перепродажа)"), ("eticketing.co.uk", "eTicketing (SECUTIX, клубы)"),
    ("thejockeyclub.co.uk", "The Jockey Club (своя касса)"), ("ticketsolve.com", "Ticketsolve"),
    ("spektrix.com", "Spektrix (касса площадки)"), ("patronbase.", "PatronBase (касса площадки)"),
    ("tickets.cambridgelive.org.uk", "Cambridge Live (касса)"), ("bookwhen.com", "Bookwhen"),
    ("classforkids.io", "ClassForKids"), ("bookpebble.co.uk", "Pebble"), ("clubhubuk.co.uk", "ClubHub UK"),
    ("nationaltrust.org.uk", "National Trust (своя касса)"), ("english-heritage.org.uk", "English Heritage (своя касса)"),
    ("iwm.org.uk", "IWM (своя касса)"), ("ticketing.museums.cam.ac.uk", "University museums (касса)"),
    ("digitickets.co.uk", "DigiTickets"), ("citizenticket.", "Citizen Ticket"), ("tixr.com", "Tixr"),
    ("ticketsuite.", "TicketSuite"), ("red61.", "Red61 (касса площадки)"), ("tessitura", "Tessitura (касса площадки)"),
    ("iceaccount.co.uk", "Planet Ice (своя касса)"), ("playwaze.com", "Playwaze"), ("findarace.com", "Find a Race"),
    ("letsdothis.com", "Let's Do This"), ("entrycentral.com", "Entry Central"), ("racebest.com", "RaceBest"),
    ("sientries.co.uk", "SI Entries"), ("howlerapp", "Howler"), ("designmynight.com", "DesignMyNight"),
    ("resdiary.com", "ResDiary"), ("ticketsource.", "TicketSource"),
]
# признаки кассовой системы в HTML страницы
SYSTEM_RE = [(re.compile(r"spektrix", re.I), "Spektrix (касса площадки)"),
             (re.compile(r"ticketsolve", re.I), "Ticketsolve"), (re.compile(r"patronbase", re.I), "PatronBase (касса площадки)"),
             (re.compile(r"tessitura", re.I), "Tessitura (касса площадки)"), (re.compile(r"red61", re.I), "Red61 (касса площадки)"),
             (re.compile(r"audienceview", re.I), "AudienceView (касса площадки)")]
BOOK_RE = re.compile(r"\b(book( now| tickets?)?|buy( now| tickets?)|tickets?|get tickets|reserve|register|sign up|enter)\b",
                     re.I)
NEWS_HOSTS = {"cambridge-news.co.uk", "cambridgeindependent.co.uk", "peterboroughtoday.co.uk", "huntspost.co.uk",
              "cambstimes.co.uk", "wisbechstandard.co.uk", "elystandard.co.uk", "cambridge105.co.uk"}
AGGREGATORS = {"visitcambridge.org", "ents24.com", "camdram.net", "talks.cam.ac.uk", "whatsonincambridge.com",
               "musiclivecambridge.com", "cambridge105.co.uk", "museums.cam.ac.uk", "findarace.com"}
# сайты площадок, на которые ведут афиши (Camdram → ADC и т.п.)
VENUE_HOSTS = {"adctheatre.com", "cornex.co.uk", "cambridgeartstheatre.com", "junction.co.uk", "saffronhall.com",
               "theapex.co.uk", "cambridgelivetickets.co.uk", "mumfordtheatre.co.uk", "thecambridgeunion.co.uk"}
# хосты одной кассы → одно название
SAME_BOX = {"cornex.co.uk": "Cambridge Live (касса Corn Exchange и Guildhall)",
            "cambridgelivetickets.co.uk": "Cambridge Live (касса Corn Exchange и Guildhall)"}
# реклама и шаблоны на страницах (виджет London Theatre Direct у газет, демо-ссылки тем WordPress, агрегаторы)
NOISE_HOSTS = ("londontheatredirect.com", "qodeinteractive.com", "allevents.in", "wordpress.com", "wix.com")
SOCIAL = ("facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "youtube.com", "linkedin.com",
          "google.com", "apple.com", "spotify.com", "wikipedia.org")


def host(url: str) -> str:
    h = (urlparse(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def by_domain(url: str) -> str | None:
    h = host(url)
    full = (url or "").lower()
    for dom, name in VENDORS:
        if dom in h or (dom.endswith("/") and dom in full):
            return name
    return None


def from_page(html: str, page_url: str) -> tuple[str | None, str | None, str]:
    """(продавец, хост продавца, способ) по HTML страницы события."""
    from selectolax.parser import HTMLParser
    tree = HTMLParser(html)
    links = []
    for a in tree.css("a[href]"):
        href = urljoin(page_url, a.attributes.get("href") or "")
        text = (a.text() or "").strip()
        links.append((href, text))
    # 1) кнопка «Book / Buy tickets» — главный сигнал
    for href, text in links:
        if BOOK_RE.search(text):
            v = by_domain(href)
            if v and not v.startswith("Ents24"):
                return v, host(href), "кнопка покупки на странице"
    # 2) любая ссылка на продавца
    for href, _ in links:
        v = by_domain(href)
        if v and not v.startswith(("Ents24", "StubHub", "viagogo")):
            return v, host(href), "ссылка на продавца на странице"
    # 3) кассовая система площадки в HTML
    for rx, name in SYSTEM_RE:
        if rx.search(html):
            return name, host(page_url), "кассовая система в коде страницы"
    # 4) кнопка покупки на тот же сайт — своя касса (не для агрегаторов афиш)
    if host(page_url) not in AGGREGATORS:
        for href, text in links:
            if BOOK_RE.search(text) and host(href) == host(page_url) and re.search(r"book|ticket|basket|checkout|event",
                                                                                      href, re.I):
                return f"своя касса ({host(page_url)})", host(page_url), "кнопка покупки на свой сайт"
    return None, None, "не определён"


def book_link_out(html: str, page_url: str) -> str | None:
    """Кнопка покупки/записи, ведущая на другой сайт (афиша → площадка или продавец)."""
    from selectolax.parser import HTMLParser
    for a in HTMLParser(html).css("a[href]"):
        href = urljoin(page_url, a.attributes.get("href") or "")
        h = host(href)
        if h and h != host(page_url) and not h.endswith(SOCIAL + NOISE_HOSTS) and (BOOK_RE.search(a.text() or "")
                                                                      or re.search(r"ticket|book", href, re.I)
                                                                      or h in VENUE_HOSTS):
            return href
    return None


def classify(con: sqlite3.Connection, http, event_id: int, urls: list[str], refresh: bool = False) -> dict:
    con.execute(SCHEMA)
    if not refresh:
        r = con.execute("SELECT * FROM ticket_vendors WHERE event_id=?", (event_id,)).fetchone()
        if r:
            return dict(r)
    urls = [u for u in dict.fromkeys(urls) if u and u.startswith("http")]
    res = {"vendor": "не определён", "vendor_host": None, "method": "не определён", "page_url": urls[0] if urls else None}
    for u in urls:   # 1) сам URL — у продавца
        v = by_domain(u)
        if v and not v.startswith("Ents24"):
            res = {"vendor": v, "vendor_host": host(u), "method": "ссылка события ведёт к продавцу", "page_url": u}
            break
    else:
        # 2) страница первоисточника (не газета и не агрегатор, если есть другая)
        ordered = sorted(urls, key=lambda u: (host(u) in NEWS_HOSTS, host(u) in AGGREGATORS))
        for u in ordered[:2]:
            try:
                html = http.get(u).text
            except Exception as e:  # noqa: BLE001 — robots.txt, защита, ошибка: пробуем следующую ссылку
                res["method"] = f"страница недоступна: {type(e).__name__}"
                continue
            v, vh, how = from_page(html, u)
            if host(u) in NEWS_HOSTS and v and (vh or "").endswith(NOISE_HOSTS + (host(u),)):
                v = None   # газета: рекламный виджет или своя «касса» газеты — не продавец события
            if not v and host(u) not in NEWS_HOSTS:   # афиша или страница без продавца → переход по кнопке покупки
                out = book_link_out(html, u)
                if out:
                    v = by_domain(out)
                    if v and not v.startswith("Ents24"):
                        vh, how = host(out), "переход по кнопке покупки → продавец"
                    else:
                        try:
                            v, vh, how = from_page(http.get(out).text, out)
                            how = f"переход по кнопке покупки → {how}" if v else how
                        except Exception as e:  # noqa: BLE001
                            v, how = None, f"переход по кнопке покупки: {type(e).__name__} {str(e)[:60]}"
            if v:
                res = {"vendor": v, "vendor_host": vh, "method": how, "page_url": u}
                break
            res = {"vendor": "не определён", "vendor_host": None,
                   "method": how if how.startswith("переход") else "на странице нет ссылки на продавца", "page_url": u}
    if res.get("vendor_host") in SAME_BOX and res["vendor"].startswith("своя касса"):
        res["vendor"] = SAME_BOX[res["vendor_host"]]
    con.execute("INSERT OR REPLACE INTO ticket_vendors VALUES (?,?,?,?,?,?)",
                (event_id, res["vendor"], res["vendor_host"], res["method"], res["page_url"],
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
    con.commit()
    return {"event_id": event_id} | res
