"""S007 Skiddle: JSON-LD на страницах списка (API-ключ не нужен)."""

from ..generic import JsonLdListCollector


class Skiddle(JsonLdListCollector):
    source_id, name = "S007", "Skiddle"
    pages = ['https://www.skiddle.com/whats-on/Cambridge/']
    # продолжение списка подгружается JS — доступна только первая страница
