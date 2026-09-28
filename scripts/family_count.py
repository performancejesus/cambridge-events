"""Семейные события на ближайшие 14 дней (этап 6): будущие события в зоне с явной пометкой — слова family / kids /
children / ages / half-term в названии, описании или категориях, либо семейная категория источника.

Запуск: python scripts/family_count.py [--db путь] [--start YYYY-MM-DD] [--json]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import issue  # noqa: E402


def family_events(con: sqlite3.Connection, start: date, days: int = 14) -> list[dict]:
    con.row_factory = sqlite3.Row
    end = start + timedelta(days=days)
    rows = con.execute("""SELECT * FROM events WHERE date_start <= ? AND coalesce(date_end, date_start) >= ?
        AND status NOT IN ('past', 'cancelled') AND coalesce(zone, '') NOT IN ('out_of_zone', '')""",
                       (end.isoformat(), start.isoformat())).fetchall()
    out = []
    for e in rows:
        cats = issue._categories(con, e["event_id"], None)
        if issue.is_family(e["title"], issue._summary(con, e["event_id"]), cats):
            srcs = [r[0] for r in con.execute("SELECT DISTINCT source_id FROM event_sources WHERE event_id=?",
                                                (e["event_id"],))]
            out.append({"event_id": e["event_id"], "title": e["title"], "date": e["date_start"], "sources": srcs})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "events.db"))
    ap.add_argument("--start", default=date.today().isoformat())
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ev = family_events(sqlite3.connect(a.db), date.fromisoformat(a.start))
    if a.json:
        print(json.dumps(ev, ensure_ascii=False, indent=1))
    else:
        print(len(ev), Counter(s for e in ev for s in e["sources"]).most_common())


if __name__ == "__main__":
    main()
