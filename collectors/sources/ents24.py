"""S006 Ents24: JSON-LD на страницах списка (сюда же попадает Arts Theatre)."""

from ..generic import JsonLdListCollector


class Ents24(JsonLdListCollector):
    source_id, name = "S006", "Ents24"
    pages = ['https://www.ents24.com/whatson/cambridge']
    # продолжение списка подгружается JS — доступна только первая страница
