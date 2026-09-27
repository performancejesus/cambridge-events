"""S004 Cambridge News: RSS What's On + общий фид новостей (контур отмен, Town and Gown)."""

from ..generic import FeedCollector


class CambridgeNews(FeedCollector):
    source_id, name = "S004", "Cambridge News"
    feeds = ['https://www.cambridge-news.co.uk/whats-on/?service=rss', 'https://www.cambridge-news.co.uk/?service=rss']
