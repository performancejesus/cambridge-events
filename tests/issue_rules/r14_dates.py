"""14. Многодневные события — диапазон дат; релизы фильмов — пятница или «на этой / следующей неделе» (исправляющая;
делают issue.page_date_end и issue.release_lines). Проверка: событие из нескольких дней не показано одним днём, в
описании нет «двухдневный» при одной дате; строка релизов с датой не в пятницу — только для одного фильма (премьера)."""

from __future__ import annotations

import re
from datetime import date

from pipeline import issue
from . import FIX, Finding

RULE, TITLE, LEVEL = 14, "Многодневные события — диапазон; релизы — пятница", FIX
RANGE = re.compile(r"\d+\s*[–-]\s*\d+|\bдо \d|\s–\s|\bи\b")
MULTI = re.compile(r"двухдневн|трёхдневн|двух дней|two-day|three-day|over two days", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(issue.MONTHS_RU)}


def check(ctx) -> Finding:
    f = Finding()
    for e in ctx.entries("ru"):
        c = e["cands"][0] if e["cands"] else {}
        if c.get("kind") in ("event", "announcement", "tickets") and c.get("dates") and not c.get("regular_series"):
            spans = [(x[0], x[1]) for x in c["dates"] if x[0]]
            multi = any(a != b for a, b in spans) or len({a for a, _ in spans}) > 1
            when = next((x for x in e["meta"].split(" · ") if re.search(r"\d", x)), "")
            if multi and not RANGE.search(when):
                f.violations.append(f"«{e['title']}»: событие на несколько дней показано одним днём ({when})")
            if not multi and MULTI.search(e["blurb"]):
                f.violations.append(f"«{e['title']}»: в описании «несколько дней», а дата одна")
        if c.get("kind") == "film_release" and c.get("dates"):   # полный пункт о фильме: дата релиза — пятница
            x = issue.d(c["dates"][0][0])
            if x >= ctx.w.issue and x.weekday() != 4 and "пт" not in e["meta"]:
                f.violations.append(f"«{e['title']}»: релиз не в пятницу ({e['meta'].split(' · ')[0]})")
        if e["rubric"] == "cinema" and e["compact"] and e["title"].startswith("В прокате с "):
            m = re.match(r"В прокате с (?:пятницы, )?(\d+) (\w+)", e["title"])
            if m and "пятницы" not in e["title"]:
                d = date(ctx.w.issue.year, MONTHS.get(m.group(2), ctx.w.issue.month), int(m.group(1)))
                films = [x for x in re.split(r",|;", e["meta"]) if x.strip()]
                if d.weekday() != 4 and len(films) > 1:
                    f.violations.append(f"«{e['title']}»: дата релиза не пятница для нескольких фильмов")
    return f
