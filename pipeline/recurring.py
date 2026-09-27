"""Ежегодные события: поиск даты текущего цикла в базе событий, на официальной странице и в статьях."""

from __future__ import annotations

import json
import re
from html import unescape
import sqlite3
from datetime import date, datetime, timedelta, timezone

from collectors.http import Disallowed, FetchError, PoliteClient

from .db import ROOT
from .normalize import norm_title

SEED = ROOT / "data" / "recurring_events.json"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_SEP = r"\s*(?:,|-|–|&|and|to)\s*(?:[A-Z][a-z]+day\s+)?"
# Серия дней одного месяца или два месяца: «5 December 2026», «Saturday 5th December 2026», «25–26 September 2026»,
# «15th, 16th, 17th January 2027», «Wednesday 24 June to Sunday 28 June 2027», «30 July – 2 August 2027».
DATE_RE = re.compile(rf"\b({_DAY}(?:{_SEP}{_DAY})*)(?:\s+({MONTHS}))?(?:{_SEP}({_DAY}))?\s+({MONTHS})\s*,?\s*(20\d\d)\b")


def seed(con: sqlite3.Connection) -> None:
    for r in json.loads(SEED.read_text()):
        con.execute("""INSERT INTO recurring_events(rec_id, name, expected_month, official_url, check_method, patterns, note)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(rec_id) DO UPDATE SET name=excluded.name,
            expected_month=excluded.expected_month, official_url=excluded.official_url,
            check_method=excluded.check_method, patterns=excluded.patterns""",
                    (r["rec_id"], r["name"], r["month"], r["url"], r["method"], json.dumps(r["patterns"]), r.get("note")))


def dates_in(text: str, months: set[str], today: str) -> list[tuple[str, str | None]]:
    """(начало, конец) будущих дат в тексте, месяц начала которых ожидаем."""
    out = []
    for days, mon1, day2, mon2, year in DATE_RE.findall(re.sub(r"\s+", " ", text)):
        nums = re.findall(r"\d{1,2}", days)
        try:
            if mon1:  # «24 June to 28 June 2027» / «30 July – 2 August 2027»
                start = datetime.strptime(f"{nums[0]} {mon1} {year}", "%d %B %Y").date()
                end = datetime.strptime(f"{day2 or nums[-1]} {mon2} {year}", "%d %B %Y").date() if day2 else None
            else:
                start = datetime.strptime(f"{nums[0]} {mon2} {year}", "%d %B %Y").date()
                end = datetime.strptime(f"{nums[-1]} {mon2} {year}", "%d %B %Y").date() if len(nums) > 1 else None
        except ValueError:
            continue
        if f"{start.month:02d}" in months and start.isoformat() >= today and start.year <= date.today().year + 1:
            out.append((start.isoformat(), end.isoformat() if end and end > start else None))
    return sorted(set(out))


def _page_text(http: PoliteClient, url: str) -> str:
    html = http.get(url).text
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return unescape(re.sub(r"<[^>]+>", " ", html))


def check(con: sqlite3.Connection, http: PoliteClient, run_id: str, fetch_pages: bool = True) -> list[dict]:
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=400)).isoformat()
    report = []
    for r in con.execute("SELECT * FROM recurring_events ORDER BY rec_id").fetchall():
        months = set(r["expected_month"].split(","))
        pats = json.loads(r["patterns"])
        rx = re.compile("|".join(re.escape(p) for p in pats), re.I)
        found = source = end = None
        eid = None
        # 1) уже есть в базе событий (из фидов или статей)
        for e in con.execute("SELECT * FROM events WHERE date_start BETWEEN ? AND ? AND status NOT IN ('cancelled')",
                             (today, horizon)):
            if rx.search(e["title"]) and e["date_start"][5:7] in months:
                found, source, eid = e["date_start"], f"событие #{e['event_id']}", e["event_id"]
                break
        # 2) официальная страница (если robots.txt разрешает; защищённые сайты — method=manual)
        if not found and fetch_pages and r["check_method"] in ("page", "page_curl"):
            try:
                ds = dates_in(_page_text(http, r["official_url"]), months, today)
                if ds:
                    found, source = ds[0][0], r["official_url"]
                    end = ds[0][1]
            except (Disallowed, FetchError) as ex:
                source = f"страница недоступна: {ex}"
        # 3) статьи (заголовок и RSS-анонс)
        if not found:
            for a in con.execute("SELECT * FROM articles WHERE published >= ?", ((date.today() - timedelta(days=120)).isoformat(),)):
                txt = f"{a['title']} {a['summary'] or ''}"
                if rx.search(txt):
                    ds = dates_in(txt, months, today)
                    if ds:
                        found, source = ds[0][0], a["url"]
                        end = ds[0][1]
                        break
        if found and not eid:  # дата есть, события нет — создаём «анонсировано»
            cur = con.execute("""INSERT INTO events(title, norm_title, date_start, date_end, status, source_type, url,
                first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                              (r["name"], norm_title(r["name"]), found, end, "announced", "recurring",
                               source if source.startswith("http") else r["official_url"], run_id, run_id))
            eid = cur.lastrowid
            con.execute("INSERT INTO status_history(event_id, status, changed_at, source_id, note) VALUES (?,?,?,?,?)",
                        (eid, "announced", run_id, None, f"ежегодное {r['rec_id']}: дата найдена ({source})"))
        con.execute("UPDATE recurring_events SET last_checked_at=?, found_date=coalesce(?, found_date), found_source=coalesce(?, found_source), event_id=coalesce(?, event_id) WHERE rec_id=?",
                    (run_id, found, source if found else None, eid, r["rec_id"]))
        report.append({"rec_id": r["rec_id"], "name": r["name"], "month": r["expected_month"],
                       "found_date": found or r["found_date"], "source": source if found else (source or r["found_source"]),
                       "status": "дата найдена" if (found or r["found_date"]) else ("вручную" if r["check_method"] == "manual" else "ожидаем")})
    return report
