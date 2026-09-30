"""32. Семейные фильмы — кандидаты и в «С детьми» (исправляющая; правки по v9: Forgotten Island — анимация DreamWorks).
Фильм окна с признаками семейного (анимация, family, для детей — по описанию Wikipedia или сайта кинотеатра) получает
kids_tag и может идти в «С детьми»; проверка — у таких кандидатов пометка есть."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 32, "Семейные фильмы — кандидаты в «С детьми» (правки по v9)", FIX
FAMILY_FILM = re.compile(r"\banimat\w+|\bfamily\b|\bchildren'?s\b|\bkids?\b|\bDreamWorks\b|\bPixar\b|\bIllumination\b|"
                         r"\bDisney\b|\bAardman\b|\bGhibli\b", re.I)


def is_family_film(c: dict) -> bool:
    return c.get("kind") == "film_release" and bool(FAMILY_FILM.search(" ".join(str(c.get(k) or "") for k in (
        "wiki_description", "wiki_extract", "genre"))))


def check(ctx) -> Finding:
    f = Finding()
    for cid, c in ctx.pools.candidates.items():
        if is_family_film(c) and not c.get("kids_tag"):
            f.violations.append(f"«{c['title']}»: семейный фильм без пометки для «С детьми»")
    return f
