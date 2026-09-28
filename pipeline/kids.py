"""Детские программы на каникулы (этап 6-v4 — быстрый срез; полноценный этап 6c — коллекторы провайдеров).

data/kids_programmes.json → таблица kids_programmes (схема этапа 6c): провайдер, название, возраст, даты, часы,
цена, место (адрес, postcode, зона), дедлайн/открытие записи, статус мест, для кого, ссылка, проверено ли на сайте.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .db import ROOT
from .geo import lookup, zone_for_postcode

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
    con.execute(SCHEMA)
    d = json.loads(DATA.read_text())
    progs = d["programmes"]
    lookup(con, [p["postcode"] for p in progs if p.get("postcode")])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("DELETE FROM kids_programmes")
    for p in progs:
        g = zone_for_postcode(con, p.get("postcode"))
        con.execute("INSERT INTO kids_programmes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["id"], p["holiday"], p["provider"], p["title"], p.get("ages"), p.get("date_start"),
                     p.get("date_end"), p.get("hours"), p.get("price"), p.get("venue"), p.get("address"),
                     p.get("postcode"), g[2] if g else None, p.get("booking_opens"), p.get("places"),
                     p.get("audience"), p["url"], int(bool(p.get("verified"))), p.get("note"), now))
    return {"kids_programmes": len(progs)}


def holidays() -> dict:
    return json.loads(DATA.read_text())["holidays"]
