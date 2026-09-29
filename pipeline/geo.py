"""Геокодирование через postcodes.io (с кэшем в таблице postcodes) и расчёт зоны по разделу «География» брифа."""

from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime, timezone

import httpx

API = "https://api.postcodes.io/postcodes"
CENTRE = (52.2053, 0.1218)  # Market Square
# Зона по расстоянию по прямой от центра — грубая замена времени в пути (решение после этапа 3).
ZONES = ((3.0, "центр"), (25.0, "до 30 мин"), (60.0, "до часа"))
COUNTY_FAR = "Кембриджшир, дальше часа"
OUT_OF_ZONE = "out_of_zone"
# Районы графства, которые бриф относит к «дальше часа» (Питерборо, Fenland: Wisbech, March…). По прямой они
# ближе 60 км (Питерборо — 48 км, Wisbech — 51 км, самая северная точка графства — 58 км), поэтому без этого
# правила метка «Кембриджшир, дальше часа» не досталась бы никому.
FAR_DISTRICTS = {"Peterborough", "Fenland"}
# Решение после этапа 5: вне Кембриджшира до 40 км по прямой — обычная зона; 40–60 км — «до часа» только для важных
# событий (оценка ≥ 7), иначе out_of_zone. Важность известна только после оценки, поэтому geo.zone ставит метку
# NEIGHBOUR_IF_IMPORTANT, а importance.resolve_neighbours после оценки заменяет её на «до часа» или out_of_zone.
NEIGHBOUR_KM = 40.0
NEIGHBOUR_MIN_SCORE = 7.0
NEIGHBOUR_IF_IMPORTANT = "до часа, если важно"
# Исключения из правила 40 км (решение после этапа 5b). West Suffolk (Бери-Сент-Эдмундс, Ньюмаркет) — обычная зона
# «до часа», хотя Бери на 40,3–40,7 км по прямой (по A14 ~40 минут). Stevenage — наоборот, всегда по правилу 40–60 км
# (только события с оценкой ≥ 7), даже если площадка ближе 40 км. В бэклоге — время в пути вместо расстояния (OSRM).
NEIGHBOUR_EXEMPT_DISTRICTS = {"West Suffolk"}
NEIGHBOUR_ALWAYS_DISTRICTS = {"Stevenage"}
POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$")


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def in_cambridgeshire(county: str | None, district: str | None) -> bool:
    return county == "Cambridgeshire" or district == "Peterborough"


def zone(lat: float | None, lon: float | None, county: str | None = None, district: str | None = None) -> str | None:
    """центр / до 30 мин / до часа / Кембриджшир, дальше часа / до часа, если важно / out_of_zone; None — координат нет."""
    if lat is None or lon is None:
        return None
    d = km(CENTRE[0], CENTRE[1], lat, lon)
    cambs = in_cambridgeshire(county, district)
    if cambs and district in FAR_DISTRICTS and d > ZONES[1][0]:
        return COUNTY_FAR
    band = next((z for limit, z in ZONES if d <= limit), None)
    if band and not cambs and ((d > NEIGHBOUR_KM and district not in NEIGHBOUR_EXEMPT_DISTRICTS)
                               or district in NEIGHBOUR_ALWAYS_DISTRICTS):
        return NEIGHBOUR_IF_IMPORTANT
    if band:
        return band
    return COUNTY_FAR if cambs else OUT_OF_ZONE


def _key(pc: str) -> str:
    return pc.upper().replace(" ", "")


def lookup(con: sqlite3.Connection, postcodes: list[str]) -> dict[str, sqlite3.Row]:
    """Postcode (без пробелов, в верхнем регистре) → строка кэша postcodes. Недостающие — из postcodes.io пачками по 100."""
    want = {_key(p) for p in postcodes if p and POSTCODE_RE.match(p.upper().strip())}
    cached = {_key(r["postcode"]): r for r in con.execute("SELECT * FROM postcodes")}
    missing = sorted(want - cached.keys())
    if missing:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with httpx.Client(timeout=30, headers={"User-Agent": "CambridgeEventsBot/0.1"}) as c:
            for i in range(0, len(missing), 100):
                r = c.post(API, json={"postcodes": missing[i:i + 100]})
                r.raise_for_status()
                for item in r.json()["result"]:
                    res = item["result"]
                    if res:
                        con.execute("INSERT OR REPLACE INTO postcodes VALUES (?,?,?,?,?,?)",
                                    (res["postcode"], res["latitude"], res["longitude"], res["admin_county"],
                                     res["admin_district"], now))
        cached = {_key(r["postcode"]): r for r in con.execute("SELECT * FROM postcodes")}
    return {k: cached[k] for k in want if k in cached}


PLACES_API = "https://api.postcodes.io/places"
PLACE_TYPES = {"City", "Town", "Village", "Hamlet", "Suburban Area", "Other Settlement"}


def place(con: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    """Населённый пункт по названию (postcodes.io /places, OS Open Names) — ближайший к Кембриджу; кэш в places."""
    key = name.strip().lower()
    row = con.execute("SELECT * FROM places WHERE query=?", (key,)).fetchone()
    if row:
        return row if row["lat"] is not None else None
    with httpx.Client(timeout=30, headers={"User-Agent": "CambridgeEventsBot/0.1"}) as c:
        r = c.get(PLACES_API, params={"q": name, "limit": 20})
        r.raise_for_status()
        found = [p for p in r.json().get("result") or [] if p.get("local_type") in PLACE_TYPES
                 and p["name_1"].lower() == key]
    best = min(found, key=lambda p: km(CENTRE[0], CENTRE[1], p["latitude"], p["longitude"]), default=None)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # унитарный Питерборо: /places отдаёт его в county_unitary, district_borough пуст — для правил графства нужен district
    district = best and (best["district_borough"] or
                         ("Peterborough" if "Peterborough" in (best["county_unitary"] or "") else None))
    con.execute("INSERT OR REPLACE INTO places VALUES (?,?,?,?,?,?,?)",
                (key, best and best["name_1"], best and best["latitude"], best and best["longitude"],
                 best and best["county_unitary"], district, now))
    return con.execute("SELECT * FROM places WHERE query=? AND lat IS NOT NULL", (key,)).fetchone()


def zone_for_postcode(con: sqlite3.Connection, postcode: str | None) -> tuple[float, float, str | None] | None:
    """(lat, lon, зона) по postcode из кэша (без сетевого запроса); None — postcode неизвестен."""
    if not postcode:
        return None
    r = con.execute("SELECT * FROM postcodes WHERE replace(upper(postcode),' ','')=?", (_key(postcode),)).fetchone()
    if not r:
        return None
    return r["lat"], r["lon"], zone(r["lat"], r["lon"], r["admin_county"], r["admin_district"])
