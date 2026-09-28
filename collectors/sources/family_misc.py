"""Этап 6.2 — семейные источники с простой разметкой.

S055 Cambridgeshire Libraries — события библиотек публикуются на Eventbrite (страница организатора; ссылка — со
страницы библиотек совета): ссылки со страницы организатора, поля — из JSON-LD страницы события (как у S008).
S133 Nene Park (Ferry Meadows, Питерборо) — JSON-LD Event на странице /events/ (The Events Calendar).
S134 Centre for Computing History — дата и название в ссылке («/det/77445/International-E-Waste-Day-Saturday-17th-
October-2026/»), страница «What's On».
"""

from __future__ import annotations

import re
from datetime import date

from ..base import Collector
from ..generic import JsonLdDetailCollector, JsonLdListCollector
from ..htmlevents import find_when


class Libraries(JsonLdDetailCollector):
    """Большинство событий библиотек — регулярные серии (Rhymetime, Storytime, Lego Club): JSON-LD Eventbrite даёт
    начало и конец всей серии («2021 … декабрь 2026»), а не ближайшее занятие. Такие записи помечаются категорией
    «recurring series» — в выпуске это «регулярные занятия», а не событие на все эти даты."""

    source_id, name = "S055", "Cambridgeshire Libraries (Eventbrite)"
    list_url = "https://www.eventbrite.co.uk/o/cambridgeshire-libraries-33302830317"
    page_param = None
    link_re = r"https://www\.eventbrite\.co\.uk/e/[a-z0-9-]+-\d+"

    def collect(self, http):
        out = super().collect(http)
        for e in out:
            if e.start and e.end and e.end[:10] > e.start[:10] and e.start[:10] < date.today().isoformat():
                e.categories = list(dict.fromkeys(e.categories + ["recurring series"]))
        return out


class NenePark(JsonLdListCollector):
    source_id, name = "S133", "Nene Park (Ferry Meadows)"
    pages = ["https://www.nenepark.org.uk/events/"]
    page_param, max_pages = None, 1

    def collect(self, http):
        out = super().collect(http)
        for e in out:   # места внутри парка («Woodlands», «Lynch Farm») — с названием парка
            if e.venue and "nene park" not in e.venue.lower():
                e.venue = f"{e.venue}, Nene Park"
            e.address = e.address or "Nene Park, Peterborough"
        return out


class ComputingHistory(Collector):
    source_id, name = "S134", "Centre for Computing History"
    url = "https://www.computinghistory.org.uk/pages/30677/What-s-On/"

    def collect(self, http):
        out, seen = [], set()
        for link, slug in re.findall(r'href="(https://www\.computinghistory\.org\.uk/det/\d+/([^"/]+)/)"',
                                     http.get(self.url).text):
            if link in seen:
                continue
            seen.add(link)
            words = slug.replace("-", " ")
            when = find_when(words)
            if not when:
                continue
            m = re.search(r"\s(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s", words)
            title = words[:m.start()] if m else words
            out.append(self.event(title=title.strip(), url=link, external_id=link, start=when[0].isoformat(),
                                  all_day=True, venue="Centre for Computing History",
                                  address="Rene Court, Coldham's Road, Cambridge", postcode="CB1 3EW"))
        return out
