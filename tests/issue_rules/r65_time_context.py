"""65. Время пункта не противоречит описанию (блокирующая; правка 6 после v14): Space Safari Drone Light Show — в строке
«12:00 и 16:00», в описании «два вечерних показа», на странице — с 16:00, шоу 19:15–20:00. «Вечерний показ» /
«после заката» / «ночное небо» и дневное время (до 15:00) в одном пункте — противоречие. Время со страницы
события подставляет pipeline/page_times.py."""

from __future__ import annotations

import re

from . import BLOCK, Finding

RULE, TITLE, LEVEL = 65, "Время пункта не противоречит описанию (вечерний показ ≠ 12:00)", BLOCK
EVENING_RU = re.compile(r"вечерн\w+ (?:показ|шоу|сеанс)|после заката|ночн\w+ неб\w+|в темноте", re.I)
EVENING_EN = re.compile(r"\bevening (?:show|display|performance)s?\b|\bafter (?:sunset|dark)\b|\bnight sky\b", re.I)


def check(ctx) -> Finding:
    f = Finding()
    for lang, rx in (("ru", EVENING_RU), ("en", EVENING_EN)):
        for e in ctx.entries(lang):
            if not rx.search(f"{e['blurb']} {e['why']}"):
                continue
            times = [int(h) for h, _ in re.findall(r"\b(\d{1,2}):(\d{2})\b", e["meta"])]
            if times and min(times) < 15:   # хоть одно дневное время («12:00 и 16:00») при вечернем показе
                f.violations.append(f"«{e['title']}» ({lang}): в описании вечерний показ, а время {e['meta'][:60]}")
    return f
