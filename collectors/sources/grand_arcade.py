"""S094 Grand Arcade: список магазинов (новые арендаторы — по сравнению с прошлым прогоном)."""

from ..generic import StoreListCollector


class GrandArcade(StoreListCollector):
    source_id, name = "S094", "Grand Arcade — магазины"
    list_url = "https://www.grandarcade.co.uk/stores/"
    link_re = r'<a href="(https://www\.grandarcade\.co\.uk/stores/[a-z0-9-]+/)"[^>]*>([^<]*)'
    centre, address = "Grand Arcade", "Grand Arcade, St Andrew's Street, Cambridge CB2 3BJ"
