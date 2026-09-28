"""Этап 6.5 — источники P3, которые дают новые события.

S022 Huntingdon Racecourse — JSON-LD на странице событий Jockey Club (как у Newmarket, S021).
S043 Mumford Theatre (ARU) — афиша на Eventbrite (страница организатора), поля — из JSON-LD страниц событий.
"""

from ..generic import JsonLdDetailCollector, JsonLdListCollector


class HuntingdonRacecourse(JsonLdListCollector):
    source_id, name = "S022", "Huntingdon Racecourse"
    pages = ["https://www.thejockeyclub.co.uk/huntingdon/events-tickets/"]


class MumfordTheatre(JsonLdDetailCollector):
    source_id, name = "S043", "Mumford Theatre (Eventbrite)"
    list_url = "https://www.eventbrite.co.uk/o/mumford-theatre-78024171593"
    page_param = None
    link_re = r"https://www\.eventbrite\.co\.uk/e/[a-z0-9-]+-\d+"
