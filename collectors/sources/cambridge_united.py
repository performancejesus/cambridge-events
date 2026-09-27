"""S018 Cambridge United: домашние матчи из iCal fixtur.es (сверять с сайтом клуба)."""

from ..generic import ICalCollector

FIXTURES = "https://www.cambridgeunited.com/fixture/list/57"


class CambridgeUnited(ICalCollector):
    source_id, name = "S018", "Cambridge United (fixtur.es)"
    feeds = ["https://ics.fixtur.es/v2/home/cambridge-united-fc.ics"]

    def adjust(self, kw, feed_url):
        # Фид только домашних матчей: площадка одна; описание — служебный текст fixtur.es.
        kw.update(venue="Abbey Stadium", address="Newmarket Road, Cambridge CB5 8LN", postcode="CB5 8LN",
                  url=kw["url"] or FIXTURES, summary=None, categories=["football", "home"])
        return kw
