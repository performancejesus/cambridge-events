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
# Месяц впереди, сокращённо: «Oct 22 - Nov 1 2026» (Cambridge Film Festival), «October 3rd–5th, 2026».
_MON = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
MONTH_FIRST_RE = re.compile(rf"\b{_MON}\s+({_DAY})(?:\s*(?:-|–|to)\s*(?:{_MON}\s+)?({_DAY}))?\s*,?\s+(20\d\d)\b")


def seed(con: sqlite3.Connection) -> None:
    for r in json.loads(SEED.read_text()):
        con.execute("""INSERT INTO recurring_events(rec_id, name, expected_month, official_url, check_method, patterns, note,
            tickets, page_date, manual_start, manual_end, venue, postcode) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(rec_id) DO UPDATE SET name=excluded.name, expected_month=excluded.expected_month,
            official_url=excluded.official_url, check_method=excluded.check_method, patterns=excluded.patterns,
            note=excluded.note, tickets=excluded.tickets, page_date=excluded.page_date,
            manual_start=excluded.manual_start, manual_end=excluded.manual_end, venue=excluded.venue,
            postcode=excluded.postcode""",
                    (r["rec_id"], r["name"], r["month"], r["url"], r["method"], json.dumps(r["patterns"]), r.get("note"),
                     int(bool(r.get("tickets"))), r.get("page_date"), r.get("manual_start") or None,
                     r.get("manual_end") or None, r.get("venue"), r.get("postcode")))


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
    for mon1, day1, mon2, day2, year in MONTH_FIRST_RE.findall(re.sub(r"\s+", " ", text)):
        try:
            start = datetime.strptime(f"{int(day1.rstrip('stndrh'))} {mon1} {year}", "%d %b %Y").date()
            end = datetime.strptime(f"{int(day2.rstrip('stndrh'))} {mon2 or mon1} {year}", "%d %b %Y").date() if day2 else None
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
        # 0) дата, внесённая вручную (data/recurring_events.json: manual_start / manual_end)
        if r["manual_start"] and r["manual_start"] >= today:
            found, end, source = r["manual_start"], r["manual_end"], "вручную"
        # 1) уже есть в базе событий (из фидов или статей)
        for e in ([] if found else con.execute(
                "SELECT * FROM events WHERE date_start BETWEEN ? AND ? AND status NOT IN ('cancelled') AND source_type!='recurring'",
                (today, horizon))):
            if rx.search(e["title"]) and e["date_start"][5:7] in months:
                found, end, source, eid = e["date_start"], e["date_end"], f"событие #{e['event_id']}", e["event_id"]
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
        if end == found:  # однодневное
            end = None
        # на странице только окончание (Folk Festival) — начало ждём вручную, событие не создаём
        only_end = None
        if found and source == r["official_url"] and r["page_date"] == "end" and not end:
            only_end, found, source = found, None, None
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
        own = con.execute("SELECT * FROM events WHERE event_id=? AND source_type='recurring'", (r["event_id"],)).fetchone() \
            if r["event_id"] else None
        if found and not eid and own:  # событие из таблицы уже есть — уточняем даты (например, внесено начало)
            eid = own["event_id"]
            if (own["date_start"], own["date_end"]) != (found, end):
                con.execute("UPDATE events SET date_start=?, date_end=?, last_seen_at=? WHERE event_id=?",
                            (found, end, run_id, eid))
        if own:  # место из таблицы (для зоны), если у события его нет
            con.execute("UPDATE events SET venue_name=coalesce(venue_name, ?), postcode=coalesce(postcode, ?) WHERE event_id=?",
                        (r["venue"], r["postcode"], own["event_id"]))
        if found and not eid:  # дата есть, события нет — создаём: с билетами announced, без — scheduled
            status = "announced" if r["tickets"] else "scheduled"
            cur = con.execute("""INSERT INTO events(title, norm_title, date_start, date_end, venue_name, postcode, status,
                source_type, url, first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                              (r["name"], norm_title(r["name"]), found, end, r["venue"], r["postcode"], status, "recurring",
                               source if source.startswith("http") else r["official_url"], run_id, run_id))
            eid = cur.lastrowid
            con.execute("INSERT INTO status_history(event_id, status, changed_at, source_id, note) VALUES (?,?,?,?,?)",
                        (eid, status, run_id, None, f"ежегодное {r['rec_id']}: дата найдена ({source})"))
        con.execute("""UPDATE recurring_events SET last_checked_at=?, found_date=coalesce(?, found_date),
            found_date_end=CASE WHEN ? IS NOT NULL THEN ? ELSE coalesce(?, found_date_end) END,
            found_source=coalesce(?, found_source), event_id=coalesce(?, event_id) WHERE rec_id=?""",
                    (run_id, found, found, end, only_end, source if found else None, eid, r["rec_id"]))
        row = con.execute("SELECT * FROM recurring_events WHERE rec_id=?", (r["rec_id"],)).fetchone()
        if row["found_date"]:
            status = "дата найдена" if row["found_source"] != "вручную" else "вручную: дата внесена"
        elif row["found_date_end"]:
            status = "ждём начало (вручную)"
        else:
            status = "вручную" if r["check_method"] == "manual" else "ожидаем"
        report.append({"rec_id": r["rec_id"], "name": r["name"], "month": r["expected_month"],
                       "found_date": row["found_date"], "found_date_end": row["found_date_end"],
                       "source": source if found else (source or row["found_source"]), "status": status})
    return report
