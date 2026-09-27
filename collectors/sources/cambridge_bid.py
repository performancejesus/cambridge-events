"""S097 Cambridge BID: новости городского центра (RSS Squarespace).

robots.txt сайта закрывает доступ ИИ-краулерам (anthropic-ai, GPTBot и др.); наш User-Agent не в списке, но статьи
в Claude не передаются (решение после этапа 3): только заголовки RSS с фильтром по ключевым словам —
см. keyword_news и NO_LLM_SOURCES в pipeline/extract.py.
"""

from ..generic import FeedCollector


class CambridgeBid(FeedCollector):
    source_id, name = "S097", "Cambridge BID — новости"
    feeds = ["https://www.cambridgebid.co.uk/news?format=rss"]
