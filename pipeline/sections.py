"""Этап 7e (бриф, п. 6): «Секции: идёт набор» — подраздел «С детьми»; взрослые программы для начинающих — строкой в
«Спорт → Поучаствовать».

В базе — все найденные секции (kids_programmes kind=regular, с постоянной информацией); в выпуск — только с объявленным
набором (recruiting = open: «new players welcome», «registration open», бесплатное пробное занятие) или со стартом
новой группы в ближайшие 3 недели. Секции меняются редко, поэтому по кругу: одна и та же секция — не чаще раза в
8 недель (история выпусков issue_items). Строк: 2, а в начале триместров (сентябрь, январь, апрель — 3 недели после
начала) и перед каникулами (3 недели до них) — до 4. Не больше одной строки от провайдера и одного вида спорта, пока
есть другие. Доступ только для своих (университет, ученики школы) — нет. Строки без модели. Проверка 42.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta

ROTATION_WEEKS = 8
START_AHEAD_DAYS = 21
CAT_RU = {"football": "футбол", "netball": "нетбол", "rugby": "регби", "hockey": "хоккей на траве", "cricket": "крикет",
          "tennis": "теннис", "basketball": "баскетбол", "dodgeball": "доджбол", "swimming": "плавание",
          "gymnastics": "гимнастика", "athletics": "лёгкая атлетика", "martial_arts": "единоборства", "dance": "танцы",
          "drama": "театр", "music": "музыка", "chess": "шахматы", "arts": "творчество", "science": "наука",
          "multi_sport": "мультиспорт", "outdoor": "на природе", "other": "секция"}
CAT_EN = {"martial_arts": "martial arts", "multi_sport": "multi-sport", "outdoor": "outdoors", "other": "club"}


def busy_season(w) -> bool:
    """Начало триместра (3 недели после) или перед каникулами (3 недели до) — строк больше."""
    from . import knowledge, school_holidays
    for t in knowledge.term_starts():
        if timedelta(0) <= w.issue - t <= timedelta(days=21):
            return True
    return any(timedelta(0) <= date.fromisoformat(h["start"]) - w.issue <= timedelta(days=21)
               for h in school_holidays.upcoming(w.issue))


def shown_recently(con: sqlite3.Connection, w) -> dict[str, str]:
    from . import history
    history.init(con)
    since = (w.issue - timedelta(weeks=ROTATION_WEEKS)).isoformat()
    return {r[0]: r[1] for r in con.execute("""SELECT cand_id, max(issue_date) FROM issue_items WHERE issue_date < ?
            AND issue_date >= ? AND (cand_id LIKE 'S:%' OR cand_id LIKE 'B:%') GROUP BY cand_id""", (w.issue.isoformat(), since))}


def _line_ok(r) -> str | None:
    if (r["audience"] or "public") != "public":
        return "доступ только для своих (университет, ученики школы)"
    if r["zone"] in (None, "", "out_of_zone", "Кембриджшир, дальше часа"):
        return "вне зоны выпуска или зона не определена"
    return None


def kids_candidates(con: sqlite3.Connection, w) -> list[dict]:
    cols = {x[1] for x in con.execute("PRAGMA table_info(kids_programmes)")}
    if "recruiting" not in cols:
        return []
    out = []
    ahead = (w.issue + timedelta(days=START_AHEAD_DAYS)).isoformat()
    for r in con.execute("""SELECT * FROM kids_programmes WHERE kind='regular' AND coalesce(status,'active')='active'
                            ORDER BY provider_host, prog_id"""):
        starts = bool(r["date_start"] and w.issue.isoformat() <= r["date_start"] <= ahead)
        why = None
        if r["recruiting"] != "open" and not starts:
            why = {"waitlist": "лист ожидания", "closed": "набор закрыт"}.get(r["recruiting"], "набор не объявлен")
        why = why or _line_ok(r)
        out.append({"cid": f"S:{r['prog_id']}", "row": r, "why": why, "starts": starts,
                    "org": r["provider_host"], "cat": r["category"] or "other"})
    return out


def select(cands: list[dict], recent: dict[str, str], limit: int) -> tuple[list[dict], dict[str, str]]:
    why: dict[str, str] = {}
    chosen, orgs, cats = [], set(), set()
    pool = [c for c in cands if not c["why"]]
    for c in cands:
        if c["why"]:
            why[c["cid"]] = c["why"]
    for c in sorted(pool, key=lambda c: (not c["starts"], not c["row"]["trial_free"], c["row"]["zone"] != "центр")):
        if c["cid"] in recent:
            why[c["cid"]] = f"уже было в выпуске от {recent[c['cid']]} (по кругу — раз в {ROTATION_WEEKS} недель)"
        elif c["org"] in orgs:
            why[c["cid"]] = "уже есть строка от этого провайдера"
        elif c["cat"] in cats and len({x["cat"] for x in pool if x["cid"] not in recent}) > len(cats):
            why[c["cid"]] = "уже есть строка этого вида"
        elif len(chosen) >= limit:
            why[c["cid"]] = f"лимит подраздела ({limit})"
        else:
            chosen.append(c)
            orgs.add(c["org"])
            cats.add(c["cat"])
            why[c["cid"]] = "в выпуске"
    return chosen, why


def _meta(r, lang: str, starts: bool) -> str:
    parts = []
    if r["ages"]:
        parts.append(r["ages"] if lang == "en" else re.sub(r"\byears?\b|\byrs\b", "лет", r["ages"]))
    sched = " ".join(x for x in (r["days"], r["hours"]) if x)
    if sched:
        parts.append(sched)
    if starts:
        parts.append(f"new group from {r['date_start']}" if lang == "en" else f"новая группа с {r['date_start']}")
    if r["venue"]:
        parts.append(r["venue"] + ("" if r["zone"] == "центр" else f" ({r['zone']})"))
    if r["price"]:
        parts.append(re.sub(r"(£\d+)\.00\b", r"\1", r["price"]))
    if r["trial_free"]:
        parts.append("free taster" if lang == "en" else "пробное занятие бесплатно")
    return " · ".join(parts)


def build_items(con: sqlite3.Connection, pools, w) -> tuple[list[dict], dict[str, str]]:
    """Строки подраздела «Секции: идёт набор» (рубрика «С детьми»). Кандидаты — в пулы (kind section)."""
    limit = 4 if busy_season(w) else 2
    cands = kids_candidates(con, w)
    chosen, why = select(cands, shown_recently(con, w), limit)
    items = []
    for c in cands:
        r = c["row"]
        pools.candidates[c["cid"]] = {"kind": "section", "title": r["title"], "url": r["url"], "event_ids": [], "dates": [],
                                      "provider": r["provider"], "zone": r["zone"], "venue": r["venue"],
                                      "price_text": r["price"], "audience": r["audience"], "recruiting": r["recruiting"],
                                      "trial_free": bool(r["trial_free"]), "category": c["cat"], "starts": c["starts"],
                                      "recruiting_note": r["recruiting_note"]}
    for c in chosen:
        r = c["row"]
        kind_ru = CAT_RU.get(c["cat"], "секция")
        items.append({"ids": [c["cid"]], "line": True, "auto": True, "section_line": True,
                      "kind_ru": kind_ru, "kind_en": CAT_EN.get(c["cat"], c["cat"].replace("_", " ")),
                      "url": r["url"], "title_en": f"{r['provider']}: {r['title']}" if r["provider"] not in r["title"] else r["title"],
                      "title_ru": f"{r['provider']}: {r['title']}" if r["provider"] not in r["title"] else r["title"],
                      "meta_en": _meta(r, "en", c["starts"]), "meta_ru": _meta(r, "ru", c["starts"]),
                      "where_en": "", "where_ru": "", "price_en": "", "price_ru": "", "blurb_en": "", "blurb_ru": "",
                      "knowledge_en": [], "knowledge_ru": []})
    return items, why


# --- взрослые программы для начинающих (Couch to 5k, Back to Netball, walking football) — «Спорт → Поучаствовать» ---

BEGINNERS_RE = re.compile(r"walking football|walking netball|back to netball|couch to 5k|c25k|beginners?'? (?:run|netball|"
                          r"hockey|cricket|rowing|swim)|learn to (?:run|row|swim)|recreational netball", re.I)


def adult_items(con: sqlite3.Connection, pools, w) -> tuple[list[dict], dict[str, str]]:
    """Строки «Поучаствовать» для взрослых начинающих: courses с категорией sport (или по названию), с набором или
    стартом в ближайшие 3 недели; по кругу — раз в 8 недель; до 2 строк."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='courses'").fetchone():
        return [], {}
    ahead = (w.issue + timedelta(days=START_AHEAD_DAYS)).isoformat()
    recent = shown_recently(con, w)
    why, items = {}, []
    for r in con.execute("""SELECT * FROM courses WHERE status='active' AND (category='sport' OR title LIKE '%walking football%'
                            OR title LIKE '%back to netball%' OR title LIKE '%couch to 5k%') ORDER BY date_start""").fetchall():
        cid = f"B:{r['course_id']}"
        ok_time = r["kind"] == "drop_in" or (r["date_start"] and w.issue.isoformat() <= r["date_start"] <= ahead)
        if not ok_time:
            why[cid] = "старт не в ближайшие 3 недели"
        elif r["zone"] in (None, "", "out_of_zone"):
            why[cid] = "вне зоны"
        elif cid in recent:
            why[cid] = f"уже было в выпуске от {recent[cid]}"
        elif len(items) >= 2:
            why[cid] = "лимит (2 строки)"
        else:
            why[cid] = "в выпуске"
        pools.candidates[cid] = {"kind": "adult_programme", "title": r["title"], "url": r["url"], "event_ids": [],
                                 "dates": [(r["date_start"], r["date_start"], r["time_start"])] if r["date_start"] else [],
                                 "provider": r["provider"], "zone": r["zone"], "venue": r["venue"], "participant": True,
                                 "price_text": r["price"]}
        if why[cid] != "в выпуске":
            continue
        sched = " ".join(x for x in (r["days"], r["hours"]) if x)
        start_ru = f"старт {r['date_start']}" if r["kind"] != "drop_in" and r["date_start"] else ""
        start_en = f"starts {r['date_start']}" if start_ru else ""
        place = (r["venue"] or "") + ("" if r["zone"] in ("центр", None) else f" ({r['zone']})")
        price = re.sub(r"(£\d+)\.00\b", r"\1", r["price"] or "")
        items.append({"ids": [cid], "line": True, "auto": True, "adult_line": True, "url": r["url"],
                      "title_en": r["title"], "title_ru": r["title"],
                      "meta_en": " · ".join(x for x in ("for beginners", start_en, sched, place, price) if x),
                      "meta_ru": " · ".join(x for x in ("для начинающих", start_ru, sched, place, price) if x),
                      "where_en": "", "where_ru": "", "price_en": "", "price_ru": "", "blurb_en": "", "blurb_ru": "",
                      "knowledge_en": [], "knowledge_ru": []})
    return items, why
