"""S096 The Grafton: список магазинов (новые арендаторы — по сравнению с прошлым прогоном)."""

from ..generic import StoreListCollector


class Grafton(StoreListCollector):
    source_id, name = "S096", "The Grafton — магазины"
    list_url = "https://graftoncentre.co.uk/stores/"
    link_re = r'<a href="(https://graftoncentre\.co\.uk/stores/[a-z0-9-]+/)"[^>]*>([^<]*)'
    centre, address = "The Grafton", "The Grafton, Fitzroy Street, Cambridge CB1 1PS"
