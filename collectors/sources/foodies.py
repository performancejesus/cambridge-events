"""S087 The Cambridge Foodies: RSS (поток «новое в городе»). WordPress.com отвечает 429 на частые
запросы — один запрос за прогон, бэк-офф в PoliteClient."""

from ..generic import FeedCollector


class CambridgeFoodies(FeedCollector):
    source_id, name = "S087", "The Cambridge Foodies"
    feeds = ["https://cambridgefoodies.me.uk/feed/"]
