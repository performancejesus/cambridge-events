"""S011 Cambridge Corn Exchange: список в HTML, JSON-LD Event (с postcode) на странице события."""

from ..generic import JsonLdDetailCollector


class CornExchange(JsonLdDetailCollector):
    source_id, name = "S011", "Cambridge Corn Exchange"
    list_url = "https://www.cornex.co.uk/events"
    link_re = r'href="(https://www\.cornex\.co\.uk/events/[a-z0-9-]+)"'
