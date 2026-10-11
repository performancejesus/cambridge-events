"""49. Название пункта совпадает с заголовком страницы по ссылке (блокирующая; правка 1 после v13: «Spem In Alium:
I Fagiolini at 40» вёл на страницу «Shine with Jess Gillam»). Заголовок — из кэша общего слоя запросов (title, og:title,
h1), без новых запросов; страницы нет в кэше — пункт не проверяется (в info). Совпадение — нормализованные названия или
общие отличительные слова (≥ 4 букв)."""

from __future__ import annotations

import gzip
import html
import re

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 49, "Название пункта = заголовок страницы по ссылке (по кэшу)", BLOCK
SKIP_KINDS = {"venue_news", "film_release", "programme", "section", "course", "festival", "union_line", "adult_programme"}


def page_title(url: str) -> str | None:
    from collectors.http import PoliteClient
    path = PoliteClient._body_path(url)
    if not path.exists():
        return None
    try:
        body = gzip.decompress(path.read_bytes())[:300000].decode("utf-8", "replace")
    except OSError:
        return None
    out = []
    for rx in (r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>"):
        m = re.search(rx, body, re.I | re.S)
        if m:
            out.append(html.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(1))).strip())
    return " | ".join(out) or None


def check(ctx) -> Finding:
    from scripts.build_issue import title_match
    f = Finding()
    checked = nocache = 0
    for e in ctx.entries("en"):
        if e["compact"] or not e["url"] or not e["cands"] or e["cands"][0].get("kind") in SKIP_KINDS:
            continue
        pt = page_title(e["url"])
        if not pt:
            nocache += 1
            continue
        checked += 1
        names = [e["title"]] + [c["title"] for c in e["cands"]]
        score = max(title_match(n, part) for n in names for part in pt.split(" | "))
        if score < 0.34:
            f.violations.append(f"«{e['title']}»: заголовок страницы по ссылке — «{pt[:90]}» ({e['url']})")
    f.info.append(f"сверено по кэшу {checked}, страниц нет в кэше {nocache}")
    return f
