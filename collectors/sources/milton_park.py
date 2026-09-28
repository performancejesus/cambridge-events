"""S132 Milton Country Park (Wix): список /events — «Название | Fri 23 Oct | Milton Country Park | … Details»;
ссылка на событие — /event-details/<slug>. Год не указан — ближайший будущий."""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from ..base import Collector
from ..htmlevents import find_when

LIST = "https://www.miltoncountrypark.org/events"


class MiltonCountryPark(Collector):
    source_id, name = "S132", "Milton Country Park"

    def collect(self, http):
        page = http.get(LIST).text
        tree = HTMLParser(page)
        links = list(dict.fromkeys(re.findall(r'href="(https://www\.miltoncountrypark\.org/event-details/[^"]+)"', page)))
        text = re.sub(r"\s+", " ", (tree.body or tree.root).text(separator=" | ", strip=True))
        part = text.split("Upcoming Events", 1)[-1]
        out = []
        for m in re.finditer(r"([^|]{4,120}?) \| ((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2}(?: \d{4})?)"
                             r"(?: \|[^|]*)? \| Milton Country Park", part):
            title, when = m.group(1).strip(), find_when(m.group(2))
            if not when or title in ("Multiple Dates", "Details", "More info"):
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            url = next((u for u in links if slug[:20] in u), LIST)
            out.append(self.event(title=title, url=url, external_id=f"{slug}#{when[0]}", start=when[0].isoformat(),
                                  all_day=True, venue="Milton Country Park", address="Cambridge Road, Milton, Cambridge",
                                  postcode="CB24 6AZ"))
        return out
