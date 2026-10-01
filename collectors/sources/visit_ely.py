"""S113 Visit Ely: /whats-on/ (JetEngine, постранично /page/N/): у карточки — название, иногда время, дата начала и
окончания («20 June 2026 – 11 October 2026»), ссылка. Площадка не указана — «Ely» (зона по населённому пункту)."""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from ..base import Collector
from ..htmlevents import find_when

LIST = "https://www.visitely.org.uk/whats-on/"


class VisitEly(Collector):
    source_id, name = "S113", "Visit Ely"
    max_pages = 30   # этап 7e: обход до пустой страницы; лимит — только предохранитель

    def collect(self, http):
        out, seen = [], set()
        for n in range(1, self.max_pages + 1):
            url = LIST if n == 1 else f"{LIST}page/{n}/"
            try:
                items = HTMLParser(http.get(url).text).css("div.jet-listing-grid__item")
            except Exception:
                break
            new = 0
            for it in items:
                a = it.css_first('a[href*="/whats-on/"]')
                f = [x.text(strip=True) for x in it.css(".jet-listing-dynamic-field__content")]
                if not a or not f:
                    continue
                link = a.attributes["href"]
                if link in seen:
                    continue
                seen.add(link)
                new += 1
                dates = [x for x in f[1:] if find_when(x)]
                if not dates:
                    continue
                start = find_when(dates[0])[0]
                end = find_when(dates[-1])[0] if len(dates) > 1 else None
                t = next((x for x in f[1:] if re.fullmatch(r"\d{1,2}:\d{2}", x)), None)
                out.append(self.event(title=f[0], url=link, external_id=link,
                                      start=f"{start.isoformat()}T{t}" if t else start.isoformat(),
                                      end=end.isoformat() if end and end != start else None, all_day=not t,
                                      venue=None, address="Ely"))
            if not new:
                break
        return out
