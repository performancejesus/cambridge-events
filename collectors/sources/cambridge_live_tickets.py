"""S091 Cambridge Live Tickets: билетный сайт Cambridge Live (Corn Exchange, Guildhall, городские события)."""

from ..generic import JsonLdDetailCollector


class CambridgeLiveTickets(JsonLdDetailCollector):
    source_id, name = "S091", "Cambridge Live Tickets"
    list_url = "https://www.cambridgelivetickets.co.uk/events"
    link_re = r'href="(https://www\.cambridgelivetickets\.co\.uk/events/[a-z0-9-]+)"'
