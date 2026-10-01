"""S069 Cambridge University Botanic Garden: /whats-on/ (постранично), дата — со страницы события («Event details
Sunday 18 October 2026 10am - 4pm»). Часть событий есть и в сводной афише музеев (S052) — склеит дедупликация."""

from ..htmlevents import HtmlDetailCollector


class BotanicGarden(HtmlDetailCollector):
    source_id, name = "S069", "Cambridge University Botanic Garden"
    list_urls = ["https://www.botanic.cam.ac.uk/whats-on/"]
    page_fmt = "{base}/page/{n}/"
    max_pages = 30   # этап 7e: обход до пустой страницы; лимит — только предохранитель
    link_re = r'href="(https://www\.botanic\.cam\.ac\.uk/whats-on/(?!page/)[a-z0-9-]+/)"'
    after = "Event details"
    venue, address, postcode = "Cambridge University Botanic Garden", "1 Brookside, Cambridge", "CB2 1JE"
