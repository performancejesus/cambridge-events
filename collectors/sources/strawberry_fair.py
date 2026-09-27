"""S033 Strawberry Fair: JSON-LD Event на главной (ежегодно)."""

from ..generic import JsonLdListCollector


class StrawberryFair(JsonLdListCollector):
    source_id, name = "S033", "Strawberry Fair"
    pages = ['https://strawberry-fair.org.uk/']
