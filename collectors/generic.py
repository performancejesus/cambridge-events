"""Типовые коллекторы, от которых наследуются модули источников."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from .base import Collector, RawEvent
from .http import Disallowed, FetchError, PoliteClient
from .parsers import feed_items, ical_events, jsonld_events


class ICalCollector(Collector):
    feeds: list[str] = []

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        seen: dict = {}
        for url in self.feeds:
            for kw in ical_events(http.get(url).content):
                kw = self.adjust(kw, url)
                key = kw["external_id"] or (kw["title"], kw["start"])
                if key in seen:  # то же событие в другом фиде — дописываем его категории
                    ev = seen[key]
                    ev.categories += [c for c in kw["categories"] if c not in ev.categories]
                else:
                    seen[key] = self.event(**kw)
        return list(seen.values())

    def adjust(self, kw: dict, feed_url: str) -> dict:
        return kw


class FeedCollector(Collector):
    feeds: list[str] = []

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        seen, out = set(), []
        for url in self.feeds:
            for kw in feed_items(http.get(url).content):
                if kw["external_id"] not in seen:
                    seen.add(kw["external_id"])
                    out.append(self.event(**kw))
        return out


class JsonLdListCollector(Collector):
    """События из JSON-LD на страницах списка; страницы перебираются, пока появляются новые события."""

    pages: list[str] = []      # первая страница или явный список страниц
    page_param: str | None = None  # напр. "page" → ?page=2, 3…
    max_pages: int = 1

    def page_urls(self):
        yield from self.pages
        if self.page_param:
            base = self.pages[0]
            sep = "&" if "?" in base else "?"
            for n in range(2, self.max_pages + 1):
                yield f"{base}{sep}{self.page_param}={n}"

    def keep(self, kw: dict) -> bool:
        return True

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        seen, out = set(), []
        for i, url in enumerate(self.page_urls()):
            try:
                found = jsonld_events(http.get(url).text)
            except (FetchError, Disallowed):
                if i == 0:
                    raise
                break
            new = [kw for kw in found if (kw["url"] or kw["title"], kw["start"]) not in seen]
            if not new:
                break
            for kw in new:
                seen.add((kw["url"] or kw["title"], kw["start"]))
                kw["url"] = kw["url"] or url  # нет ссылки на событие — ссылка на страницу, где оно найдено
                if self.keep(kw):
                    out.append(self.event(**kw))
        return out


PAGE_PRICE_RE = re.compile(r"£\s?\d+(?:\.\d{2})?(?:\s*[-–]\s*£\s?\d+(?:\.\d{2})?)?")


def page_price(page_html: str) -> str | None:
    """Цена текстом со страницы события («£38.50 - £71.50»), если в JSON-LD её нет."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page_html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    m = PAGE_PRICE_RE.search(text)
    if m:
        return m.group(0)
    return "Free" if re.search(r"\bfree (entry|admission|event)\b", text, re.I) else None


class DetailCache:
    """Страницы событий с кэшем: cache (url → (fetched_at, поля)) заполняет и сохраняет вызывающий код."""

    refresh_days: int = 7

    def start_details(self) -> None:
        self.fresh_pages: dict[str, dict | None] = {}
        self._fresh_after = (datetime.now(timezone.utc) - timedelta(days=self.refresh_days)).isoformat()
        self.stats = {"links": 0, "cached": 0, "fetched": 0, "fetch_errors": 0, "no_jsonld": 0}

    def detail(self, http: PoliteClient, link: str) -> dict | None:
        """Поля события со страницы (JSON-LD + цена текстом); None — страница недоступна или без JSON-LD."""
        self.stats["links"] += 1
        cache = getattr(self, "cache", {})
        if link in self.fresh_pages:   # уже запрошена в этом прогоне
            self.stats["cached"] += 1
            kw = self.fresh_pages[link]
        elif link in cache and cache[link][0] >= self._fresh_after:
            self.stats["cached"] += 1
            kw = cache[link][1]
        else:
            try:
                page = http.get(link).text
            except (FetchError, Disallowed):
                self.stats["fetch_errors"] += 1
                return None
            self.stats["fetched"] += 1
            kw = self.parse_page(page, link)
            self.fresh_pages[link] = kw
        if not kw:
            self.stats["no_jsonld"] += 1
        return kw


    def parse_page(self, page: str, link: str) -> dict | None:
        """Поля события со страницы: по умолчанию JSON-LD (+ цена текстом). HTML-коллекторы переопределяют."""
        found = jsonld_events(page)
        kw = found[0] if found else None  # первое событие страницы — само событие; остальное — «похожие»
        if kw and not kw.get("price"):
            kw["price"] = page_price(page)
        return kw


class JsonLdDetailCollector(DetailCache, Collector):
    """Ссылки на события собираются со страниц списка, JSON-LD берётся со страницы каждого события.

    Инкрементальный режим — см. DetailCache: свежие страницы (моложе refresh_days) повторно не запрашиваются.
    """

    list_url: str = ""
    page_param: str | None = "page"
    max_pages: int = 10
    link_re: str = ""          # регулярка для ссылок на страницы событий
    max_events: int = 600   # этап 7e: предохранитель, а не окно (было 250)

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        links: list[str] = []
        for n in range(1, self.max_pages + 1):
            url = self.list_url if n == 1 else f"{self.list_url}{'&' if '?' in self.list_url else '?'}{self.page_param}={n}"
            try:
                page = http.get(url).text
            except FetchError:
                if n == 1:
                    raise
                break
            new = [urljoin(url, m) for m in dict.fromkeys(re.findall(self.link_re, page))]
            new = [u for u in new if u not in links]
            if not new:
                break
            links += new
            if not self.page_param:
                break
        out = []
        self.start_details()
        for link in links[: self.max_events]:
            kw = self.detail(http, link)
            if kw:
                out.append(self.event(**dict(kw, url=kw.get("url") or link, external_id=link)))
        return out


class StoreListCollector(Collector):
    """Список арендаторов ТЦ со страницы /stores/: одна запись kind="store" на магазин."""

    list_url: str = ""
    link_re: str = ""   # группа 1 — URL страницы магазина
    centre: str = ""
    address: str = ""

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        page = http.get(self.list_url).text
        names: dict[str, str] = {}
        for m in re.finditer(self.link_re, page):
            url, tail = m.group(1), m.group(0)
            dn = re.search(r'data-name="([^"]+)"', tail)
            text = re.sub(r"\s+", " ", m.group(2) if m.lastindex and m.lastindex >= 2 else "").strip()
            name = (dn.group(1) if dn else text) or names.get(url, "")
            if url not in names or (name and not names[url]):
                names[url] = name
        out = []
        for url, name in names.items():
            name = html.unescape(name) or url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
            out.append(self.event(kind="store", title=name, url=url, external_id=url, venue=self.centre,
                                  address=self.address))
        return out


class TownPagesJsonLd(JsonLdListCollector):
    """Страницы агрегатора по городам зоны: все страницы обходятся независимо (пустая страница города — не конец
    списка, недоступная — пропускается). stats — событий по городу."""

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        seen, out = set(), []
        self.stats = {}
        for url in self.pages:
            try:
                found = jsonld_events(http.get(url).text)
            except (FetchError, Disallowed) as e:
                self.stats[url] = f"ошибка: {e}"[:80]
                continue
            n = 0
            for kw in found:
                key = (kw["url"] or kw["title"], kw["start"])
                if key in seen:
                    continue
                seen.add(key)
                kw["url"] = kw["url"] or url
                if self.keep(kw):
                    out.append(self.event(**kw))
                    n += 1
            self.stats[url] = n
        return out
