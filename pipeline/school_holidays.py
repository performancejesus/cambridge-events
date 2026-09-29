"""Школьные каникулы Cambridgeshire (этап 6c, «Постоянное отслеживание»): все каникулы учебного года — в recurring_events.

Источник — страница сроков четвертей совета (term dates). Разбор без модели: блоки «School term and holiday dates
YYYY-YYYY», строки «Half Term: …», «Christmas Holidays: …», «Easter Holidays: …», «Summer Holiday: … onwards»
(конец летних каникул — день перед началом следующей осенней четверти). Результат — data/school_holidays.json и строки
recurring_events с rec_id H-<учебный год>-<каникулы>. Перепроверка — в еженедельном прогоне (check_recurring).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

from .db import ROOT

URL = ("https://www.cambridgeshire.gov.uk/residents/children-and-families/schools-learning/"
       "school-term-dates-closures/school-term-dates")
DATA = ROOT / "data" / "school_holidays.json"
NAMES = {"october_half_term": "Октябрьские каникулы (half term)", "christmas": "Рождественские каникулы",
         "february_half_term": "Февральские каникулы (half term)", "easter": "Пасхальные каникулы",
         "may_half_term": "Майские каникулы (half term)", "summer": "Летние каникулы"}
D = r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day (\d{1,2}) ([A-Z][a-z]+)"


def _d(day: str, month: str, year: int) -> date:
    return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()


def parse(text: str) -> list[dict]:
    out = []
    blocks = re.split(r"School term and holiday dates (\d{4})-(\d{4})", text)
    for i in range(1, len(blocks) - 2, 3):
        y1, y2, body = int(blocks[i]), int(blocks[i + 1]), blocks[i + 2]
        year = f"{y1}-{y2 % 100:02d}"
        half = re.findall(rf"Half Term: {D} to {D}", body)
        # порядок в блоке: осень (октябрь), весна (февраль), лето (май)
        for key, (a, am, b, bm), y in zip(("october_half_term", "february_half_term", "may_half_term"), half, (y1, y2, y2)):
            out.append({"key": key, "year": year, "start": _d(a, am, y).isoformat(), "end": _d(b, bm, y).isoformat()})
        m = re.search(rf"Christmas Holidays: {D} to {D}", body)
        if m:
            out.append({"key": "christmas", "year": year, "start": _d(m[1], m[2], y1).isoformat(),
                        "end": _d(m[3], m[4], y1 if m[4] == "December" else y2).isoformat()})
        m = re.search(rf"Easter Holidays: {D} to {D}", body)
        if m:
            out.append({"key": "easter", "year": year, "start": _d(m[1], m[2], y2).isoformat(), "end": _d(m[3], m[4], y2).isoformat()})
        m = re.search(rf"Summer Holiday: {D} onwards", body)
        if m:
            nxt = re.search(rf"School term and holiday dates {y2}-\d{{4}}.*?Autumn term dates {y2} \| {D}", text)
            start = _d(m[1], m[2], y2)
            end = (_d(nxt[1], nxt[2], y2) - timedelta(days=1)) if nxt else date(y2, 8, 31)
            out.append({"key": "summer", "year": year, "start": start.isoformat(), "end": end.isoformat()})
    return out


def refresh(con: sqlite3.Connection, http) -> dict:
    from collectors.llmlist import visible_text
    text, _ = visible_text(http.get(URL).text)
    text = re.sub(r"(?:\| )+", "| ", text)
    hols = parse(text)
    DATA.write_text(json.dumps({"_comment": "Каникулы школ Cambridgeshire (совет, term dates). Академии и частные школы "
                                            "могут отличаться.", "source": URL, "holidays": hols}, ensure_ascii=False, indent=1))
    return store(con, hols)


def store(con: sqlite3.Connection, hols: list[dict]) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for h in hols:
        rid = f"H-{h['year']}-{h['key']}"
        con.execute("""INSERT INTO recurring_events(rec_id, name, expected_month, official_url, check_method, patterns,
            last_checked_at, found_date, found_date_end, found_source, note, tickets)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,0)
            ON CONFLICT(rec_id) DO UPDATE SET found_date=excluded.found_date, found_date_end=excluded.found_date_end,
            last_checked_at=excluded.last_checked_at""",
                    (rid, f"{NAMES[h['key']]} {h['year']}", h["start"][5:7], URL, "page", "[]", now, h["start"], h["end"],
                     URL, "школьные каникулы Cambridgeshire (этап 6c) — не событие, календарь для детских программ"))
    return {"school_holidays": len(hols)}


def load() -> list[dict]:
    return json.loads(DATA.read_text())["holidays"] if DATA.exists() else []


def upcoming(today: date | None = None) -> list[dict]:
    today = today or date.today()
    return [h for h in load() if h["end"] >= today.isoformat()]
