"""Этап 7e, пункты 3–4: необычные традиции и крупные ежегодные события зоны — поиск официальных страниц и дат.

Keenable даёт кандидатов (официальный сайт, дата текущего цикла, проводится ли) — это не факты: дата и статус
подтверждаются нашим ботом на официальной странице (scripts/check_recurring.py, правила бережного сбора).

Запуск: python scripts/recurring_research.py → data/recurring_research_7e.json (запросы и выдача)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.db import connect  # noqa: E402
from pipeline.keenable import Keenable  # noqa: E402

CANDIDATES = [
    # (ключ, название, запросы)
    ("pea_shooting", "World Pea Shooting Championship (Witcham)", ["World Pea Shooting Championship Witcham 2026", "worldpeashoot 2027 date"]),
    ("snail_racing", "World Snail Racing Championship (Congham)", ["World Snail Racing Championship Congham 2026", "Congham snail racing 2027"]),
    ("pig_racing", "Гонки поросят в зоне", ["pig racing Cambridgeshire show", "pig racing Suffolk Norfolk farm park event", "pig races country show Cambridgeshire 2026"]),
    ("cheese_rolling", "Stilton Cheese Rolling", ["Stilton cheese rolling 2026", "Stilton cheese rolling May bank holiday"]),
    ("eel_festival", "Ely Eel Festival / Eel Day", ["Ely Eel Festival 2026", "Ely Eel Festival eel throwing"]),
    ("quirky_other", "Другие необычные традиции зоны", ["unusual traditions Cambridgeshire annual quirky event", "quirky annual events Fens Cambridgeshire",
                                                        "Plough Monday molly dancing Cambridgeshire", "duck race St Ives annual", "bathtub race Cambridgeshire"]),
    ("lit_fest", "Cambridge Literary Festival", ["Cambridge Literary Festival 2026 winter dates", "Cambridge Literary Festival spring 2027"]),
    ("shakespeare", "Cambridge Shakespeare Festival", ["Cambridge Shakespeare Festival 2026 college gardens"]),
    ("summer_music", "Cambridge Summer Music Festival", ["Cambridge Summer Music Festival 2026"]),
    ("jazz", "Cambridge International Jazz Festival", ["Cambridge International Jazz Festival November 2026"]),
    ("lent_bumps", "Lent Bumps", ["Lent Bumps 2027 dates CUCBC"]),
    ("nine_lessons", "King's College Festival of Nine Lessons and Carols", ["King's College Nine Lessons and Carols 24 December queue 2026"]),
    ("ely_folk", "Ely Folk Festival", ["Ely Folk Festival 2026", "Ely Folk Festival 2027 dates"]),
    ("ely_aquafest", "Ely Aquafest", ["Ely Aquafest", "Ely Aquafest 2026 river"]),
    ("st_ives_fair", "St Ives Michaelmas Fair", ["St Ives Michaelmas Fair October 2026", "St Ives Cambridgeshire Michaelmas fair funfair"]),
    ("wisbech_rose", "Wisbech Rose Fair", ["Wisbech Rose Fair 2026"]),
    ("pboro_beer", "Peterborough Beer Festival", ["Peterborough Beer Festival 2026 August"]),
    ("pboro_heritage", "Peterborough Heritage Festival", ["Peterborough Heritage Festival 2026"]),
    ("great_eastern", "Great Eastern Run", ["Great Eastern Run Peterborough 2026"]),
    ("secret_garden", "Secret Garden Party (Abbots Ripton)", ["Secret Garden Party 2026 Abbots Ripton", "Secret Garden Party festival 2027"]),
    ("big_retreat", "The Big Retreat", ["The Big Retreat festival 2026", "Big Retreat festival 2027 Newmarket"]),
    ("july_festival", "Newmarket July Festival", ["Newmarket July Festival 2026 dates"]),
    ("guineas", "Newmarket Guineas Festival", ["Newmarket Guineas Festival 2027 dates"]),
    ("newmarket_nights", "Newmarket Nights", ["Newmarket Nights 2026 concerts racecourse"]),
    ("bury_xmas", "Bury St Edmunds Christmas Fayre", ["Bury St Edmunds Christmas Fayre 2026"]),
    ("bury_festival", "Bury Festival", ["Bury Festival 2026 May Bury St Edmunds"]),
    ("bury_lit", "Bury St Edmunds Literary Festival", ["Bury St Edmunds Literary Festival 2026"]),
    ("saffron_hall", "Saffron Hall — сезон", ["Saffron Hall 2026-27 season"]),
    ("kl_festival", "King's Lynn Festival", ["King's Lynn Festival 2026 July"]),
    ("kl_mart", "King's Lynn Mart", ["King's Lynn Mart 2027 February"]),
    ("sandringham", "Royal Sandringham Flower Show", ["Sandringham Flower Show 2026"]),
    ("bedford_river", "Bedford River Festival", ["Bedford River Festival 2026", "Bedford River Festival next"]),
    ("knebworth", "Концерты в Knebworth", ["Knebworth Park concert 2026", "Knebworth 2027 concert announced"]),
    ("duxford_airshow", "IWM Duxford — авиашоу", ["IWM Duxford air show 2026 dates", "Duxford Battle of Britain air show 2026"]),
    ("ely_orchard", "Ely's Autumn and Orchard Fayre", ["Ely Autumn and Orchard Fayre 2026"]),
]


def main() -> None:
    con = connect()
    k = Keenable(con)
    out = {}
    for key, name, queries in CANDIDATES:
        out[key] = {"name": name, "results": []}
        for q in queries:
            for r in k.search(q, "recurring_7e", max_results=6, snippet_max_length=400):
                out[key]["results"].append({"q": q, "title": r.get("title"), "url": r.get("url"),
                                            "snippet": (r.get("snippet") or "")[:400], "published": r.get("published_at")})
    (ROOT / "data" / "recurring_research_7e.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print({"keenable_calls": k.calls, "cached": k.cached})


if __name__ == "__main__":
    main()
