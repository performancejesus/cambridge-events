"""S010 Peterborough Telegraph: RSS (статьи → извлечение через Claude, как у Cambridge News). HTML закрыт (403)."""

from ..generic import FeedCollector


class PeterboroughTelegraph(FeedCollector):
    source_id, name = "S010", "Peterborough Telegraph"
    feeds = ["https://www.peterboroughtoday.co.uk/rss"]
