"""S003 Cambridge Independent: RSS раздела What's On."""

from ..generic import FeedCollector


class CambridgeIndependent(FeedCollector):
    source_id, name = "S003", "Cambridge Independent"
    feeds = ['https://www.cambridgeindependent.co.uk/_api/rss/cambridge_independent_whatson_feed.xml']
