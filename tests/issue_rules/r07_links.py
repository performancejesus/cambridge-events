"""7. Ссылки (блокирующая): каждая ссылка читательской версии отвечает (не 404 / 410); нет относительных ссылок на
файлы, которых не будет у читателя. Закрытые robots.txt и защита от ботов (403) — не блок, а замечание: страницу не
проверить нашим ботом."""

from __future__ import annotations

from urllib.parse import urlparse

from . import BLOCK, Finding
from .links import hrefs

RULE, TITLE, LEVEL = 7, "Ссылки отвечают, нет относительных ссылок на отсутствующие файлы", BLOCK
PUBLISHED_PAGES = ("kids_",)   # страницы, которые публикуются рядом с выпуском (этап 8: Cloudflare Pages)


def check(ctx) -> Finding:
    f = Finding()
    urls = []
    for name, html in ctx.html.items():
        if not name.startswith("reader"):
            continue
        for u in hrefs(html):
            p = urlparse(u)
            if p.scheme in ("http", "https"):
                urls.append(u)
            elif p.scheme in ("mailto", "tel") or u.startswith("#"):
                continue
            elif not (ctx.out_dir / p.path).exists() or not p.path.startswith(PUBLISHED_PAGES):
                f.violations.append(f"{name}: относительная ссылка «{u}» — файла не будет у читателя")
    urls = list(dict.fromkeys(urls))
    if ctx.links is None:
        f.skipped = f"сеть не проверялась ({len(urls)} ссылок)"
        return f
    for u in urls:
        r = ctx.links.get(u)
        if not r:
            continue
        if r["status"] == "dead":
            f.violations.append(f"{u} — HTTP {r['detail']}")
        elif r["status"] in ("error", "disallowed"):
            f.warnings.append(f"{u} — не проверить: {r['detail']}")
    f.info.append(f"ссылок проверено: {len(urls)}")
    return f
