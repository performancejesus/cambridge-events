"""53. Дети: секции и программы (исправляющая; итоги 7f и правки 5, 10 после v13). В детской рубрике и «Секциях»:
нет взрослого (adult / senior men / masters / 16+ / 18+ / over 50); нет продлёнок и завтраков при школах; у секции —
провайдер в названии, площадка, возраст, что за занятие (иначе — в «нужно дополнить» редактору); Home Ed — с пометкой;
занятие в учебное время в будни без пометки Home Ed — не показываем (уточнить). Программы каникул: только в зоне
выпуска; в строке — возраст, место, цена или «цены на сайте»; цена с точкой («£5.50», не «£5,50»); возраст в названии
один раз; «Ещё N программ» — с согласованием числа."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 53, "Дети: без взрослого и продлёнок, обязательные поля, Home Ed, строки программ", FIX


def check(ctx) -> Finding:
    from pipeline import issue
    from pipeline.selection import WRAPAROUND_RE, adult, section_reason
    f = Finding()
    for e in ctx.entries("ru"):
        if e["rubric"] not in ("kids", "holidays"):
            continue
        text = f"{e['title']} {e['meta']}"
        if adult(e["title"]) and not re.search(r"\b(kids|children|junior|youth|teen|family)\b", e["title"], re.I):
            f.violations.append(f"«{e['title']}»: взрослое в детской рубрике")
        if WRAPAROUND_RE.search(text):
            f.violations.append(f"«{e['title']}»: продлёнка или завтрак при школе")
        for c in e["cands"]:
            if c.get("kind") == "section":
                why = section_reason({"provider": c.get("provider"), "title": f"{c.get('title')} {e['title']}",
                                      "venue": c.get("venue"), "ages": c.get("ages") or e["meta"],
                                      "category": c.get("category")})
                if why and why.startswith("нужно дополнить"):
                    f.violations.append(f"«{e['title']}»: {why}")
        if e["rubric"] == "holidays" and not e.get("more") and e["ids"]:
            if re.search(r"£\s?\d+,\d{2}\b", text):
                f.violations.append(f"«{e['title']}»: цена с запятой")
            if not re.search(r"£|бесплатно|цены на сайте|free", e["meta"], re.I):
                f.violations.append(f"«{e['title']}»: нет цены или «цены на сайте»")
            ages = re.findall(r"\(([^)]*\d[^)]*)\)", e["title"])
            if len(ages) > 1:
                f.violations.append(f"«{e['title']}»: возраст в названии дважды")
            for c in e["cands"]:
                if c.get("zone") and c["zone"] not in issue.LISTED_ZONES:
                    f.violations.append(f"«{e['title']}»: программа вне зоны")
        m = re.search(r"Ещё (\d+) (программ\w*)", e["title"])
        if m:
            n, word = int(m.group(1)), m.group(2)
            want = issue._n_ru(n, "программа", "программы", "программ").split()[1]
            if word != want:
                f.violations.append(f"«{e['title']}»: «{n} {word}» — нужно «{n} {want}»")
    sw = ctx.result.get("sections_why") or {}
    need = sum(1 for v in sw.values() if v.startswith("нужно дополнить"))
    f.info.append(f"секций скрыто до дополнения данных: {need}")
    return f
