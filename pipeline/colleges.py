"""Этап 7c: рубрика «В колледжах» (бриф, «Рубрика «В колледжах»», решено 30.09).

Компактная рубрика, 3–6 строк, как «Также играют»: название — дата, время — колледж и площадка — цена или «бесплатно» —
доступ, если не для всех. Собирается без модели из кандидатов окна, которые не попали в полные пункты.
- Берём: публичные лекции и лекционные серии, концерты хоров и музыкальных обществ (не службы и не evensong), выставки в
  галереях колледжей, открытые сады (NGS), студенческий театр (Camdram: Corpus Playroom, театры колледжей), открытые дни
  библиотек и колледжей.
- Не берём: ADC и Footlights (обычные театральные рубрики), Kettle's Yard и музеи университета (обычные рубрики),
  службы, встречи выпускников и внутренние занятия, события с доступом restricted.
- Отбор: оценка важности (известность исполнителя или лектора уже в ней) + бонус крупной серии (Darwin, Tanner, Birkbeck
  и др.), не больше 2 строк от одного колледжа, при равенстве — ближайшая дата.
"""

from __future__ import annotations

import re

from .normalize import norm_venue

COLLEGES = ["Christ's", "Churchill", "Clare Hall", "Clare", "Corpus Christi", "Darwin", "Downing", "Emmanuel",
            "Fitzwilliam College", "Girton", "Gonville & Caius", "Hughes Hall", "Jesus", "King's", "Lucy Cavendish",
            "Magdalene", "Murray Edwards", "Newnham", "Pembroke", "Peterhouse", "Queens'", "Robinson", "St Catharine's",
            "St Edmund's", "St John's", "Selwyn", "Sidney Sussex", "Trinity Hall", "Trinity", "Wolfson"]
# площадки колледжей без слова College в названии
VENUE_COLLEGE = {"corpus playroom": "Corpus Christi", "heong gallery": "Downing", "howard theatre": "Downing",
                 "women's art collection": "Murray Edwards", "fitzpatrick hall": "Queens'", "pembroke new cellars": "Pembroke",
                 "new cellars": "Pembroke", "brickhouse": "Robinson", "graham storey room": "Trinity Hall",
                 "von hügel institute": "St Edmund's", "churchill archives centre": "Churchill", "wren library": "Trinity",
                 "parker library": "Corpus Christi", "pepys library": "Magdalene", "old divinity school": "St John's",
                 "stephen hawking building": "Gonville & Caius", "cockcroft": "Churchill"}
COLLEGE_SOURCES = {"S143", "S144", "S149", "S166", "S169", "S170", "S171", "S172", "S173", "S174", "S175", "S163", "S164"}
SKIP_RE = re.compile(r"\b(evensong|eucharist|compline|matins|vespers|holy communion|mass\b|service|congregation|"
                     r"alumni|alumnae|members'? (?:dinner|lunch)|family supper|formal hall|admissions|open day for applicants|"
                     r"visit day|interview|footlights)\b", re.I)
NOT_HERE_VENUE_RE = re.compile(r"\b(ADC Theatre|Kettle'?s Yard|Fitzwilliam Museum|Museum of|Sedgwick|Polar Museum|Whipple|"
                               r"Botanic Garden|Arts Theatre|Corn Exchange|Junction|West Road)\b", re.I)
SERIES_RE = re.compile(r"\b(Darwin College Lecture|Tanner Lecture|Birkbeck Lecture|Roskill|Ashby Lecture|Von H[üu]gel|"
                       r"Kate Pretty|Inaugural Lecture|Memorial Lecture|Lecture Series)\b", re.I)
LINES_MIN, LINES_MAX, PER_COLLEGE = 3, 6, 2
KIND_RU = {"lecture": "лекция", "concert": "концерт", "theatre": "студенческий театр", "garden": "открытый сад",
           "exhibition": "выставка", "other": ""}


def college_of(c: dict) -> str | None:
    text = f"{c.get('venue') or ''}, {c.get('address') or ''}"
    low = norm_venue(c.get("venue") or "")
    for k, col in VENUE_COLLEGE.items():
        if k in low or k in text.lower():
            return col
    for col in COLLEGES:
        name = col.replace("'", "['’]?")
        if re.search(rf"\b{name}(?: College)?\b", text, re.I) and re.search(r"college|hall|chapel|court|library|"
                                                                            r"garden|lecture theatre|room", text, re.I):
            if col in ("Clare", "Trinity") and re.search(rf"{col} (Hall)", text, re.I):
                return f"{col} Hall"
            return col
    return None


