"""S071 Ely Cathedral: карточки на /events («1 October 2026 | Lunchtime Recital - English Piano Trio»), без страниц
событий (время — на странице бронирования). Отложен в P2 на этапе 5, подключён в блоке «церкви» этапа 6."""

from __future__ import annotations

from datetime import datetime

from selectolax.parser import HTMLParser

from ..base import Collector
from ..htmlevents import find_when

LIST = "https://www.elycathedral.org/events"


class ElyCathedral(Collector):
    source_id, name = "S071", "Ely Cathedral"

    def collect(self, http):
        out = []
        for a in HTMLParser(http.get(LIST).text).css("a.listing"):
            d, t = a.css_first(".listing__date"), a.css_first(".listing__title")
            when = find_when(d.text(strip=True)) if d else None
            if not when or not t:
                continue
            url = a.attributes.get("href")
            out.append(self.event(title=t.text(strip=True), url=url, external_id=url, start=when[0].isoformat(),
                                  end=when[1].isoformat() if when[1] else None, all_day=True, venue="Ely Cathedral",
                                  address="The College, Ely", postcode="CB7 4DL"))
        return out
