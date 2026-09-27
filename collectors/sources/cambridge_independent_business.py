"""S092 Cambridge Independent — News и Business (RSS) для «новое в городе» и отмен (через извлечение из статей)."""

from ..generic import FeedCollector


class CambridgeIndependentBusiness(FeedCollector):
    source_id, name = "S092", "Cambridge Independent — News/Business"
    feeds = ["https://www.cambridgeindependent.co.uk/_api/rss/cambridge_independent_business_feed.xml",
             "https://www.cambridgeindependent.co.uk/_api/rss/cambridge_independent_news_feed.xml"]
