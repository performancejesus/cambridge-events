"""S093 Cambridge News — еда и напитки, магазины (RSS) для «новое в городе»; общий фид новостей — в S004."""

from ..generic import FeedCollector


class CambridgeNewsBusiness(FeedCollector):
    source_id, name = "S093", "Cambridge News — Food & Drink/Shopping"
    feeds = ["https://www.cambridge-news.co.uk/all-about/food-and-drink?service=rss",
             "https://www.cambridge-news.co.uk/all-about/shopping?service=rss"]
