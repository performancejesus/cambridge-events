"""Загрузка прогона коллекторов в events.db: сырые записи → дедупликация → события → жизненный цикл."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import venues
from .geo import lookup, zone_for_postcode
from .normalize import end_date, minutes, norm_title, norm_venue, parse_price, split_datetime, title_similarity

# Источники-продавцы билетов: событие у них = продажа открыта.
TICKETING = {"S006", "S007", "S008", "S011", "S017", "S021", "S072", "S091", "S128", "S129"}
# Событие платное/по билетам, но билеты продаются не у нас в источниках (футбол, ADC, пивной фестиваль):
# пока продажа не замечена — announced. Остальные события без билетов и цены — scheduled.
TICKETS_ELSEWHERE = {"S018", "S032", "S042", "S123"}
# Чьи поля предпочитать при сведении (официальные площадки и организаторы — раньше агрегаторов).
SOURCE_RANK = ["S042", "S011", "S072", "S018", "S123", "S032", "S033", "S038", "S047", "S021", "S091", "S005",
               "S006", "S007", "S128", "S129", "S008"]
# Агрегаторы, у которых собирается только первая страница списка: её состав плавает, пропажа ≠ отмена.
PARTIAL_LISTING = {"S006", "S007", "S008", "S128", "S129"}
HISTORY_DAYS = 60            # старше — в события не превращаем (в сыром виде храним)
MATCH_MIN, MATCH_MIN_NO_VENUE = 0.8, 0.9
# «Cambridge» без адреса (подборки «Various, Cambridge», экскурсии по частным домам с одной улицей):
# зона «центр» условно, с пометкой address_unknown (решение после этапа 3, часть 2).
CITY_ONLY_RE = re.compile(r"(^|,)\s*Cambridge\s*(,|$)", re.I)
# Фестивали на нескольких площадках (Cambridge Poetry Festival): «разные площадки, Кембридж», зона «центр».
MULTI_VENUE_RE = re.compile(r"^\s*(various|multiple (locations|venues)|several venues|разные площадки)\b", re.I)
STATUS_PRIORITY = ["cancelled", "postponed", "disappeared", "past", "sold_out", "on_sale", "announced", "scheduled"]


def rank(source_id: str) -> int:
    return SOURCE_RANK.index(source_id) if source_id in SOURCE_RANK else len(SOURCE_RANK)


def item_key(d: dict) -> str:
    return d.get("external_id") or d.get("url") or f"{d['title']}|{d.get('start')}"


# --- 1. сырые записи ---

def load_run(con: sqlite3.Connection, raw_dir: Path) -> dict:
    run = json.loads((raw_dir / "_run.json").read_text())
    entries = {k: v for k, v in run.items() if not k.startswith("_")}
    run_id = run.get("_run_id") or min(r["started_at"] for r in entries.values())
    stats = {"run_id": run_id, "new_raw": 0, "seen_raw": 0, "disappeared": 0, "new_articles": 0}
    for sid, r in entries.items():
        if r["started_at"] < run_id:  # источник не запускался в этом прогоне — его старый файл не перечитываем
            continue
        items = 0
        if r["ok"]:
            path = next(raw_dir.glob(f"{sid}_*.json"))
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            for d in json.loads(path.read_text()):
                items += 1
                key = item_key(d)
                row = con.execute("SELECT raw_id FROM raw_items WHERE source_id=? AND item_key=?", (sid, key)).fetchone()
                vals = (d["kind"], d["title"], d["url"], d["start"], d["end"], int(bool(d["all_day"])), d["venue"],
                        d["address"], d["postcode"], d["lat"], d["lon"], d["price"], d["status"], d["organizer"],
                        json.dumps(d["categories"], ensure_ascii=False), d["summary"], d["published"])
                if row:
                    con.execute("""UPDATE raw_items SET kind=?, title=?, url=?, start=?, "end"=?, all_day=?, venue=?,
                        address=?, postcode=?, lat=?, lon=?, price=?, status=?, organizer=?, categories=?, summary=?,
                        published=?, last_seen_at=?, disappeared_at=NULL WHERE raw_id=?""", vals + (run_id, row[0]))
                    stats["seen_raw"] += 1
                else:
                    con.execute("""INSERT INTO raw_items(kind, title, url, start, "end", all_day, venue, address,
                        postcode, lat, lon, price, status, organizer, categories, summary, published, source_id,
                        item_key, first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                vals + (sid, key, run_id, run_id))
                    stats["new_raw"] += 1
                if d["kind"] == "article" and d["url"]:
                    cur = con.execute("""INSERT OR IGNORE INTO articles(source_id, url, title, published, summary,
                        first_seen_at) VALUES (?,?,?,?,?,?)""", (sid, d["url"], d["title"], d["published"], d["summary"], run_id))
                    stats["new_articles"] += cur.rowcount
            # пропало из источника до своей даты → отметка для ручной проверки
            # (кроме агрегаторов с неполным списком и событий сегодняшнего дня — они уходят из афиш сами)
            if sid not in PARTIAL_LISTING:
                cur = con.execute("""UPDATE raw_items SET disappeared_at=? WHERE source_id=? AND kind='event'
                    AND item_key NOT LIKE 'article:%' AND last_seen_at < ? AND disappeared_at IS NULL
                    AND substr(start,1,10) >= ?""", (run_id, sid, run_id, tomorrow))
                stats["disappeared"] += cur.rowcount
        con.execute("INSERT OR REPLACE INTO runs(run_id, source_id, ok, items, error) VALUES (?,?,?,?,?)",
                    (run_id, sid, int(r["ok"]), items, r.get("error")))
    return stats


