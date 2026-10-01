"""Сайты на The Events Calendar (REST /wp-json/tribe/events/v1/events): тот же разбор, что у Cambridge 105 (S005)."""

from ..base import Collector, RawEvent
from ..http import PoliteClient
from ..parsers import clean_text, find_postcode


class TribeEvents(Collector):
    api: str = ""
    max_pages: int = 30   # этап 7e: обход до пустой страницы; лимит — только предохранитель

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        out, url, n = [], f"{self.api}?per_page=50", 0
        while url and n < self.max_pages:
            data = http.get(url).json()
            n += 1
            for e in data.get("events", []):
                v = e.get("venue") if isinstance(e.get("venue"), dict) else {}
                address = ", ".join(x for x in (v.get("address"), v.get("city"), v.get("zip")) if x) or None
                out.append(self.event(
                    external_id=str(e["id"]), title=clean_text(e.get("title"), 200), url=e.get("url"),
                    start=(e.get("start_date") or "").replace(" ", "T") or None,
                    end=(e.get("end_date") or "").replace(" ", "T") or None, all_day=bool(e.get("all_day")),
                    venue=clean_text(v.get("venue"), 200) or self.name, address=address,
                    postcode=find_postcode(v.get("zip"), address), price=e.get("cost") or None,
                    categories=[c.get("name") for c in e.get("categories", []) if c.get("name")],
                    summary=clean_text(e.get("description"))))
            url = data.get("next_rest_url")
        return out


class MuseumOfCambridge(TribeEvents):
    source_id, name = "S130", "Museum of Cambridge"
    api = "https://www.museumofcambridge.org.uk/wp-json/tribe/events/v1/events"
