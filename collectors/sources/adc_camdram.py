"""S042 ADC Theatre: афиша площадки в Camdram (JSON)."""

from ..base import Collector, RawEvent
from ..http import PoliteClient

DIARY = "https://www.camdram.net/venues/adc-theatre/diary.json"
ADDRESS, POSTCODE = "Park Street, Cambridge CB5 8AS", "CB5 8AS"


class AdcCamdram(Collector):
    source_id, name = "S042", "ADC Theatre (Camdram)"

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        out = []
        for p in http.get(DIARY).json().get("events", []):
            show = p.get("show") or {}
            out.append(self.event(
                external_id=f"camdram-performance-{p['id']}", title=show.get("name") or "(без названия)",
                url=f"https://www.camdram.net/shows/{show['slug']}" if show.get("slug") else None,
                start=p.get("start_at"), end=p.get("repeat_until"),
                venue=(p.get("venue") or {}).get("name") or p.get("other_venue"),
                address=ADDRESS, postcode=POSTCODE, summary=p.get("date_string"),
            ))
        return out
