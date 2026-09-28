"""S116–S119 газеты Newsquest (Hunts Post, Cambs Times, Wisbech Standard, Ely Standard): RSS /news/rss/.

Статьи идут в извлечение через Claude, но сначала — дедупликация между газетами и предфильтр по ключевым словам
(pipeline/extract.newsquest_prefilter, решение после этапа 5). Метка ?ref=rss из ссылок убирается: по ссылке
и номеру материала общий материал узнаётся во всех четырёх газетах.
"""

from ..generic import FeedCollector


class _Newsquest(FeedCollector):
    site = ""

    @property
    def feeds(self) -> list[str]:
        return [f"https://www.{self.site}/news/rss/"]

    def collect(self, http):
        out = super().collect(http)
        for e in out:
            e.url = (e.url or "").split("?")[0]
        return out


class HuntsPost(_Newsquest):
    source_id, name, site = "S116", "Hunts Post", "huntspost.co.uk"


class CambsTimes(_Newsquest):
    source_id, name, site = "S117", "Cambs Times", "cambstimes.co.uk"


class WisbechStandard(_Newsquest):
    source_id, name, site = "S118", "Wisbech Standard", "wisbechstandard.co.uk"


class ElyStandard(_Newsquest):
    source_id, name, site = "S119", "Ely Standard", "elystandard.co.uk"
