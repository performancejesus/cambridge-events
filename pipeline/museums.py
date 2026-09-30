"""Этап 7d: рубрика «В музеях и усадьбах» (бриф, этап 7d, п. 1) — компактные строки по образцу «В колледжах».

Музеи университета (Museum of Zoology, Whipple, Sedgwick, MAA и др. — S052), Museum of Cambridge (S130), Centre for
Computing History (S134), Cambridge Museum of Technology (S179), Ely Museum (S180), Royston Museum (S153), усадьбы
National Trust (S070: Wimpole, Anglesey Abbey, Wicken Fen), Audley End (S139), фермы (Bury Lane, S178), Wandlebury.
У их событий оценка ~2.5 (нет вместимости, цены, Wikipedia), поэтому полными пунктами они почти не проходят.
- 4–6 строк: выставки (новые — в первую неделю открытия), экскурсии, семейные занятия, сезонные события усадеб;
- не больше 2 строк от одного места; семейные — кандидаты и в «С детьми» (по kids_tag, как все события);
- регулярные занятия (parkrun, еженедельные прогулки), закрытые и служебные события — нет;
- событие уже стоит полным пунктом — не дублируем.
"""

from __future__ import annotations

import re
from datetime import timedelta

PLACES = [("Museum of Zoology", r"Museum of Zoology"), ("Whipple Museum", r"Whipple"), ("Sedgwick Museum", r"Sedgwick"),
          ("Museum of Archaeology and Anthropology", r"Archaeology and Anthropology|\bMAA\b"),
          ("Polar Museum", r"Polar Museum|Scott Polar"), ("Museum of Classical Archaeology", r"Classical Archaeology"),
          ("Fitzwilliam Museum", r"Fitzwilliam Museum"), ("Kettle's Yard", r"Kettle.?s Yard"),
          ("Botanic Garden", r"Botanic Garden"), ("Museum of Cambridge", r"Museum of Cambridge"),
          ("Centre for Computing History", r"Computing History"), ("Cambridge Museum of Technology", r"Museum of Technology"),
          ("Ely Museum", r"Ely Museum"), ("Royston Museum", r"Royston Museum"), ("Wimpole Estate", r"Wimpole"),
          ("Anglesey Abbey", r"Anglesey Abbey"), ("Wicken Fen", r"Wicken Fen"), ("Audley End", r"Audley End"),
          ("Bury Lane Farm Shop", r"Bury Lane"), ("Wandlebury", r"Wandlebury"), ("Lynn Museum", r"Lynn Museum"),
          ("IWM Duxford", r"\bDuxford\b"), ("Shepreth Wildlife Park", r"Shepreth")]
SKIP_RE = re.compile(r"\b(parkrun|park run|weekly|every (?:mon|tues|wednes|thurs|fri|satur|sun)day|wednesday walks?|"
                     r"yoga|pilates|volunteer\w*|private hire|wedding|members'? (?:evening|event)|staff|corporate|"
                     r"home ed(?:ucation)?|toddle into)\b", re.I)
KIND_RU = {"exhibition": "выставка", "tour": "экскурсия", "family": "для семей", "seasonal": "сезонное событие",
           "talk": "лекция", "workshop": "мастер-класс", "late": "вечер в музее", "other": ""}
LINE_KINDS = set(KIND_RU) - {"other"}   # концерты и прочее — в обычных рубриках
LINES_MIN, LINES_MAX, PER_PLACE = 4, 6, 2
NEW_EXHIBITION_DAYS = 7


def place_of(c: dict) -> str | None:
    text = f"{c.get('venue') or ''} | {c.get('address') or ''}"
    return next((name for name, rx in PLACES if re.search(rx, text, re.I)), None)


def kind_of(c: dict) -> str:
    t = f"{c.get('title') or ''} {' '.join(c.get('categories') or [])}"
    title = c.get("title") or ""
    if re.search(r"\btours?\b|guided|stroll|\bwalk", title, re.I):
        return "tour"
    if re.search(r"\b(concert|piano|quartet|quartetto|trio|recital|chamber music|choir|orchestra|gig)\b", title, re.I):
        return "concert"   # концерты в музеях — обычные рубрики («На неделе»), не эта
    if re.search(r"\blates?\b|after hours|evening opening", title, re.I):
        return "late"
    if re.search(r"exhibition|display|gallery", title, re.I) or (c.get("long_running") and not re.search(
            r"talk|workshop|class|session|club|day\b", title, re.I)):
        return "exhibition"
    if re.search(r"halloween|christmas|santa|pumpkin|autumn|festive|apple|harvest|bonfire|firework", t, re.I):
        return "seasonal"
    if re.search(r"workshop|weaving|craft|make\b|class\b", t, re.I):
        return "workshop"
    if c.get("kids_tag") or re.search(r"family|kids|children|half[- ]term|trail", t, re.I):
        return "family"
    if re.search(r"talk|lecture|conversation", t, re.I):
        return "talk"
    return "other"


