"""17. Пустые описания (исправляющая): если в описании нет содержательного факта — загрузка страницы → recurring_events →
факты матча или скачек → знания модели с пометкой; иначе пункт не брать (кроме оценки ≥ 6 — нейтральная фраза и
пометка редактору). Правки по v9: у «Нового в городе» то же («открылось новое чайное кафе» — пусто): факт со страницы
(build_issue.fix_empty_news) или пункт убирается."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 17, "Пустые описания (в том числе «Новое в городе»)", FIX
NEWS_GENERIC_RU = re.compile(r"^(?:на [\w' -]+ )?(?:открыл\w*|откро\w*|появил\w*)\s+(?:нов\w+\s+)?[\w -]{0,30}"
                             r"(?:кафе|ресторан|бар|магазин|паб|пекарн\w+|кофейн\w+|заведени\w+)"
                             r"(?:\s+на [\w' -]+)?\.?$|^нов\w+ [\w -]{0,30}(?:кафе|ресторан|бар|магазин|паб|пекарн\w+|кофейн\w+)"
                             r"(?: на [\w' -]+)? открыл\w*\.?$", re.I)


def generic(blurb_en: str, blurb_ru: str, title_en: str, kind: str) -> bool:
    from scripts.build_issue import GENERIC_RE, GENERIC_RU_RE, content_words
    if not blurb_ru.strip():
        return True
    if GENERIC_RE.match(blurb_en.strip()) or GENERIC_RU_RE.match(blurb_ru.strip()) or NEWS_GENERIC_RU.match(blurb_ru.strip()):
        return True
    if kind == "venue_news":   # v10: «Tea Apothecary открылось на Magdalene Street и подает чай посетителям» — пусто
        stop = {"opened", "open", "opens", "opening", "serves", "serving", "visitors", "customers", "street", "road",
                "cambridge", "new", "recently", "doors", "their", "with", "that", "this", "which", "offers", "offering",
                "tea", "coffee", "food", "drinks", "cafe", "café", "restaurant", "shop", "store", "bar", "pub"}
        words = [w for w in re.findall(r"[a-zà-ÿ']+", blurb_en.lower()) if len(w) > 3 and w not in stop
                 and w not in title_en.lower()]
        return len(words) < 3
    return content_words(blurb_en, title_en) < 3


def check(ctx) -> Finding:
    from pipeline import issue
    f = Finding()
    for rub, it in ctx.model_items():
        c = ctx.pools.candidates.get(it["ids"][0]) or {}
        if rub == "cancelled" or it.get("also") or it.get("line") or it.get("union") or c.get("kind") in ("film_release",) \
                or len(it["ids"]) > 3:   # компактные строки («Также играют», «В колледжах», Union) — без описания
            continue
        if generic(it.get("blurb_en") or "", it.get("blurb_ru") or "", it.get("title_en") or "", c.get("kind")):
            if issue.importance_of(ctx.pools, it) >= 6 and c.get("kind") != "venue_news":
                f.warnings.append(f"«{it['title_ru']}»: оценка ≥ 6, нейтральная фраза — пометка редактору")
            else:
                f.violations.append(f"«{it['title_ru']}»: «{it.get('blurb_ru')}»")
    return f