def kind_of(c: dict) -> str:
    t = f"{c.get('title') or ''} {' '.join(c.get('categories') or [])}"
    if re.search(r"lecture|talk|in conversation|seminar|panel", t, re.I):
        return "lecture"
    if re.search(r"NGS|garden opening", t):
        return "garden"
    if "S168" in (c.get("sources") or []) or re.search(r"\b(play|theatre|musical|drama)\b", t, re.I):
        return "theatre"
    if re.search(r"exhibition|gallery", f"{t} {c.get('venue') or ''}", re.I) or c.get("long_running"):
        return "exhibition"
    if re.search(r"concert|recital|choir|organ|music|quartet|trio|orchestra|singers|ensemble", t, re.I):
        return "concert"
    return "other"


def candidates(pools, used_events: set[int]) -> list[tuple[str, dict, str, str]]:
    """(id, кандидат, колледж, вид) — все подходящие кандидаты окна; used_events — события, уже стоящие полными пунктами."""
    out, seen = [], set()
    for cid, c in pools.candidates.items():
        if c["kind"] != "event" or c.get("access") == "restricted" or c.get("zone") != "центр":
            continue
        col = college_of(c)
        if not col and not set(c.get("sources") or []) & COLLEGE_SOURCES:
            continue
        if not col:
            continue
        if SKIP_RE.search(c["title"]) or NOT_HERE_VENUE_RE.search(c.get("venue") or ""):
            continue
        if set(c["event_ids"]) & used_events:
            continue
        sib = {e for s in c.get("siblings") or [] for e in s["event_ids"]}
        key = (c["dates"][0][0], re.sub(r"\W+", " ", c["title"].lower())[:30])
        if key in seen or sib & used_events:
            continue
        seen.add(key)
        out.append((cid, c, col, kind_of(c)))
    return out


def score(c: dict, kind: str) -> float:
    s = c.get("importance") or 2.5
    if SERIES_RE.search(c["title"]):
        s += 1.5
    if c.get("performer") or c.get("lineup"):
        s += 0.5
    return s


def select(cands: list[tuple[str, dict, str, str]]) -> tuple[list, dict[str, str]]:
    """Отбор 3–6 строк: по оценке, не больше 2 от колледжа; → (выбранные, причины для остальных)."""
    ranked = sorted(cands, key=lambda x: (-score(x[1], x[3]), x[1]["dates"][0][0]))
    chosen, per, why = [], {}, {}
    for cid, c, col, kind in ranked:
        if len(chosen) >= LINES_MAX:
            why[cid] = f"лимит рубрики ({LINES_MAX} строк)"
        elif per.get(col, 0) >= PER_COLLEGE:
            why[cid] = f"уже {PER_COLLEGE} строки от колледжа {col}"
        else:
            chosen.append((cid, c, col, kind))
            per[col] = per.get(col, 0) + 1
    return sorted(chosen, key=lambda x: (x[1]["dates"][0][0], x[1]["dates"][0][2] or "")), why


def build_items(pools, result: dict) -> tuple[list[dict], dict[str, str]]:
    """Строки рубрики (элементы ответа модели с флагом line) и причины пропуска для редакторской версии."""
    from . import issue
    used = {e for sec in result["sections"] if sec["rubric"] != "colleges" for it in sec["items"] for i in it["ids"]
            if i in pools.candidates for e in pools.candidates[i]["event_ids"]}
    cands = candidates(pools, used)
    chosen, why = select(cands)
    if len(chosen) < LINES_MIN:
        for cid, *_ in chosen:
            why[cid] = f"меньше {LINES_MIN} кандидатов — рубрика не выводится"
        chosen = []
    items = []
    for cid, c, col, kind in chosen:
        from .issue_fixes import _priced
        best = next(iter(_priced(c)), None)
        en, ru = issue.price_from_data({"price_text": best[1], "price_from": best[2]} if best else c)
        if best and best[1] == "Free":
            en, ru = "free", "бесплатно"
        if en == "price not listed":
            en, ru = "prices on the website", "цены на сайте"
        venue = c.get("venue") or (c.get("address") or "").split(",")[0] or col
        where_ru = venue if col.split()[0].lower() in venue.lower() else f"{col} College, {venue}"
        acc = issue.access_mark(c, "ru")[0]
        from tests.issue_rules.common import tier
        from tests.issue_rules.r11_primary_link import best_url
        b = best_url(c)
        items.append({"ids": [cid], "line": True, "url": b if b and tier(b) < tier(c.get("url")) else c.get("url"), "auto": True, "college": col, "kind_ru": KIND_RU[kind],
                      "title_en": c["title"], "title_ru": c["title"], "where_en": where_ru, "where_ru": where_ru,
                      "price_en": en, "price_ru": ru, "blurb_en": "", "blurb_ru": "", "access_ru": acc,
                      "knowledge_en": [], "knowledge_ru": []})
    return items, why
