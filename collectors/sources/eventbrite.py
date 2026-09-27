"""S008 Eventbrite: JSON-LD на страницах поиска по Кембриджу; фильтр — Кембридж и окрестности."""

from ..generic import JsonLdListCollector

# Почтовые области в пределах ~1 часа от Кембриджа.
NEAR_AREAS = {"CB", "PE", "SG", "CM", "IP"}


class Eventbrite(JsonLdListCollector):
    source_id, name = "S008", "Eventbrite"
    pages = ["https://www.eventbrite.co.uk/d/united-kingdom--cambridge/all-events/"]
    page_param, max_pages = "page", 5

    def keep(self, kw):
        pc = kw.get("postcode")
        if pc:
            return pc.split()[0].rstrip("0123456789") in NEAR_AREAS
        return "cambridge" in (kw.get("address") or "").lower()  # онлайн и без адреса — отбрасываем
