"""S131 Cambridge Past, Present & Future (CPPF): события Wandlebury, Leper Chapel (Stourbridge Fair), Hinxton Watermill,
Coton, Bourn Windmill, Grantchester Meadows. Страница /events-list/ (плагин Eventin): у каждого события — место
(категория), дата «September 30, 2026», название и начало описания со временем («Wednesday 30 Sep, 8pm – 9.30pm»)."""

from __future__ import annotations

import re
from datetime import datetime

from selectolax.parser import HTMLParser

from ..base import Collector
from ..htmlevents import TIME_RE

LIST = "https://cambridgeppf.org/events-list/"
PLACES = {  # адреса мест CPPF (известные postcode — из справочника площадок)
    "Leper Chapel": ("Leper Chapel", "Newmarket Road, Cambridge", "CB5 8JJ"),
    "Wandlebury": ("Wandlebury Country Park", "Wandlebury Ring, Babraham Road, Cambridge", "CB22 3AE"),
    "Hinxton Watermill": ("Hinxton Watermill", "Mill Lane, Hinxton", None),
    "Coton": ("Coton Countryside Reserve", "Coton, Cambridge", None),
    "Bourn Windmill": ("Bourn Windmill", "Bourn", None),
    "Grantchester": ("Grantchester Meadows", "Grantchester Meadows, Cambridge", None),
}


class CambridgePPF(Collector):
    source_id, name = "S131", "Cambridge Past, Present & Future"

    def collect(self, http):
        out, seen = [], set()
        for item in HTMLParser(http.get(LIST).text).css("div.etn-event-item"):
            a = item.css_first(".etn-event-title a")
            d = item.css_first(".etn-event-date")
            if not a or not d:
                continue
            url = a.attributes.get("href")
            try:
                day = datetime.strptime(d.text(strip=True), "%B %d, %Y").date()
            except ValueError:
                continue
            if (url, day) in seen:
                continue
            seen.add((url, day))
            cat = (item.css_first(".etn-event-category") or item).text(strip=True)
            place = next((v for k, v in PLACES.items() if k.lower() in cat.lower()), (cat or None, None, None))
            desc = (item.css_first("p") or item).text(strip=True)
            tm = TIME_RE.search(desc[:60])
            t = None
            if tm and tm.group(3):
                t = f"{int(tm.group(1)) % 12 + (12 if tm.group(3).lower() == 'p' else 0):02d}:{int(tm.group(2) or 0):02d}"
            out.append(self.event(title=a.text(strip=True).rstrip(":"), url=url, external_id=f"{url}#{day}",
                                  start=f"{day.isoformat()}T{t}" if t else day.isoformat(), all_day=not t,
                                  venue=place[0], address=place[1], postcode=place[2], categories=[cat] if cat else [],
                                  summary=desc or None))
        return out
