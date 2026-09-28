"""HTML-страницы событий без JSON-LD: дата, время и цена берутся из текста страницы.

find_when — первая дата с годом или без («Thu 1st Oct 2026», «Sunday 18 October 2026 10am - 4pm»,
«18th October 2026 - 18th October 2026 10:00 am - 4:00 pm», «Fri 25 September - Thu 12 November»); год не указан —
ближайший будущий. HtmlDetailCollector — ссылки со страниц списка + разбор страницы события, с тем же
инкрементальным кэшем, что у JSON-LD-коллекторов (DetailCache).
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from .base import Collector, RawEvent
from .generic import DetailCache, page_price
from .http import FetchError, PoliteClient

_MON = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_WD = r"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+)?"
DATE = rf"{_WD}(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON}(?:,?\s+(20\d\d))?"
RANGE_RE = re.compile(rf"{DATE}(?:\s*(?:-|–|—|to|until)\s*{DATE})?", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?m\b|\b([01]?\d|2[0-3]):([0-5]\d)\b", re.I)
PRICE_FIELD_RE = re.compile(r"\bPrice\s*\|?\s*£\s*(\d+(?:\.\d{2})?(?:\s*[-–]\s*£?\s*\d+(?:\.\d{2})?)?)", re.I)
POSTCODE_RE = re.compile(r"\b(CB|PE|SG|IP|CO|CM|MK|NR|LU)\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b")


def _mk(day: str, mon: str, year: str | None, today: date) -> date | None:
    try:
        d = datetime.strptime(f"{int(day)} {mon[:3].title()} {year or today.year}", "%d %b %Y").date()
    except ValueError:
        return None
    if not year and d < today - timedelta(days=60):   # «25 September» в сентябре — этот год; в январе — следующий
        d = d.replace(year=d.year + 1)
    return d


def find_when(text: str, today: date | None = None) -> tuple[date, date | None, str | None] | None:
    """(начало, конец или None, время HH:MM или None) — по первой дате в тексте."""
    today = today or date.today()
    text = re.sub(r"\s+", " ", text)
    m = RANGE_RE.search(text)
    if not m:
        return None
    d1, mon1, y1, d2, mon2, y2 = m.groups()
    end = _mk(d2, mon2, y2, today) if d2 else None
    if end and not y1:   # диапазон без года у начала: год начала — от окончания («21 April – 5 December»)
        start = _mk(d1, mon1, str(end.year), today)
        if start and start > end:
            start = start.replace(year=start.year - 1)
    else:
        start = _mk(d1, mon1, y1, today)
    if not start:
        return None
    if end and end < start:
        end = end.replace(year=end.year + 1)
    tm = TIME_RE.search(text[m.end():m.end() + 80])
    t = None
    if tm:
        if tm.group(3):
            h = int(tm.group(1)) % 12 + (12 if tm.group(3).lower() == "p" else 0)
            t = f"{h:02d}:{int(tm.group(2) or 0):02d}"
        else:
            t = f"{int(tm.group(4)):02d}:{tm.group(5)}"
    return start, (end if end and end != start else None), t


def page_text(node) -> str:
    if not node:
        return ""
    return re.sub(r"(?:\s*\|\s*)+", " | ", re.sub(r"\s+", " ", node.text(separator=" | ", strip=True)))


def meta(tree: HTMLParser, prop: str) -> str | None:
    n = tree.css_first(f'meta[property="{prop}"]') or tree.css_first(f'meta[name="{prop}"]')
    return html.unescape(n.attributes.get("content") or "").strip() or None if n else None


class HtmlDetailCollector(DetailCache, Collector):
    """list_urls — страницы списка (page_fmt с {n} — постраничный обход до max_pages или первой пустой страницы);
    link_re — группа 1 = ссылка на событие; after — текст, после которого на странице искать дату (блок «Event
    details»); venue/address/postcode — площадка по умолчанию. parse() можно переопределить."""

    list_urls: list[str] = []
    page_fmt: str | None = None
    max_pages: int = 1
    link_re: str = ""
    skip_re: str | None = None
    after: str | None = None
    venue: str | None = None
    address: str | None = None
    postcode: str | None = None
    max_events: int = 300

    def links(self, http: PoliteClient) -> dict[str, list[str]]:
        """Ссылка → категории (по странице списка, где она найдена)."""
        found: dict[str, list[str]] = {}
        for base in self.list_urls:
            cat = self.category_of(base)
            for n in range(1, self.max_pages + 1):
                url = base if n == 1 or not self.page_fmt else self.page_fmt.format(base=base.rstrip("/"), n=n)
                try:
                    page = http.get(url).text
                except FetchError:
                    if n == 1 and base == self.list_urls[0]:
                        raise
                    break
                new = [urljoin(url, x) for x in dict.fromkeys(re.findall(self.link_re, page))]
                new = [x for x in new if not (self.skip_re and re.search(self.skip_re, x))]
                fresh = [x for x in new if x not in found]
                for x in new:
                    found.setdefault(x, [])
                    if cat and cat not in found[x]:
                        found[x].append(cat)
                if not fresh or not self.page_fmt:
                    break
        return found

    def category_of(self, list_url: str) -> str | None:
        return None

    def parse_page(self, page: str, link: str) -> dict | None:
        tree = HTMLParser(page)
        main = tree.css_first("main") or tree.body
        text = page_text(main)
        if self.after and self.after in text:
            scope = text[text.index(self.after):]
        else:
            scope = text
        when = find_when(scope)
        if not when:
            return None
        start, end, t = when
        h1 = tree.css_first("h1")
        title = h1.text(strip=True) if h1 else meta(tree, "og:title")
        if not title:
            return None
        pc = POSTCODE_RE.search(scope)
        # цена из поля «Price» блока события («Price | £ 29.50»); page_price по всей странице цепляет посторонние
        # суммы (у Junction — «save £4.50 per ticket» из рекламы членства), поэтому он — только запасной вариант
        pm = PRICE_FIELD_RE.search(scope)
        nums = re.findall(r"\d+(?:\.\d{2})?", pm.group(1)) if pm else []
        price = (f"£{nums[0]}" + (f" – £{nums[1]}" if len(nums) > 1 else "")) if nums else page_price(page)
        return dict(title=title, start=f"{start.isoformat()}T{t}" if t else start.isoformat(),
                    end=end.isoformat() if end else None, all_day=not t, venue=self.venue, address=self.address,
                    postcode=self.postcode or (pc.group(0) if pc else None), price=price,
                    summary=(meta(tree, "og:description") or meta(tree, "description") or "")[:500] or None)

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        links = self.links(http)
        self.start_details()
        out = []
        for link, cats in list(links.items())[: self.max_events]:
            kw = self.detail(http, link)
            if not kw:
                continue
            last = (kw.get("end") or kw["start"])[:10]
            if last >= date.today().isoformat():   # прошедшие (страницы архива) не нужны
                out.append(self.event(**dict(kw, url=link, external_id=link, categories=cats)))
        return out
