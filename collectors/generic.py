"""Типовые коллекторы, от которых наследуются модули источников."""

from __future__ import annotations

import re
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


class JsonLdDetailCollector(Collector):
    """Ссылки на события собираются со страниц списка, JSON-LD берётся со страницы каждого события."""

    list_url: str = ""
    page_param: str | None = "page"
    max_pages: int = 10
    link_re: str = ""          # регулярка для ссылок на страницы событий
    max_events: int = 250

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
        self.stats = {"links": len(links), "fetch_errors": 0, "no_jsonld": 0}
        for link in links[: self.max_events]:
            try:
                found = jsonld_events(http.get(link).text)
            except (FetchError, Disallowed):
                self.stats["fetch_errors"] += 1
                continue
            if not found:
                self.stats["no_jsonld"] += 1
            for kw in found[:1]:  # первое событие страницы — само событие; остальное — «похожие»
                kw["url"] = kw.get("url") or link
                kw["external_id"] = link
                out.append(self.event(**kw))
        return out
