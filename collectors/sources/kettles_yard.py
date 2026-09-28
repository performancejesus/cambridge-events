"""S051 Kettle's Yard: ссылки со страницы /whats-on/, дата и время — со страницы события («Thursday 22 October, 8pm»;
год не указан — ближайший будущий). Выставки — диапазон «D Month YYYY – D Month YYYY». JSON-LD на сайте нет."""

from __future__ import annotations

import re
from datetime import date, datetime

from selectolax.parser import HTMLParser

from ..base import Collector
from ..http import Disallowed, FetchError

LIST = "https://www.kettlesyard.cam.ac.uk/whats-on/"
LINK_RE = re.compile(r'href="(https://www\.kettlesyard\.cam\.ac\.uk/whats-on/(?!types/)[a-z0-9-]+/?)"')
DAY_RE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day (\d{1,2} [A-Z][a-z]+)(?: (\d{4}))?"
                    r"(?:,\s*(\d{1,2}(?:[.:]\d{2})?\s?[ap]m))?")
RANGE_RE = re.compile(r"(\d{1,2} [A-Z][a-z]+(?: \d{4})?)\s*[–-]\s*(\d{1,2} [A-Z][a-z]+ \d{4})")
SKIP_RE = re.compile(r"subscription|gift|membership|friends", re.I)


def _date(dm: str, year: str | None, today: date) -> date:
    if year:
        return datetime.strptime(f"{dm} {year}", "%d %B %Y").date()
    d = datetime.strptime(f"{dm} {today.year}", "%d %B %Y").date()
    return d if d >= today else d.replace(year=today.year + 1)


def _time(t: str | None) -> str | None:
    if not t:
        return None
    m = re.match(r"(\d{1,2})(?:[.:](\d{2}))?\s?([ap]m)", t)
    return f"{(int(m.group(1)) % 12) + (12 if m.group(3) == 'pm' else 0):02d}:{int(m.group(2) or 0):02d}"


class KettlesYard(Collector):
    source_id, name = "S051", "Kettle's Yard"

    def collect(self, http):
        today = date.today()
        links = list(dict.fromkeys(u.rstrip("/") + "/" for u in LINK_RE.findall(http.get(LIST).text)))
        out = []
        for url in links:
            if SKIP_RE.search(url):
                continue
            try:
                tree = HTMLParser(http.get(url).text)
            except (FetchError, Disallowed):
                continue
            main = tree.css_first("main") or tree.body
            h1 = tree.css_first("h1")
            title = h1.text(strip=True) if h1 else url.rstrip("/").rsplit("/", 1)[-1]
            text = main.text(separator=" | ", strip=True) if main else ""
            rng = RANGE_RE.search(text)
            m = DAY_RE.search(text)
            if rng and (not m or rng.start() < m.start()):
                end = datetime.strptime(rng.group(2), "%d %B %Y").date()
                y = rng.group(1).split()[-1] if re.search(r"\d{4}$", rng.group(1)) else str(end.year)
                start = datetime.strptime(" ".join(rng.group(1).split()[:2]) + f" {y}", "%d %B %Y").date()
                out.append(self.event(title=title, url=url, external_id=url, start=start.isoformat(),
                                      end=end.isoformat(), all_day=True, venue="Kettle's Yard",
                                      address="Castle Street, Cambridge", categories=["exhibition"]))
            elif m:
                d = _date(m.group(1), m.group(2), today)
                t = _time(m.group(3))
                out.append(self.event(title=title, url=url, external_id=url,
                                      start=f"{d.isoformat()}T{t}" if t else d.isoformat(), all_day=not t,
                                      venue="Kettle's Yard", address="Castle Street, Cambridge",
                                      price="Free" if re.search(r"\bfree\b", text[:2000], re.I) else None,
                                      summary=text[m.end():m.end() + 300] or None))
        return out
