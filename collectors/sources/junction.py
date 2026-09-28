"""S012 Cambridge Junction: список /whats-on/ (постранично), дата, время и цена — со страницы события
(блок «Event Information»: «Date Thu 1st Oct 2026 … Time Doors 7pm Price £40.50»). JSON-LD событий на сайте нет."""

from ..htmlevents import HtmlDetailCollector


class Junction(HtmlDetailCollector):
    source_id, name = "S012", "Cambridge Junction"
    list_urls = ["https://www.junction.co.uk/whats-on/"]
    page_fmt = "{base}/page/{n}/"
    max_pages = 15
    link_re = r'href="(https://www\.junction\.co\.uk/events/[a-z0-9-]+/)"'
    after = "Event Information"
    venue, address, postcode = "Cambridge Junction", "Clifton Way, Cambridge", "CB1 7GX"
