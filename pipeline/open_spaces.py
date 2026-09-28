"""Выездные события на лугах, в парках и на площадях (этап 6: луна-парки, фуд-фестивали, ярмарки, маркеты).

Единого календаря у советов нет, поэтому событие помечается по месту: events.open_space = название пространства,
если оно упомянуто в площадке, адресе или названии (включая события из статей). Список — и для запросов этапа 6b.
"""

from __future__ import annotations

import re
import sqlite3

OPEN_SPACES = {
    # Кембридж
    "Jesus Green": r"jesus green", "Midsummer Common": r"midsummer common", "Parker's Piece": r"parker'?s piece",
    "Christ's Pieces": r"christ'?s pieces", "Coldham's Common": r"coldham'?s common",
    "Stourbridge Common": r"stourbridge common", "Cherry Hinton Hall": r"cherry hinton hall",
    "Sheep's Green": r"sheep'?s green", "Lammas Land": r"lammas land", "Market Square, Cambridge": r"market square,? cambridge",
    # другие города зоны
    "Jubilee Gardens, Ely": r"jubilee gardens", "Cherry Hill Park, Ely": r"cherry hill park",
    "Riverside Park, Huntingdon": r"riverside park,? huntingdon", "Riverside Park, St Neots": r"riverside park,? st neots",
    "Priory Park, St Neots": r"priory park", "The Quay, St Ives": r"the quay,? st ives|st ives quay",
    "The Embankment, Peterborough": r"embankment,? peterborough|peterborough embankment",
    "Cathedral Square, Peterborough": r"cathedral square", "Ferry Meadows": r"ferry meadows",
}
_RE = [(name, re.compile(rx, re.I)) for name, rx in OPEN_SPACES.items()]


def tag(con: sqlite3.Connection) -> dict:
    n = 0
    for e in con.execute("SELECT event_id, title, venue_name, address, open_space FROM events").fetchall():
        text = " ".join(x or "" for x in (e["venue_name"], e["address"], e["title"]))
        found = next((name for name, rx in _RE if rx.search(text)), None)
        if found != e["open_space"]:
            con.execute("UPDATE events SET open_space=? WHERE event_id=?", (found, e["event_id"]))
        n += bool(found)
    return {"open_space_events": n}