def candidates(pools, used_events: set[int], w) -> list[tuple[str, dict, str, str]]:
    from . import issue
    out, seen_ev = [], set()
    for cid, c in sorted(pools.candidates.items(), key=lambda kv: -(kv[1].get("importance") or 0)):
        if c["kind"] != "event" or c.get("access") == "restricted" or c.get("zone") not in issue.LISTED_ZONES:
            continue
        place = place_of(c)
        if not place or SKIP_RE.search(c["title"]) or c.get("regular_series") or c.get("participant"):
            continue
        if set(c["event_ids"]) & (used_events | seen_ev):
            continue
        sib = {e for s in c.get("siblings") or [] for e in s["event_ids"]}
        if sib & (used_events | seen_ev):
            continue
        kind = kind_of(c)
        if kind not in LINE_KINDS:
            continue
        first = min(issue.d(x[0]) for x in c["dates"])
        if kind == "exhibition" and not (w.issue - timedelta(days=NEW_EXHIBITION_DAYS) <= first <= w.end):
            continue   # выставка — только в первую неделю открытия (идущие давно — в «Выставках», если сильные)
        seen_ev.update(c["event_ids"])
        out.append((cid, c, place, kind))
    return out


def score(c: dict, kind: str, w) -> float:
    s = c.get("importance") or 2.5
    if kind in ("exhibition", "seasonal", "late"):
        s += 0.7   # новая выставка, сезонный повод, вечер в музее
    if c.get("kids_tag"):
        s += 0.3
    return s


def select(cands, w):
    ranked = sorted(cands, key=lambda x: (-score(x[1], x[3], w), x[1]["dates"][0][0]))
    chosen, per, why = [], {}, {}
    for cid, c, place, kind in ranked:
        if len(chosen) >= LINES_MAX:
            why[cid] = f"лимит рубрики ({LINES_MAX} строк)"
        elif per.get(place, 0) >= PER_PLACE:
            why[cid] = f"уже {PER_PLACE} строки от места {place}"
        else:
            chosen.append((cid, c, place, kind))
            per[place] = per.get(place, 0) + 1
    return sorted(chosen, key=lambda x: (x[1]["dates"][0][0], x[1]["dates"][0][2] or "")), why


ADMISSION_RE = re.compile(r"included in (?:the )?admission|with (?:\w+ ){0,3}admission|admission (?:applies|required)|"
                          r"normal (?:\w+ )?admission", re.I)   # 7d: «Free with normal Garden admission» (Botanic Garden)


def price_pair(c: dict) -> tuple[str, str]:
    from . import issue
    from .issue_fixes import _priced
    best = next(iter(_priced(c)), None)
    txt = (best[1] if best else c.get("price_text")) or ""
    if ADMISSION_RE.search(txt):
        return "with admission", "по входному билету"
    en, ru = issue.price_from_data({"price_text": best[1], "price_from": best[2]} if best else c)
    if best and best[1] == "Free":
        return "free", "бесплатно"
    if en == "price not listed":
        return "prices on the website", "цены на сайте"
    return en, ru


def build_items(pools, result: dict, w) -> tuple[list[dict], dict[str, str]]:
    from . import issue
    from tests.issue_rules.common import tier
    from tests.issue_rules.r11_primary_link import best_url
    used = {e for sec in result["sections"] if sec["rubric"] != "museums" for it in sec["items"] for i in it["ids"]
            if i in pools.candidates for e in pools.candidates[i]["event_ids"]}
    chosen, why = select(candidates(pools, used, w), w)
    if len(chosen) < LINES_MIN:
        for cid, *_ in chosen:
            why[cid] = f"меньше {LINES_MIN} кандидатов — рубрика не выводится"
        chosen = []
    items = []
    for cid, c, place, kind in chosen:
        en, ru = price_pair(c)
        venue = c.get("venue") or place
        zone = "" if c.get("zone") == "центр" else f" ({c.get('zone')})"
        b = best_url(c)
        items.append({"ids": [cid], "line": True, "auto": True, "place": place, "kind_ru": KIND_RU[kind],
                      "url": b if b and tier(b) < tier(c.get("url")) else c.get("url"),
                      "title_en": c["title"], "title_ru": c["title"], "where_en": venue, "where_ru": venue + zone,
                      "price_en": en, "price_ru": ru, "blurb_en": "", "blurb_ru": "",
                      "knowledge_en": [], "knowledge_ru": []})
    return items, why
