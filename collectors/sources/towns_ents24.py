"""S128 Ents24 — страницы городов зоны (этап 5: расширение географии через агрегатор S006).

Площадки Питерборо (Key Theatre, New Theatre, собор), Ely, Бери-Сент-Эдмундс (Apex, Theatre Royal), Saffron Walden
(Saffron Hall), Haverhill и др. — одной страницей на город; JSON-LD с адресом и postcode площадки.
"""

from ..generic import TownPagesJsonLd

TOWNS = ["peterborough", "ely", "huntingdon", "st-neots", "st-ives", "wisbech", "march", "bury-st-edmunds",
         "saffron-walden", "newmarket", "royston", "haverhill"]


class TownsEnts24(TownPagesJsonLd):
    source_id, name = "S128", "Ents24 — города зоны"
    pages = [f"https://www.ents24.com/whatson/{t}" for t in TOWNS]
