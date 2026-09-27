"""S021 Newmarket Racecourses: JSON-LD на странице событий."""

from ..generic import JsonLdListCollector


class Newmarket(JsonLdListCollector):
    source_id, name = "S021", "Newmarket Racecourses"
    pages = ['https://www.thejockeyclub.co.uk/newmarket/events-tickets/']
