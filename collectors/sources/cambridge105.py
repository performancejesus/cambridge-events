"""S005 Cambridge 105: REST The Events Calendar (+ новости из /feed/ — для событий, которых нет в афише)."""

from ..base import Collector, RawEvent
from ..http import PoliteClient
from ..parsers import clean_text, feed_items, find_postcode

API = "https://cambridge105.co.uk/wp-json/tribe/events/v1/events?per_page=50"
NEWS = "https://cambridge105.co.uk/feed/"


class Cambridge105(Collector):
    source_id, name = "S005", "Cambridge 105"

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        out, url = [], API
        while url:
            data = http.get(url).json()
            for e in data.get("events", []):
                v = e.get("venue") if isinstance(e.get("venue"), dict) else {}
                address = ", ".join(x for x in (v.get("address"), v.get("city"), v.get("zip")) if x) or None
                out.append(self.event(
                    external_id=str(e["id"]), title=clean_text(e.get("title"), 200), url=e.get("url"),
                    start=_iso(e.get("start_date")), end=_iso(e.get("end_date")), all_day=bool(e.get("all_day")),
                    venue=clean_text(v.get("venue"), 200), address=address,
                    postcode=find_postcode(v.get("zip"), address),
                    lat=_f(v.get("geo_lat")), lon=_f(v.get("geo_lng")),
                    price=e.get("cost") or None,
                    organizer=clean_text((e.get("organizer") or [{}])[0].get("organizer"), 200) if e.get("organizer") else None,
                    categories=[c.get("name") for c in e.get("categories", []) if c.get("name")],
                    summary=clean_text(e.get("description")),
                ))
            url = data.get("next_rest_url")
        out += [self.event(**kw) for kw in feed_items(http.get(NEWS).content)]
        return out


def _iso(s):
    return s.replace(" ", "T") if s else None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
