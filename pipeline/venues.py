"""Справочник площадок: из событий с адресом + ручной список (data/venues_seed.json)."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict

from .db import ROOT
from .geo import lookup, zone, zone_for_postcode
from .normalize import norm_venue

SEED = ROOT / "data" / "venues_seed.json"


def _add_venue(con, name, address, postcode, origin, aliases) -> int:
    cur = con.execute("INSERT INTO venues(name, address, postcode, origin) VALUES (?,?,?,?)",
                      (name, address, postcode, origin))
    vid = cur.lastrowid
    for a in aliases:
        if a:
            con.execute("INSERT OR IGNORE INTO venue_aliases(alias, venue_id) VALUES (?,?)", (a, vid))
    return vid


def build(con: sqlite3.Connection) -> dict:
    """Дополняет справочник; существующие записи не трогает."""
    known = {r["alias"] for r in con.execute("SELECT alias FROM venue_aliases")}
    added = 0
    for v in json.loads(SEED.read_text()):
        aliases = [norm_venue(v["name"])] + [norm_venue(a) or a for a in v["aliases"]]
        if not any(a in known for a in aliases):
            _add_venue(con, v["name"], v["address"], v["postcode"], "manual", aliases)
            known.update(aliases)
            added += 1
        else:  # новые синонимы к уже известной площадке
            vid = next(con.execute("SELECT venue_id FROM venue_aliases WHERE alias=?", (a,)).fetchone()[0]
                       for a in aliases if a in known)
            for a in aliases:
                con.execute("INSERT OR IGNORE INTO venue_aliases(alias, venue_id) VALUES (?,?)", (a, vid))
    # из сырых событий с postcode: самое частое сочетание название → postcode
    groups: dict[str, Counter] = defaultdict(Counter)
    names: dict[str, Counter] = defaultdict(Counter)
    addrs: dict[tuple, str] = {}
    for r in con.execute("SELECT venue, address, postcode FROM raw_items WHERE kind='event' AND venue IS NOT NULL AND postcode IS NOT NULL"):
        a = norm_venue(r["venue"])
        if len(a) < 3 or a in known:
            continue
        groups[a][r["postcode"]] += 1
        names[a][r["venue"].split(",")[0].strip()] += 1
        addrs[(a, r["postcode"])] = r["address"]
    for a, pcs in groups.items():
        pc = pcs.most_common(1)[0][0]
        _add_venue(con, names[a].most_common(1)[0][0], addrs[(a, pc)], pc, "events", [a])
        known.add(a)
        added += 1
    # координаты и зоны (зона пересчитывается у всех: правила могли измениться)
    lookup(con, [r["postcode"] for r in con.execute("SELECT postcode FROM venues WHERE postcode IS NOT NULL")])
    geocoded = 0
    for v in con.execute("SELECT venue_id, postcode, lat FROM venues WHERE postcode IS NOT NULL").fetchall():
        g = zone_for_postcode(con, v["postcode"])
        if g:
            geocoded += v["lat"] is None
            con.execute("UPDATE venues SET lat=?, lon=?, zone=? WHERE venue_id=?", g + (v["venue_id"],))
    # площадки, известные только по населённому пункту (locate: precision = place) — зона по графству и району места
    for v in con.execute("SELECT venue_id, lat, lon FROM venues WHERE precision='place' AND lat IS NOT NULL").fetchall():
        p = con.execute("SELECT county, district FROM places WHERE lat=? AND lon=?", (v["lat"], v["lon"])).fetchone()
        if p:
            district = "Peterborough" if p["county"] == "Peterborough" else p["district"]
            con.execute("UPDATE venues SET zone=? WHERE venue_id=?", (zone(v["lat"], v["lon"], p["county"], district), v["venue_id"]))
    return {"venues_added": added, "venues_geocoded": geocoded}


def resolve(con: sqlite3.Connection, *names: str | None) -> sqlite3.Row | None:
    """Площадка по любой части названия/адреса («Seminar Room 1, Department of …» → HPS)."""
    for name in names:
        if not name:
            continue
        parts = [name] + [p for p in name.replace(" - ", ",").replace("(", ",").replace(")", ",").split(",")]
        for p in parts:
            a = norm_venue(p) if p != name else norm_venue(name)
            for cand in {a, " ".join(a.split()[:3]), " ".join(a.split()[:2])}:
                if len(cand) >= 3:
                    row = con.execute("SELECT v.* FROM venue_aliases va JOIN venues v USING(venue_id) WHERE va.alias=?", (cand,)).fetchone()
                    if row:
                        return row
            # «Seminar Room West RDC (A0.015)» — короткий синоним-аббревиатура (rdc, cms, hps) внутри строки;
            # только слова, написанные заглавными: иначе «Arts Picturehouse» попадает в Arts Theatre (синоним «arts»)
            for w in (x.lower() for x in re.findall(r"\b[A-Z]{3,4}\b", p)):
                if 3 <= len(w) <= 4:
                    row = con.execute("SELECT v.* FROM venue_aliases va JOIN venues v USING(venue_id) WHERE va.alias=?", (w,)).fetchone()
                    if row:
                        return row
    return None
