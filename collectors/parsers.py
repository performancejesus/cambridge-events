"""Парсеры форматов: iCal, JSON-LD schema.org/Event, RSS/Atom. Возвращают kwargs для RawEvent."""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime

import feedparser
from icalendar import Calendar
from selectolax.parser import HTMLParser

SUMMARY_LEN = 300
POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
EVENT_TYPES = {
    "Event", "BusinessEvent", "ChildrensEvent", "ComedyEvent", "CourseInstance", "DanceEvent",
    "EducationEvent", "ExhibitionEvent", "Festival", "FoodEvent", "LiteraryEvent", "MusicEvent",
    "SaleEvent", "ScreeningEvent", "SocialEvent", "SportsEvent", "TheaterEvent", "VisualArtsEvent",
}
STATUS = {"EventScheduled": "scheduled", "EventCancelled": "cancelled", "EventPostponed": "postponed",
          "EventRescheduled": "rescheduled", "EventMovedOnline": "moved_online"}


def clean_text(s: str | None, limit: int = SUMMARY_LEN) -> str | None:
    """HTML → короткий плоский текст."""
    if not s:
        return None
    text = HTMLParser(f"<div>{s}</div>").text(separator=" ") if "<" in s else s
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return (text[: limit - 1] + "…" if len(text) > limit else text) or None


def find_postcode(*parts: str | None) -> str | None:
    for p in parts:
        m = POSTCODE_RE.search(p or "")
        if m:
            return f"{m.group(1).upper()} {m.group(2).upper()}"
    return None


# --- iCal ---

def _ical_dt(v) -> tuple[str | None, bool]:
    if v is None:
        return None, False
    d = v.dt
    if isinstance(d, datetime):
        return d.isoformat(), False
    if isinstance(d, date):
        return d.isoformat(), True
    return str(d), False


def ical_events(content: bytes) -> list[dict]:
    out = []
    for ve in Calendar.from_ical(content).walk("VEVENT"):
        start, all_day = _ical_dt(ve.get("DTSTART"))
        end, _ = _ical_dt(ve.get("DTEND"))
        location = str(ve.get("LOCATION") or "") or None
        cats = ve.get("CATEGORIES")
        cat_list = []
        for c in (cats if isinstance(cats, list) else [cats] if cats else []):
            cat_list += [str(x) for x in getattr(c, "cats", [c])]
        status = str(ve.get("STATUS") or "").lower() or None
        out.append(dict(
            external_id=str(ve.get("UID") or "") or None,
            title=clean_text(str(ve.get("SUMMARY") or ""), 200) or "(без названия)",
            url=str(ve.get("URL") or "") or None,
            start=start, end=end, all_day=all_day,
            venue=location.split(",")[0].strip() if location else None,
            address=location, postcode=find_postcode(location),
            status={"confirmed": "scheduled", "cancelled": "cancelled", "tentative": "scheduled"}.get(status, status),
            categories=cat_list,
            summary=clean_text(str(ve.get("DESCRIPTION") or "")),
        ))
    return out


# --- JSON-LD ---

def _walk(node, out: list[dict]) -> None:
    if isinstance(node, list):
        for n in node:
            _walk(n, out)
    elif isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x) in EVENT_TYPES for x in types):
            out.append(node)
            return  # вложенные события (subEvent) не разворачиваем
        for k, v in node.items():
            if k != "@context":
                _walk(v, out)


def _first(x):
    return x[0] if isinstance(x, list) and x else x


def _name(x) -> str | None:
    x = _first(x)
    if isinstance(x, dict):
        return clean_text(x.get("name"), 200)
    return clean_text(x, 200) if isinstance(x, str) else None


def jsonld_nodes(page_html: str) -> list[dict]:
    nodes: list[dict] = []
    for s in HTMLParser(page_html).css('script[type="application/ld+json"]'):
        raw = s.text(strip=True)
        try:
            _walk(json.loads(raw), nodes)
        except json.JSONDecodeError:
            try:  # у некоторых сайтов в JSON-LD неэкранированные переводы строк
                _walk(json.loads(re.sub(r"[\r\n\t]+", " ", raw)), nodes)
            except json.JSONDecodeError:
                continue
    return nodes


def jsonld_event(n: dict) -> dict:
    loc = _first(n.get("location")) or {}
    venue = address = postcode = None
    lat = lon = None
    if isinstance(loc, dict):
        venue = clean_text(loc.get("name"), 200)
        a = loc.get("address")
        if isinstance(a, dict):
            parts = [a.get(k) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode")]
            address = ", ".join(str(p).strip(" ,") for p in parts if p and str(p).strip(" ,"))
            postcode = find_postcode(a.get("postalCode"))
        elif isinstance(a, str):
            address = clean_text(a, 300)
        postcode = postcode or find_postcode(address)
        geo = loc.get("geo") or {}
        if isinstance(geo, dict):
            try:
                lat, lon = float(geo["latitude"]), float(geo["longitude"])
            except (KeyError, TypeError, ValueError):
                pass
    elif isinstance(loc, str):
        venue = address = clean_text(loc, 300)
        postcode = find_postcode(loc)

    offers = n.get("offers")
    offers = offers if isinstance(offers, list) else [offers] if offers else []
    offers = [o for o in offers if isinstance(o, dict)]
    prices = []
    for o in offers:
        for k in ("price", "lowPrice"):
            if o.get(k) not in (None, ""):
                prices.append(f"{o.get('priceCurrency', '')} {o[k]}".strip())
                break
    # sold out — только если распроданы все предложения (одна категория билетов не в счёт)
    sold_out = bool(offers) and all("SoldOut" in str(o.get("availability", "")) for o in offers)
    status = STATUS.get(str(n.get("eventStatus", "")).rsplit("/", 1)[-1])
    if sold_out and status in (None, "scheduled"):
        status = "sold_out"
    t = n.get("@type")
    start = n.get("startDate")
    return dict(
        external_id=n.get("@id") or n.get("url"),
        title=clean_text(n.get("name"), 200) or "(без названия)",
        url=n.get("url"),
        start=start, end=n.get("endDate"),
        all_day=bool(start) and len(str(start)) == 10,
        venue=venue, address=address, postcode=postcode, lat=lat, lon=lon,
        price=", ".join(dict.fromkeys(prices)) or None,
        status=status,
        organizer=_name(n.get("organizer")) or _name(n.get("performer")),
        categories=[str(x) for x in (t if isinstance(t, list) else [t]) if x and x != "Event"],
        summary=clean_text(n.get("description")),
    )


def jsonld_events(page_html: str) -> list[dict]:
    return [jsonld_event(n) for n in jsonld_nodes(page_html)]


# --- RSS/Atom ---

def feed_items(content: bytes) -> list[dict]:
    fp = feedparser.parse(content)
    out = []
    for e in fp.entries:
        pub = e.get("published_parsed") or e.get("updated_parsed")
        out.append(dict(
            kind="article",
            external_id=e.get("id") or e.get("link"),
            title=clean_text(e.get("title"), 200) or "(без названия)",
            url=e.get("link"),
            published=datetime(*pub[:6]).isoformat() + "Z" if pub else None,
            categories=[t.get("term") for t in e.get("tags", []) if t.get("term")],
            summary=clean_text(e.get("summary")),
        ))
    return out
