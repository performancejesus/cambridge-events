"""S095 Lion Yard: список магазинов (новые арендаторы — по сравнению с прошлым прогоном)."""

from ..generic import StoreListCollector


class LionYard(StoreListCollector):
    source_id, name = "S095", "Lion Yard — магазины"
    list_url = "https://www.thelionyard.co.uk/stores/"
    link_re = r'<a href="(https://www\.thelionyard\.co\.uk/stores/[a-z0-9-]+/)"[^>]*>([^<]*)'
    centre, address = "Lion Yard", "Lion Yard, St Tibbs Row, Cambridge CB2 3ET"
