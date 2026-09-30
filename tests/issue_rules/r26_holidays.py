"""26. «Каникулы» (исправляющая; issue.limited_holiday_groups, holiday_clip, kids_collect, glossary): лимиты строк
(ближайшие — до 12, следующие — до 5, «Куда сходить с детьми» — до 6), даты только в дни каникул (с прилегающими
выходными), зона по площадке (только зоны выпуска), глоссарий перевода (gym ≠ гимнастика, junior ≠ младший)."""

from __future__ import annotations

import re

from pipeline import issue
from . import FIX, Finding

RULE, TITLE, LEVEL = 26, "«Каникулы»: лимиты, дни каникул, зона, глоссарий", FIX
BAD_TRANSLATION = re.compile(r"гимнастик\w* для младших|для младших|младш\w+ (?:группа|гимнаст)|гимнастик\w*[^.]*\bgym\b", re.I)


def check(ctx) -> Finding:
    f = Finding()
    L = ctx.layout("ru")
    hols = issue.nearest_holidays(ctx.w)
    for sec in L["sections"]:
        if sec["rubric"] != "holidays":
            continue
        for g in sec["groups"]:
            lines = [x for x in g["items"] if not x.get("more")]
            t = g["title"]
            cap = 6 if t.startswith("Куда сходить") else None if t.startswith("Успейте") else 12 if "запись идёт" in t else 5
            if cap is not None and len(lines) > cap:
                f.violations.append(f"«{t[:40]}»: {len(lines)} строк, лимит {cap}")
            for x in lines:
                if BAD_TRANSLATION.search(x["title"]):
                    f.violations.append(f"перевод: «{x['title']}»")
                for i in x.get("ids") or []:
                    c = ctx.pools.candidates.get(i) or {}
                    if c.get("kind") == "programme" and c.get("zone") not in issue.LISTED_ZONES \
                            and not (c.get("zone") is None and c.get("audience") == "eligible"):
                        f.violations.append(f"«{x['title']}»: зона {c.get('zone')}")
                    h = hols.get(c.get("holiday")) if c.get("kind") == "programme" else None
                    if h and c.get("dates"):
                        clipped, _ = issue.holiday_clip(c, [tuple(c["dates"][0][:2])], h)
                        a, b = issue.d(clipped[0][0]), issue.d(clipped[0][1])
                        hs, he = issue.d(h["start"]), issue.d(h["end"])
                        from datetime import timedelta
                        if b < hs - timedelta(days=2) or a > he + timedelta(days=2):
                            f.violations.append(f"«{x['title']}»: даты вне каникул")
    return f
