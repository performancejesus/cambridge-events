"""S097 Cambridge BID: новости городского центра (RSS Squarespace).

robots.txt сайта закрывает доступ ИИ-краулерам (anthropic-ai, GPTBot и др.); наш User-Agent не в списке,
но передавать статьи в Claude — только после решения владельца проекта (см. NO_LLM_SOURCES в pipeline/extract.py).
"""

from ..generic import FeedCollector


class CambridgeBid(FeedCollector):
    source_id, name = "S097", "Cambridge BID — новости"
    feeds = ["https://www.cambridgebid.co.uk/news?format=rss"]
