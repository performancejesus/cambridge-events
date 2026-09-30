"""S123 Peterborough United: домашние матчи из iCal fixtur.es (как S018 Cambridge United)."""

from ..generic import ICalCollector

FIXTURES = "https://www.theposh.com/matches/fixtures"   # этап 7c: /fixtures отвечает 404 (нашла проверка ссылок)


class PeterboroughUnited(ICalCollector):
    source_id, name = "S123", "Peterborough United (fixtur.es)"
    feeds = ["https://ics.fixtur.es/v2/home/peterborough-united-fc.ics"]

    def adjust(self, kw, feed_url):
        # Фид только домашних матчей: стадион London Road (postcode проверен через postcodes.io — Fletton, Peterborough).
        kw.update(venue="London Road Stadium (Peterborough United)", address="London Road, Peterborough PE2 8AL",
                  postcode="PE2 8AL", url=kw["url"] or FIXTURES, summary=None, categories=["football", "home"])
        return kw
