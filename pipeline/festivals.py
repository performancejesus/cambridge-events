"""Этап 7g: рубрика «Фестивали» (новая, решено 11.10) — календарь ближайших фестивалей из recurring_events.

Строка без модели: название — даты · город · статус («ожидаем» / «даты объявлены» / «в продаже»), ссылка на сайт
фестиваля. В рубрику попадает фестиваль, когда до него меньше 10 недель (`WEEKS`) или открыта продажа; «ожидаем»
без дат — если обычный месяц проведения наступает в эти 10 недель (дата не выдумывается: только «обычно в …»).
Фестиваль — по названию (Festival, Pride); скачки Newmarket (July Festival, Guineas) — в «Спорт», «A Festival of Nine
Lessons» — служба, не фестиваль (calendar=false в data/recurring_events.json). Jazz Festival (official_only) без
подтверждения на сайте фестиваля не показывается (решение 01.10).
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

from .db import ROOT

WEEKS = 10
FEST_RE = re.compile(r"\bfestival\b|\bpride\b|\bfest\b|\bfair\b|\bfayre\b", re.I)   # ярмарки — тоже календарь
MONTHS_RU_IN = ["январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре",
                "ноябре", "декабре"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
STAGE = {"ожидаем": ("expected", "ожидаем"), "дата объявлена": ("dates announced", "даты объявлены"),
         "в продаже": ("tickets on sale", "в продаже")}


def calendar_ids() -> set[str]:
    out = set()
    for r in json.loads((ROOT / "data" / "recurring_events.json").read_text()):
        if r.get("calendar") is False:
            continue
        if r.get("calendar") or FEST_RE.search(r["name"]):
            out.add(r["rec_id"])
    return out


def due(r, issue: date) -> tuple[bool, str]:
    """(показывать, почему) по статусу и датам."""
    keys = r.keys()
    stage = r["stage"] if "stage" in keys else None
    if stage == "не проводится":
        return False, "не проводится"
    if ("official_only" in keys and r["official_only"]) and r["found_source"] != r["official_url"]:
        return False, "ждём подтверждения на сайте фестиваля"
    since = (r["stage_since"] or "")[:10] if "stage_since" in keys else ""
    if r["found_date"] and (r["found_date_end"] or r["found_date"])[:10] < issue.isoformat():
        return False, "прошёл"   # сначала — не прошёл ли (Bury Lit Festival 8–11.10 в выпуске 15.10)
    if r["found_date"] and stage in ("дата объявлена", "в продаже") and since and \
            since >= (issue - timedelta(days=21)).isoformat():
        return True, "даты или продажа объявлены недавно"   # анонс (как правило 39), даже если до начала далеко
    if r["found_date"]:
        start = date.fromisoformat(r["found_date"][:10])
        end = date.fromisoformat((r["found_date_end"] or r["found_date"])[:10])
        if end < issue:
            return False, "прошёл"
        if (start - issue).days <= WEEKS * 7:
            return True, f"до начала {(start - issue).days} дн."
        if stage == "в продаже":
            return True, "продажа открыта"
        return False, f"до начала больше {WEEKS} недель"
    months = [int(m) for m in (r["expected_month"] or "").split(",") if m.strip().isdigit()]
    horizon = [(issue + timedelta(days=i)).month for i in range(0, WEEKS * 7, 7)]
    if stage in (None, "ожидаем") and months and months[0] in horizon and months[0] != issue.month - 1:
        return True, "обычно проходит в эти недели"
    return False, "дат нет"


def build_items(con, pools, result: dict, w) -> tuple[list[dict], dict[str, str]]:
    """Строки рубрики и причины для редакторской версии (rec_id → причина)."""
    from .issue import TOWN_RU, _day
    ids = calendar_ids()
    placed = {e for sec in result["sections"] for it in sec["items"] for i in it["ids"]
              for e in (pools.candidates.get(i) or {}).get("event_ids", [])}
    items, why = [], {}
    rows = con.execute("SELECT * FROM recurring_events ORDER BY coalesce(found_date, '9999'), rec_id").fetchall()
    for r in rows:
        if r["rec_id"] not in ids:
            continue
        ok, reason = due(r, w.issue)
        if not ok:
            why[r["rec_id"]] = reason
            continue
        if r["event_id"] and r["event_id"] in placed:
            why[r["rec_id"]] = "уже в выпуске полной карточкой"
            continue
        stage = r["stage"] or "ожидаем"
        st_en, st_ru = STAGE.get(stage, (stage, stage))
        town = r["town"] or ""
        line = {}
        for lang in ("en", "ru"):
            if r["found_date"]:
                a = date.fromisoformat(r["found_date"][:10])
                b = date.fromisoformat((r["found_date_end"] or r["found_date"])[:10])
                when = _day(a, lang, weekday=False, year=a.year != w.issue.year) + (
                    f" – {_day(b, lang, weekday=False, year=b.year != w.issue.year)}" if b != a else "")
            else:
                m = int((r["expected_month"] or "1").split(",")[0])
                when = f"usually in {MONTHS_EN[m - 1]}" if lang == "en" else f"обычно в {MONTHS_RU_IN[m - 1]}"
            place = town if lang == "en" else TOWN_RU.get(town, "Кембридж" if town == "Cambridge" else town)
            status = st_en if lang == "en" else st_ru
            note = (r["on_sale_note"] or "") if lang == "ru" and stage == "в продаже" else ""
            line[lang] = " · ".join(x for x in (when, place, status) if x) + (f" ({note})" if note and len(note) < 80 else "")
            desc = r["description"] if lang == "ru" else r["description_en"]
            if desc and r["tags"] and "quirky" in r["tags"]:   # необычная традиция — одна фраза, что это за обычай (правило 40)
                line[lang] += " — " + re.split(r"(?<=[.!?])\s", desc)[0]
        cid = f"R:{r['rec_id']}"
        pools.candidates[cid] = {"kind": "festival", "title": r["name"], "url": r["official_url"], "event_ids":
                                 [r["event_id"]] if r["event_id"] else [], "dates": [(r["found_date"],
                                 r["found_date_end"] or r["found_date"], None)] if r["found_date"] else [],
                                 "rec_id": r["rec_id"], "stage": stage, "importance": None, "sources": ["recurring"],
                                 "types": ["festival"], "category": "traditions"}
        items.append({"ids": [cid], "title_en": r["name"], "title_ru": r["name"], "meta_en": line["en"],
                      "meta_ru": line["ru"], "url": r["official_url"], "festival_line": True, "line": True,
                      "where_en": "", "where_ru": "", "price_en": "", "price_ru": "", "blurb_en": "", "blurb_ru": "",
                      "knowledge_en": [], "knowledge_ru": [], "why_en": "", "why_ru": ""})
        why[r["rec_id"]] = "в выпуске: " + reason
    return items, why
