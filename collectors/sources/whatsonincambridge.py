"""S002 What's On In Cambridge: RSS (страница /events/ за JS-проверкой)."""

from ..generic import FeedCollector


class WhatsOnInCambridge(FeedCollector):
    source_id, name = "S002", "What's On In Cambridge"
    feeds = ['https://www.whatsonincambridge.com/feed/']
