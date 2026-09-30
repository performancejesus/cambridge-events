"""Запуск всех проверок на собранном выпуске: сверка утверждений (Haiku, кэш), проверка ссылок (наш бот, кэш на
сутки), затем правила r01–rNN. Используется в scripts/build_issue.py (каждая сборка) и scripts/check_issue.py."""

from __future__ import annotations

from . import run
from .common import Ctx


def full_run(ctx: Ctx, client=None, http=None) -> tuple[list, float]:
    from . import claims, links
    cost = 0.0
    if ctx.options.get("api", True):
        res, cost = claims.collect(ctx, client)
        if res["sentences"] or res["items"] or client is not None:
            ctx.claims = res
    if ctx.options.get("links", True) and http is not None:
        urls = [u for name, h in ctx.html.items() if name.startswith("reader") for u in links.hrefs(h)
                if u.startswith("http")]
        ctx.links = links.check_urls(ctx.con, list(dict.fromkeys(urls)), http)
    return run(ctx), cost
