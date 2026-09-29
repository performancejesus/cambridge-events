"""S042 ADC Theatre: афиша площадки в Camdram (JSON). Этап 6c (правки по v5): цена — со страницы продажи билетов
adctheatre.com (ссылка со страницы спектакля в Camdram), кэш страниц; описание — из Camdram."""

import re

from selectolax.parser import HTMLParser

from ..base import Collector, RawEvent
from ..generic import DetailCache
from ..http import PoliteClient

DIARY = "https://www.camdram.net/venues/adc-theatre/diary.json"
ADDRESS, POSTCODE = "Park Street, Cambridge CB5 8AS", "CB5 8AS"
PRICE_RE = re.compile(r"£\s?\d+(?:\.\d{2})?(?:\s*[-–]\s*£?\s?\d+(?:\.\d{2})?)?")


class AdcCamdram(DetailCache, Collector):
    source_id, name = "S042", "ADC Theatre (Camdram)"

    def parse_page(self, page: str, link: str) -> dict | None:
        """Страница спектакля в Camdram → ссылка на adctheatre.com → цены (все суммы со страницы продажи)."""
        tree = HTMLParser(page)
        desc = re.sub(r"\s+", " ", (tree.css_first("main") or tree.body).text(separator=" "))[:1500]
        adc = next((a.attributes.get("href") for a in tree.css("a[href]")
                    if "adctheatre.com/whats-on" in (a.attributes.get("href") or "")), None)
        price = None
        if adc and getattr(self, "_http", None):
            try:
                t = re.sub(r"\s+", " ", HTMLParser(self._http.get(adc).text).body.text(separator=" "))
                vals = sorted({float(x) for m in PRICE_RE.findall(t) for x in re.findall(r"\d+(?:\.\d{2})?", m)})
                if vals:
                    fmt = lambda v: f"£{v:g}" if v == int(v) else f"£{v:.2f}"
                    price = fmt(vals[0]) + (f" – {fmt(vals[-1])}" if len(vals) > 1 else "")
            except Exception:  # noqa: BLE001 — страница продажи недоступна: цена остаётся неизвестной
                pass
        return {"price": price, "ticket_url": adc, "summary": desc}

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        self._http = http
        self.start_details()
        out = []
        for p in http.get(DIARY).json().get("events", []):
            show = p.get("show") or {}
            url = f"https://www.camdram.net/shows/{show['slug']}" if show.get("slug") else None
            kw = self.detail(http, url) if url else None
            out.append(self.event(
                external_id=f"camdram-performance-{p['id']}", title=show.get("name") or "(без названия)",
                url=(kw or {}).get("ticket_url") or url,
                start=p.get("start_at"), end=p.get("repeat_until"),
                venue=(p.get("venue") or {}).get("name") or p.get("other_venue"),
                address=ADDRESS, postcode=POSTCODE, price=(kw or {}).get("price"),
                summary=" · ".join(x for x in (p.get("date_string"), (kw or {}).get("summary", "")[:600]) if x),
            ))
        return out
