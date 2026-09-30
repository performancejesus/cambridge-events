"""11. Ссылка на первоисточник (исправляющая): порядок — площадка или организатор → продавец билетов → агрегатор →
газета; у фильмов Wikipedia — только если кинотеатр не подтверждён. Кандидаты ссылки — все записи источников события и
его несклеенных дублей той же даты и площадки (The bEAT: ссылка на musiclivecambridge при странице Corn Exchange).
Исправляет build_issue.fix_links."""

from __future__ import annotations

from . import FIX, Finding
from .common import TIER_RU, tier

RULE, TITLE, LEVEL = 11, "Ссылка — на первоисточник", FIX


def best_url(c: dict) -> str | None:
    urls = [u for u in (c.get("all_urls") or []) if u]
    urls += [u for s in c.get("siblings") or [] for u in s.get("urls") or [] if u]
    return min(urls, key=tier) if urls else None


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        if not e["cands"] or not e["url"] or e["more"]:
            continue
        c = e["cands"][0]
        if c.get("kind") == "film_release":
            if "wikipedia.org" in e["url"] and (c.get("cinemas") or c.get("cinema_url")):
                f.violations.append(f"«{e['title']}»: ссылка на Wikipedia, хотя фильм идёт в {', '.join(c.get('cinemas') or [])}")
            continue
        if len(e["ids"]) > 3:   # компактные строки из многих занятий («Регулярно в библиотеках») — своя ссылка
            continue
        b = best_url(c)
        if b and tier(b) < tier(e["url"]):
            f.violations.append(f"«{e['title']}»: ссылка — {TIER_RU.get(tier(e['url']), '?')} ({e['url']}), есть "
                                f"{TIER_RU[tier(b)]} ({b})")
    return f
