"""S126 Theatre Royal Bury St Edmunds: список спектаклей — REST WordPress /wp-json/wp/v2/events (все опубликованные,
~30), дата и цена — со страницы спектакля («Wed 30 Sep 2026», «Fri 2 Oct - Sat 3 Oct 2026»). Ents24 (S128) даёт
только первую страницу листинга театра, поэтому — собственный коллектор (решение после этапа 5)."""

import json

from ..htmlevents import HtmlDetailCollector

API = "https://theatreroyal.org/wp-json/wp/v2/events?per_page=100&_fields=link,title"


class TheatreRoyalBury(HtmlDetailCollector):
    source_id, name = "S126", "Theatre Royal Bury St Edmunds"
    venue, address, postcode = "Theatre Royal", "Westgate Street, Bury St Edmunds", "IP33 1QR"

    def links(self, http):
        return {e["link"]: [] for e in json.loads(http.get(API).text) if e.get("link")}
