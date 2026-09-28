"""S129 Skiddle — страницы городов зоны (этап 5: расширение географии через агрегатор S007).

Страница города у Skiddle включает и ближайшие города — события вне зоны помечаются out_of_zone по postcode.
"""

from ..generic import TownPagesJsonLd

TOWNS = ["Peterborough", "Ely", "Huntingdon", "St-Neots", "St-Ives", "Wisbech", "March", "Bury-St-Edmunds",
         "Saffron-Walden", "Newmarket", "Royston", "Haverhill"]


class TownsSkiddle(TownPagesJsonLd):
    source_id, name = "S129", "Skiddle — города зоны"
    pages = [f"https://www.skiddle.com/whats-on/{t}/" for t in TOWNS]
