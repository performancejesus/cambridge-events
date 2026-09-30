"""10. Цена (исправляющая): только из данных; неизвестная — «цены на сайте»; ровные суммы без копеек; «бесплатно» —
только если максимум £0 (или страница события говорит «free»); цена берётся из лучшего источника события (в том числе
из несклеенного дубля той же даты и площадки), а не из источника ссылки. Исправляет build_issue.fix_prices_best."""

from __future__ import annotations

import re

from pipeline import issue
from . import FIX, Finding
from .common import UNKNOWN_PRICE, price_nums

RULE, TITLE, LEVEL = 10, "Цена — из данных и из лучшего источника", FIX
SKIP = {"venue_news", "film_release", "cancellation", "programme", "holiday_event"}


def known_prices(c: dict) -> set[float]:
    vals = set(price_nums(c.get("price_text"))) | set(price_nums(c.get("page_price")))
    if c.get("price_from") is not None:
        vals.add(float(c["price_from"]))
    for s in c.get("siblings") or []:
        vals |= set(price_nums(s.get("price_text")))
    return vals | {round(x) for x in vals}


def has_price(c: dict) -> bool:
    return bool(price_nums(c.get("price_text")) or price_nums(c.get("page_price"))
                or any(price_nums(s.get("price_text")) for s in c.get("siblings") or []))


def is_free(c: dict) -> bool:
    return issue.strictly_free(c.get("price_from"), c.get("price_text")) or (c.get("page_price") or "").lower() == "free" \
        or any(issue.strictly_free(s.get("price_from"), s.get("price_text")) or (s.get("price_text") or "").lower() == "free"
               for s in c.get("siblings") or [])


def check(ctx) -> Finding:
    f = Finding()
    for rub, it in ctx.model_items():
        cands = [ctx.pools.candidates[i] for i in it["ids"] if i in ctx.pools.candidates]
        if not cands or cands[0]["kind"] in SKIP or rub == "cancelled" or it.get("also"):
            continue
        p = (it.get("price_ru") or "").strip()
        t = it.get("title_ru")
        if re.fullmatch(r"цена не указана|цена при (?:записи|бронировании)|цена — при записи", p, re.I):
            f.violations.append(f"«{t}»: «{p}» вместо «цены на сайте»")
        if re.fullmatch(r"бесплатно|free", p, re.I) and not any(is_free(c) for c in cands):
            f.violations.append(f"«{t}»: «бесплатно», а в данных цена {cands[0].get('price_text')}")
        if UNKNOWN_PRICE.match(p) and any(has_price(c) or is_free(c) for c in cands):
            best = next(c for c in cands if has_price(c) or is_free(c))
            f.violations.append(f"«{t}»: «{p}», хотя цена есть в данных "
                                f"({best.get('price_text') or best.get('page_price') or [s['price_text'] for s in best.get('siblings') or [] if s.get('price_text')][:1]})")
        nums = set(price_nums(p))
        known = set().union(*(known_prices(c) for c in cands))
        wrong = {x for x in nums if x not in known and not re.search(rf"{x:g}\s*(?:лет|years|%)", p)}
        if wrong and known:
            f.violations.append(f"«{t}»: цифры цены {sorted(wrong)} не из данных ({p})")
    for name, html in ctx.html.items():   # ровные суммы без копеек — в том, что видит читатель
        for m in re.finditer(r"£\d+\.00\b", html):
            f.violations.append(f"{name}: копейки в ровной сумме ({m.group(0)})")
    return f
