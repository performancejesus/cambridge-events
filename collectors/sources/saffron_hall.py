"""S017 Saffron Hall (Saffron Walden): карточки списка /whats-on?page=N&sort=date — дата, время, наличие билетов.

Наличие билетов из карточки: «Sold out» → sold_out, «Nearly full» / «Limited availability» → few_left (сигнал
«мало билетов» для оценки важности), «has been cancelled» → cancelled. JSON-LD на сайте нет. Адрес площадки — postcode
со страницы (подвал сайта), не из памяти.
"""

from __future__ import annotations

import re
from datetime import datetime

from selectolax.parser import HTMLParser

from ..base import Collector
from ..parsers import find_postcode

LIST = "https://www.saffronhall.com/whats-on?page={}&sort=date"
DATE_RE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day (\d{1,2} [A-Z][a-z]+ \d{4})(?:, (\d{1,2}(?:\.\d{2})?\s?[ap]m))?")


def _time(t: str | None) -> str | None:
    if not t:
        return None
    m = re.match(r"(\d{1,2})(?:\.(\d{2}))?\s?([ap]m)", t)
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    return f"{(h % 12) + (12 if ap == 'pm' else 0):02d}:{mi:02d}"


class SaffronHall(Collector):
    source_id, name = "S017", "Saffron Hall"
    max_pages = 30   # этап 7e: обход до пустой страницы; лимит — только предохранитель

    def collect(self, http):
        out, seen, postcode = [], set(), None
        for n in range(1, self.max_pages + 1):
            page = http.get(LIST.format(n)).text
            tree = HTMLParser(page)
            postcode = postcode or find_postcode(tree.body.text(separator=" ") if tree.body else "")
            new = 0
            for a in tree.css('a[href*="/whats-on/view/"]'):
                url = a.attributes["href"]
                if url in seen:
                    continue
                card = a
                for _ in range(5):  # ближайший предок с датой — карточка события
                    if card.parent is None or DATE_RE.search(card.text(separator=" | ")):
                        break
                    card = card.parent
                parts = [p.strip() for p in card.text(separator=" | ").split("|") if p.strip()]
                text = " | ".join(parts)
                m = DATE_RE.search(text)
                if not m:
                    continue
                seen.add(url)
                new += 1
                day = datetime.strptime(m.group(1), "%d %B %Y").date().isoformat()
                t = _time(m.group(2))
                after = parts[parts.index(next(p for p in parts if m.group(1) in p)) + 1:]
                title = next((p for p in after if p not in ("Saffron Hall",) and not re.search(
                    r"availability|full|sold out|seating|^Presented by", p, re.I)), url.rsplit("/", 1)[-1])
                low = text.lower()
                status = ("cancelled" if "has been cancelled" in low else "sold_out" if "sold out" in low
                          else "few_left" if re.search(r"nearly full|limited availability|few (seats|tickets)", low)
                          else "scheduled")
                presenter = next((p[len("Presented by "):] for p in after if p.startswith("Presented by ")), None)
                out.append(self.event(title=title, url=url, external_id=url, start=f"{day}T{t}" if t else day,
                                      all_day=not t, venue="Saffron Hall", address="Saffron Walden",
                                      postcode=postcode, status=status, organizer=presenter,
                                      summary=" ".join(after[1:4])[:300] or None))
            if not new:
                break
        return out
