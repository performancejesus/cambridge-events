"""S054 Cambridge Science Centre: ссылки на события — из RSS /whats-on/feed/ (страница афиши собирается скриптом),
дата и время — со страницы события («When | Everyday between 24th October – 25th October | Time | 9:00 am»).
Все события центра — семейные (научный центр для детей): категория family."""

import re

from ..htmlevents import HtmlDetailCollector


class ScienceCentre(HtmlDetailCollector):
    source_id, name = "S054", "Cambridge Science Centre"
    list_urls = ["https://www.cambridgesciencecentre.org/whats-on/feed/"]
    link_re = r"<link>(https://www\.cambridgesciencecentre\.org/whats-on/[a-z0-9-]+/)</link>"
    after = "When"
    venue, address, postcode = "Cambridge Science Centre", "Cambridge", "CB4 0FN"   # postcode — с сайта центра

    def category_of(self, list_url):
        return "family"
