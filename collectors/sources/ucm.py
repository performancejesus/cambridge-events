"""S052 University of Cambridge Museums — сводная афиша (Drupal views, HTML): Fitzwilliam, Kettle's Yard, Museum of
Zoology, Sedgwick, Polar Museum, MAA, Whipple, Museum of Classical Archaeology, Botanic Garden.

Список целиком на одной странице (infinite scroll отдаёт тот же набор). Семейные события — по фильтрам сайта
(«для кого»: Families / Under 5s / 5+, тип «Family events»): у найденных там событий категория family, чтобы тег
«С детьми» опирался на разметку музея, а не на догадку. Строки-ссылки на блог (без даты) пропускаются.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from ..base import Collector, RawEvent

BASE = "https://www.museums.cam.ac.uk/whats-on"
FAMILY_FILTERS = {"field_for_whom_target_id=14": "families", "field_for_whom_target_id=15": "under 5s",
                  "field_for_whom_target_id=16": "ages 5+", "field_event_type_target_id=102": "family events"}
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)", re.I)


def _field(row, name: str) -> str:
    n = row.css_first(f"div.views-field-{name}")
    return n.text(separator=" ", strip=True) if n else ""


def _date(s: str) -> str | None:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _time(s: str, i: int) -> str | None:
    t = TIME_RE.findall(s)
    if len(t) <= i:
        return None
    h, mi, ap = t[i]
    return datetime.strptime(f"{h}:{mi} {ap.upper()}", "%I:%M %p").strftime("%H:%M")


def rows(html: str) -> list[dict]:
    out = []
    for r in HTMLParser(html).css("div.views-row"):
        a = r.css_first("div.views-field-title a")
        start = _date(_field(r, "field-date"))
        if not a or not start:
            continue
        end = _date(_field(r, "field-end-date"))
        times = _field(r, "field-event-time")
        t0, t1 = _time(times, 0), _time(times, 1)
        address = _field(r, "field-address") or None
        pc = POSTCODE_RE.search(address or "")
        price = _field(r, "field-price") or _field(r, "field-free") or None
        out.append(dict(title=a.text(strip=True), url=urljoin(BASE, a.attributes.get("href")),
                        start=f"{start}T{t0}" if t0 else start,
                        end=f"{end or start}T{t1}" if t1 else end,
                        all_day=not t0, venue=_field(r, "field-museum") or None, address=address,
                        postcode=pc.group(0) if pc else None, price=price,
                        summary=_field(r, "field-description") or None))
    return out


class UniversityMuseums(Collector):
    source_id, name = "S052", "University of Cambridge Museums"

    def collect(self, http) -> list[RawEvent]:
        family: dict[str, set[str]] = {}
        for q, tag in FAMILY_FILTERS.items():
            for x in rows(http.get(f"{BASE}?{q}").text):
                family.setdefault(x["url"], set()).add(tag)
        seen, out = set(), []
        for x in rows(http.get(BASE).text):
            key = (x["url"], x["start"])
            if key in seen:
                continue
            seen.add(key)
            cats = sorted(family.get(x["url"], set()))
            out.append(self.event(external_id=f"{x['url']}#{x['start']}", categories=cats, **x))
        return out
