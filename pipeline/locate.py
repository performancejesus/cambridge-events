"""Площадки без postcode (решение после этапа 4): справочник площадок по названию → адрес площадки в тексте
страницы события или статьи (Claude Haiku, только из текста) → postcode через postcodes.io, иначе населённый
пункт через postcodes.io /places; если площадка явно в Кембридже, но адреса нет — зона «центр» с address_unknown.
Найденные площадки добавляются в справочник venues (origin = located), так что следующие события с тем же
названием получат адрес без модели.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from collectors.http import PoliteClient

from . import extract, venues
from .db import ROOT
from .geo import CENTRE, POSTCODE_RE, lookup, place, zone, zone_for_postcode
from .normalize import norm_venue

MODEL = extract.MODEL
PROMPT = (ROOT / "prompts" / "venue_locate.md").read_text()
SCHEMA = json.loads((ROOT / "prompts" / "venue_locate.schema.json").read_text())
TBC_RE = re.compile(r"title to be confirmed|location to be announced", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def todo(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Будущие события без зоны, у которых есть хоть какая-то зацепка (площадка, адрес или страница),
    кроме лекций «Title to be confirmed» и мест «to be announced»; уже проверенные — пропускаем."""
    rows = con.execute("""SELECT e.* FROM events e WHERE e.zone IS NULL
        AND coalesce(e.date_end, e.date_start) >= date('now')
        AND e.event_id NOT IN (SELECT event_id FROM venue_lookups)""").fetchall()
    return [r for r in rows if not TBC_RE.search(f"{r['title']} {r['venue_name'] or ''}")]


def _page_url(con, e: sqlite3.Row) -> str | None:
    art = con.execute("""SELECT a.url FROM event_sources s JOIN articles a ON a.article_id = s.article_id
        WHERE s.event_id=? LIMIT 1""", (e["event_id"],)).fetchone()
    return art["url"] if art else e["url"]


def ask(client, e: sqlite3.Row, text: str) -> tuple[dict, float, object]:
    msg = client.messages.create(
        model=MODEL, max_tokens=1000, system=PROMPT,
        messages=[{"role": "user", "content": json.dumps({
            "event_title": e["title"], "known_venue": e["venue_name"] or "", "address_fragment": e["address"] or "",
            "page_text": text}, ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if msg.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={msg.stop_reason}")
    cost = msg.usage.input_tokens * extract.PRICE_IN + msg.usage.output_tokens * extract.PRICE_OUT
    return json.loads(next(b.text for b in msg.content if b.type == "text")), cost, msg.usage


def _add_venue(con, name: str, address: str | None, postcode: str | None, lat, lon, zn, precision: str) -> None:
    alias = norm_venue(name)
    if len(alias) < 3 or con.execute("SELECT 1 FROM venue_aliases WHERE alias=?", (alias,)).fetchone():
        return
    cur = con.execute("""INSERT INTO venues(name, address, postcode, lat, lon, zone, origin, precision)
        VALUES (?,?,?,?,?,?,?,?)""", (name, address, postcode, lat, lon, zn, "located", precision))
    con.execute("INSERT OR IGNORE INTO venue_aliases(alias, venue_id) VALUES (?,?)", (alias, cur.lastrowid))


def resolve(con, e: sqlite3.Row, r: dict) -> str:
    """Ответ модели → площадка в справочнике и поля события. Возвращает точность: postcode | place | city | none."""
    name = (r["venue_name"] or e["venue_name"] or "").strip()
    street = r["street_address"].strip()
    town = r["town"].strip()
    address = ", ".join(x for x in (street, town) if x) or None
    pc = r["postcode"].strip().upper()
    if pc and POSTCODE_RE.match(pc):
        lookup(con, [pc])
        g = zone_for_postcode(con, pc)
        if g:
            _add_venue(con, name, address, pc, *g, "postcode")
            con.execute("UPDATE events SET venue_name=coalesce(venue_name, ?), address=?, postcode=? WHERE event_id=?",
                        (name, address, pc, e["event_id"]))
            return "postcode"
    if town and town.lower() != "cambridge":
        p = place(con, town)
        if p:
            district = "Peterborough" if p["county"] == "Peterborough" else p["district"]
            zn = zone(p["lat"], p["lon"], p["county"], district)
            _add_venue(con, name or town, address, None, p["lat"], p["lon"], zn, "place")
            con.execute("UPDATE events SET venue_name=coalesce(venue_name, ?), address=coalesce(address, ?) WHERE event_id=?",
                        (name or town, address, e["event_id"]))
            return "place"
    if town.lower() == "cambridge" or r["is_cambridge_city"] == "yes":
        _add_venue(con, name, address or "Cambridge", None, CENTRE[0], CENTRE[1], "центр", "city")
        con.execute("UPDATE events SET venue_name=coalesce(venue_name, ?), address=coalesce(address, ?) WHERE event_id=?",
                    (name or None, address or "Cambridge", e["event_id"]))
        return "city"
    return "none"


def run(con: sqlite3.Connection, client, http: PoliteClient | None = None) -> dict:
    http = http or PoliteClient()
    stats = {"checked": 0, "postcode": 0, "place": 0, "city": 0, "none": 0, "by_directory": 0, "cost_usd": 0.0}
    for e in todo(con):
        # 1. справочник по названию (площадка могла появиться после прошлого прогона)
        v = venues.resolve(con, e["venue_name"], e["address"])
        if v and v["zone"]:
            stats["by_directory"] += 1
            continue
        # 2. адрес площадки в тексте страницы события или статьи
        url = _page_url(con, e)
        if not url:
            continue
        text, source = extract.article_text(http, url, "")
        if not text:
            continue
        r, cost, usage = ask(client, e, text)
        con.execute("INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?,?,?,?)",
                    (now(), "venue_locate", MODEL, None, usage.input_tokens, usage.output_tokens, cost))
        stats["cost_usd"] += cost
        how = resolve(con, e, r)
        if r["multi_venue"]:
            con.execute("UPDATE events SET multi_venue=1 WHERE event_id=?", (e["event_id"],))
        con.execute("INSERT OR REPLACE INTO venue_lookups VALUES (?,?,?,?,?)",
                    (e["event_id"], url, json.dumps(r, ensure_ascii=False), how, now()))
        con.commit()
        stats["checked"] += 1
        stats[how] += 1
    stats["cost_usd"] = round(stats["cost_usd"], 4)
    return stats
