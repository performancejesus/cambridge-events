"""S050 Fitzwilliam Museum: Atom-фид выставок."""

from ..generic import FeedCollector


class Fitzwilliam(FeedCollector):
    source_id, name = "S050", "Fitzwilliam Museum"
    feeds = ['https://fitzmuseum.cam.ac.uk/feeds/exhibitions']