# --- 2. дедупликация ---

def _venue_match(v1: str, p1: str | None, v2: str, p2: str | None) -> bool | None:
    """True/False, если есть что сравнивать; None — у одной из сторон площадка неизвестна."""
    if p1 and p2 and p1.replace(" ", "") == p2.replace(" ", ""):
        return True
    if not v1 or not v2:
        return None
    return v1 == v2 or v1 in v2 or v2 in v1


def dedupe(con: sqlite3.Connection, run_id: str) -> dict:
    cutoff = (date.today() - timedelta(days=HISTORY_DAYS)).isoformat()
    stats = {"new_events": 0, "merged": 0}
    raws = con.execute("""SELECT * FROM raw_items WHERE kind='event' AND event_id IS NULL
        AND substr(coalesce("end", start),1,10) >= ? ORDER BY source_id, start""", (cutoff,)).fetchall()
    for r in sorted(raws, key=lambda r: rank(r["source_id"])):
        d, t = split_datetime(r["start"])
        if not d:
            continue
        if r["all_day"]:
            t = None
        nt, nv = norm_title(r["title"]), norm_venue(r["venue"])
        best, best_score = None, 0.0
        for e in con.execute("SELECT * FROM events WHERE date_start=?", (d,)):
            srcs = {x[0] for x in con.execute("SELECT source_id FROM event_sources WHERE event_id=?", (e["event_id"],))}
            if r["source_id"] in srcs:
                continue
            vm = _venue_match(nv, r["postcode"], norm_venue(e["venue_name"]), e["postcode"])
            if vm is False:
                continue
            m1, m2 = minutes(t), minutes(e["time_start"])
            if m1 is not None and m2 is not None and abs(m1 - m2) > 90:
                continue
            score = title_similarity(nt, e["norm_title"])
            if score >= (MATCH_MIN if vm else MATCH_MIN_NO_VENUE) and score > best_score:
                best, best_score = e, score
        if best:
            eid = best["event_id"]
            stats["merged"] += 1
        else:
            de, te = end_date(r["start"], r["end"]), split_datetime(r["end"])[1]
            if de == d and te and te < "06:00":
                te = None
            cur = con.execute("""INSERT INTO events(title, norm_title, date_start, time_start, date_end, time_end,
                venue_name, postcode, status, source_type, url, first_seen_at, last_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (r["title"], nt, d, t, de, None if r["all_day"] else te, r["venue"], r["postcode"],
                               "announced", "article" if r["item_key"].startswith("article:") else "feed",
                               r["url"], r["first_seen_at"], r["last_seen_at"]))
            eid = cur.lastrowid  # первую запись в status_history делает refresh() — уже с итоговым статусом
            stats["new_events"] += 1
        con.execute("UPDATE raw_items SET event_id=? WHERE raw_id=?", (eid, r["raw_id"]))
        art = r["item_key"].split(":")[1] if r["item_key"].startswith("article:") else None
        con.execute("INSERT OR IGNORE INTO event_sources(event_id, source_id, url, raw_id, article_id) VALUES (?,?,?,?,?)",
                    (eid, r["source_id"], r["url"] or "", r["raw_id"], art))
    return stats


# --- 2b. ручные склейки (data/manual_merges.json): дубли, которые не видит автоматическое сравнение ---

MERGES = Path(__file__).resolve().parent.parent / "data" / "manual_merges.json"


def apply_merges(con: sqlite3.Connection) -> dict:
    """Событие-дубль переносится в основное: записи источников, статьи, обновления; сам дубль удаляется."""
    stats = {"manual_merged": 0}
    find = lambda k: con.execute("SELECT event_id FROM events WHERE date_start=? AND title=?", (k["date"], k["title"])).fetchone()
    for rule in json.loads(MERGES.read_text()) if MERGES.exists() else []:
        keep = find(rule["keep"])
        if not keep:
            continue
        for m in rule["merge"]:
            dup = find(m)
            if not dup or dup[0] == keep[0]:
                continue
            k, d = keep[0], dup[0]
            con.execute("UPDATE raw_items SET event_id=? WHERE event_id=?", (k, d))
            con.execute("""INSERT OR IGNORE INTO event_sources(event_id, source_id, url, raw_id, article_id)
                SELECT ?, source_id, url, raw_id, article_id FROM event_sources WHERE event_id=?""", (k, d))
            con.execute("DELETE FROM event_sources WHERE event_id=?", (d,))
            for table in ("event_updates", "recurring_events"):
                con.execute(f"UPDATE {table} SET event_id=? WHERE event_id=?", (k, d))
            con.execute("DELETE FROM venue_lookups WHERE event_id=?", (d,))
            con.execute("DELETE FROM status_history WHERE event_id=?", (d,))
            con.execute("DELETE FROM events WHERE event_id=?", (d,))
            stats["manual_merged"] += 1
    return stats


# --- 3. сведение полей и жизненный цикл ---

def _status(raws: list, updates: set[str], price_from, end_date: str, today: str,
            tickets_expected: bool) -> tuple[str, str | None]:
    """announced — билеты ожидаются, но продажа не открыта; scheduled — событие без билетов (лекции, ярмарки)."""
    st = {r["status"] for r in raws}
    if "cancelled" in st or "cancelled" in updates:
        return "cancelled", None
    if "postponed" in st or "rescheduled" in st or "postponed" in updates:
        return "postponed", None
    if raws and all(r["disappeared_at"] for r in raws):
        return "disappeared", raws[0]["source_id"]
    if end_date < today:
        return "past", None
    ticketing = [r for r in raws if r["source_id"] in TICKETING]
    if ticketing and all(r["status"] == "sold_out" for r in ticketing):
        return "sold_out", ticketing[0]["source_id"]
    if ticketing or (price_from or 0) > 0 or "on_sale" in updates or "on_sale" in st:
        return "on_sale", (ticketing[0]["source_id"] if ticketing else None)
    if price_from == 0 or "no_tickets" in st:
        return "scheduled", None
    if tickets_expected:
        return "announced", None
    return "scheduled", None


def _tickets_expected(con, e, raws: list, today: str) -> bool:
    if e["on_sale_date"] and e["on_sale_date"] > today:
        return True
    if any(r["source_id"] in TICKETS_ELSEWHERE or r["status"] == "tickets_expected" for r in raws):
        return True
    rec = con.execute("SELECT tickets FROM recurring_events WHERE event_id=?", (e["event_id"],)).fetchone()
    return bool(rec and rec["tickets"])


def refresh(con: sqlite3.Connection, run_id: str) -> dict:
    today = date.today().isoformat()
    stats = {"status_changes": 0, "date_end_fixed": 0}
    # postcodes.io — один раз на все postcode событий и площадок (кэш в таблице postcodes)
    before = con.execute("SELECT count(*) FROM postcodes").fetchone()[0]
    lookup(con, [r[0] for r in con.execute("""SELECT postcode FROM raw_items WHERE kind='event' AND postcode IS NOT NULL
        UNION SELECT postcode FROM events WHERE postcode IS NOT NULL""")])
    stats["geocoded_postcodes"] = con.execute("SELECT count(*) FROM postcodes").fetchone()[0] - before
    for e in con.execute("SELECT * FROM events").fetchall():
        raws = sorted(con.execute("SELECT * FROM raw_items WHERE event_id=?", (e["event_id"],)).fetchall(),
                      key=lambda r: rank(r["source_id"]))
        # старт продаж из статей: с прошедшей/неизвестной датой — продажа открыта, с будущей — ещё ожидается
        updates = {u["kind"] for u in con.execute("SELECT kind, on_sale_date FROM event_updates WHERE event_id=?",
                                                   (e["event_id"],))
                   if not (u["kind"] == "on_sale" and (u["on_sale_date"] or "") > today)}
        if not raws and e["source_type"] == "feed":
            continue
        first = raws[0] if raws else None
        venue = next((r["venue"] for r in raws if r["venue"]), e["venue_name"])
        address = next((r["address"] for r in raws if r["address"] and r["postcode"]),
                       next((r["address"] for r in raws if r["address"]), e["address"]))
        postcode = next((r["postcode"] for r in raws if r["postcode"]), e["postcode"])
        v = venues.resolve(con, venue, address)
        venue_id = v["venue_id"] if v else None
        if not postcode and v:
            postcode, address = v["postcode"], v["address"]
        lat, lon, zn = zone_for_postcode(con, postcode) or (None, None, None)
        address_unknown = 0
        # площадка из справочника без postcode: населённый пункт (place) или только «Кембридж» (city)
        if zn is None and v and v["zone"] and not v["postcode"]:
            lat, lon, zn = v["lat"], v["lon"], v["zone"]
            address_unknown = int(v["precision"] == "city")
        multi_venue = int(bool(e["multi_venue"]) or bool(MULTI_VENUE_RE.match(venue or "")))
        where = f"{venue or ''} {address or ''}"
        if zn is None and multi_venue and re.search(r"\bCambridge\b", where):
            zn, address_unknown = "центр", 1
        if zn is None and e["lat"] is None and any(CITY_ONLY_RE.search(x or "") for x in (address, venue)):
            zn, address_unknown = "центр", 1
        prices = [parse_price(r["price"], r["summary"], r["title"]) for r in raws]
        prices = [p for p in prices if p is not None]
        price_from = min(prices) if prices else e["price_from"]
        price_text = next((r["price"] for r in raws if r["price"]), e["price_text"])
        # однодневные события, показанные как двухдневные (окончание после полуночи) — по всей базе
        if first and first["end"] and e["date_end"]:
            de = end_date(first["start"], first["end"])
            if de and de < e["date_end"]:
                con.execute("UPDATE events SET date_end=?, time_end=NULL WHERE event_id=?", (de, e["event_id"]))
                stats["date_end_fixed"] += 1
                e = dict(e) | {"date_end": de}
        end_date_ = e["date_end"] or e["date_start"]
        if raws:
            status, src = _status(raws, updates, price_from, end_date_, today, _tickets_expected(con, e, raws, today))
        elif end_date_ < today:  # ежегодные и прочие события без записей источников
            status, src = ("past" if e["status"] not in ("cancelled", "postponed") else e["status"]), None
        elif e["status"] in ("announced", "scheduled"):
            status, src = ("announced" if _tickets_expected(con, e, raws, today) else "scheduled"), None
        else:
            status, src = e["status"], None
        if e["status"] == "past" and status == "disappeared":
            status = "past"
        con.execute("""UPDATE events SET title=?, venue_id=?, venue_name=?, address=?, postcode=?, lat=coalesce(?, lat),
            lon=coalesce(?, lon), zone=coalesce(?, zone), address_unknown=?, multi_venue=?, price_from=?, price_text=?, url=?,
            last_seen_at=?, status=? WHERE event_id=?""",
                    (first["title"] if first else e["title"], venue_id, venue, address, postcode, lat, lon,
                     zn, address_unknown, multi_venue, price_from, price_text, first["url"] if first and first["url"] else e["url"],
                     max(r["last_seen_at"] for r in raws) if raws else e["last_seen_at"], status, e["event_id"]))
        if not con.execute("SELECT 1 FROM status_history WHERE event_id=?", (e["event_id"],)).fetchone():
            con.execute("INSERT INTO status_history(event_id, status, changed_at, source_id, note) VALUES (?,?,?,?,?)",
                        (e["event_id"], status, e["first_seen_at"], first["source_id"] if first else None, "впервые увидено"))
        elif status != e["status"]:
            stats["status_changes"] += 1
            con.execute("INSERT INTO status_history(event_id, status, changed_at, source_id, note) VALUES (?,?,?,?,?)",
                        (e["event_id"], status, run_id, src, f"было: {e['status']}"))
            if status == "on_sale" and e["status"] == "announced" and e["first_seen_at"] != run_id:
                con.execute("UPDATE events SET on_sale_date=? WHERE event_id=?", (run_id[:10], e["event_id"]))
    return stats


# --- 4. новые арендаторы торговых центров ---

def store_changes(con: sqlite3.Connection, run_id: str) -> dict:
    """Новый магазин в списке ТЦ → venue_news. Первый прогон источника — только база для сравнения."""
    stats = {"new_stores": 0, "gone_stores": 0}
    for (sid,) in con.execute("SELECT DISTINCT source_id FROM raw_items WHERE kind='store'").fetchall():
        # источник не запускался в этом прогоне (частичный запуск) — сравнивать не с чем, «пропавших» нет
        if not con.execute("SELECT 1 FROM runs WHERE source_id=? AND run_id=? AND ok=1", (sid, run_id)).fetchone():
            continue
        earlier = con.execute("SELECT count(*) FROM runs WHERE source_id=? AND ok=1 AND run_id < ?", (sid, run_id)).fetchone()[0]
        if not earlier:
            continue
        for r in con.execute("SELECT * FROM raw_items WHERE source_id=? AND kind='store' AND first_seen_at=?", (sid, run_id)):
            stage = "coming_soon" if "coming soon" in f"{r['title']} {r['summary'] or ''}".lower() else "opened"
            cur = con.execute("""INSERT OR IGNORE INTO venue_news(name, type, address, stage, date, source_id,
                source_type, url, note, first_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                              (r["title"], "магазин", r["address"], stage, run_id[:10], sid, "store_list", r["url"],
                               "новый арендатор в списке ТЦ", run_id))
            stats["new_stores"] += cur.rowcount
        for r in con.execute("SELECT * FROM raw_items WHERE source_id=? AND kind='store' AND last_seen_at < ? AND disappeared_at IS NULL", (sid, run_id)).fetchall():
            con.execute("UPDATE raw_items SET disappeared_at=? WHERE raw_id=?", (run_id, r["raw_id"]))
            cur = con.execute("""INSERT OR IGNORE INTO venue_news(name, type, address, stage, date, source_id,
                source_type, url, note, first_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                              (r["title"], "магазин", r["address"], "closed", run_id[:10], sid, "store_list", r["url"],
                               "пропал из списка ТЦ", run_id))
            stats["gone_stores"] += cur.rowcount
    return stats
