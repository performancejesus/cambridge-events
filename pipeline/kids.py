"""Детские программы на каникулы (этап 6-v4 — быстрый срез; полноценный этап 6c — коллекторы провайдеров).

data/kids_programmes.json → таблица kids_programmes (схема этапа 6c): провайдер, название, возраст, даты, часы,
цена, место (адрес, postcode, зона), дедлайн/открытие записи, статус мест, для кого, ссылка, проверено ли на сайте.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .db import ROOT
from .geo import NEIGHBOUR_IF_IMPORTANT, lookup, place, zone, zone_for_postcode

DATA = ROOT / "data" / "kids_programmes.json"
SCHEMA = """CREATE TABLE IF NOT EXISTS kids_programmes (
    prog_id     TEXT PRIMARY KEY,
    holiday     TEXT,          -- october_half_term / christmas / both / …
    provider    TEXT, title TEXT, ages TEXT,
    date_start  TEXT, date_end TEXT, hours TEXT, price TEXT,
    venue       TEXT, address TEXT, postcode TEXT, zone TEXT,
    booking_opens TEXT,        -- запись ещё не открыта: дата открытия
    places      TEXT,          -- open / few_left / full / not_open / unknown
    audience    TEXT,          -- public / eligible (HAF) / university (дети сотрудников и студентов)
    url         TEXT, verified INTEGER, note TEXT, checked_at TEXT
)"""


def load(con: sqlite3.Connection) -> dict:
    """Ручной срез 6-v4 (data/kids_programmes.json). Этап 6c: строки коллектора (source = collector) не трогаем; ручные
    строки провайдера, по которому уже есть данные коллектора, не загружаем — срез заменяется коллектором."""
    from .kids_collect import init
    init(con)
    d = json.loads(DATA.read_text())
    progs = d["programmes"]
    lookup(con, [p["postcode"] for p in progs if p.get("postcode")])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    collected = {r[0] for r in con.execute("SELECT DISTINCT provider_host FROM kids_programmes WHERE source='collector'")}
    con.execute("DELETE FROM kids_programmes WHERE source IS NULL")
    n = 0
    for p in progs:
        host = p["url"].split("/")[2].lower().removeprefix("www.")
        if host in collected:
            continue
        g = zone_for_postcode(con, p.get("postcode")) or _town_zone(con, p.get("address"))
        con.execute("""INSERT OR REPLACE INTO kids_programmes(prog_id, holiday, provider, title, ages, date_start, date_end,
            hours, price, venue, address, postcode, zone, booking_opens, places, audience, url, verified, note, checked_at,
            provider_host, kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p["id"], p["holiday"], p["provider"], p["title"], p.get("ages"), p.get("date_start"),
                     p.get("date_end"), p.get("hours"), p.get("price"), p.get("venue"), p.get("address"),
                     p.get("postcode"), g[2] if g else None, p.get("booking_opens"), p.get("places"),
                     p.get("audience"), p["url"], int(bool(p.get("verified"))), p.get("note"), now, host, "holiday"))
        n += 1
    return {"kids_programmes_manual": n, "kids_programmes_collector":
            con.execute("SELECT count(*) FROM kids_programmes WHERE source='collector'").fetchone()[0]}


def _town_zone(con: sqlite3.Connection, address: str | None) -> tuple | None:
    """Без postcode — зона по населённому пункту из адреса (последняя часть: «Brampton Road, Huntingdon» → Huntingdon)."""
    town = (address or "").split(",")[-1].strip()
    if not town or town.lower() == "cambridgeshire":
        return None
    if town.lower() == "cambridge":
        return None, None, "центр"
    pl = place(con, town)
    if not pl:
        return None
    # у унитарного Питерборо postcodes.io /places отдаёт его как county — для правила FAR_DISTRICTS нужен district
    district = pl["district"] or (pl["county"] if "Peterborough" in (pl["county"] or "") else None)
    z = zone(pl["lat"], pl["lon"], pl["county"], "Peterborough" if district and "Peterborough" in district else district)
    # правки по v8: вне Кембриджшира 40–60 км по прямой («до часа, если важно» — для событий с оценкой ≥ 7) у программ
    # оценки нет — вне зоны (School's Out в Челмсфорде, 55 км); West Suffolk (Бери) — обычная зона по правилу 5b
    return pl["lat"], pl["lon"], "out_of_zone" if z == NEIGHBOUR_IF_IMPORTANT else z


def holidays() -> dict:
    return json.loads(DATA.read_text())["holidays"]
