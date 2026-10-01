"""S008 Eventbrite: JSON-LD на страницах поиска по Кембриджу; фильтр — Кембридж и окрестности.

В списке нет цены — она берётся из JSON-LD страницы события (offers.lowPrice); страницы кэшируются (DetailCache).
"""

from ..base import RawEvent
from ..generic import DetailCache, JsonLdListCollector
from ..http import PoliteClient

# Почтовые области в пределах ~1 часа от Кембриджа.
NEAR_AREAS = {"CB", "PE", "SG", "CM", "IP"}


class Eventbrite(DetailCache, JsonLdListCollector):
    source_id, name = "S008", "Eventbrite"
    pages = ["https://www.eventbrite.co.uk/d/united-kingdom--cambridge/all-events/"]
    page_param, max_pages = "page", 20   # этап 7e: до первой страницы без новых событий (было 5)

    def keep(self, kw):
        pc = kw.get("postcode")
        if pc:
            return pc.split()[0].rstrip("0123456789") in NEAR_AREAS
        return "cambridge" in (kw.get("address") or "").lower()  # онлайн и без адреса — отбрасываем

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        events = super().collect(http)
        self.start_details()
        for ev in events:
            kw = self.detail(http, ev.url) if ev.url else None
            if kw:
                ev.price = ev.price or kw.get("price")
                ev.status = kw.get("status") or ev.status
        return events
