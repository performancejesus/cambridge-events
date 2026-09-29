"""Этап 6d: какие списки talks.cam собирает S047 и сколько в них событий (всего, будущих, в окне выпуска).

  python scripts/talks_audit.py --issue 2026-10-01      # → data/talks_audit_6d.json

Для каждого списка: название со страницы списка, число событий в iCal, последнее прошедшее и ближайшее будущее событие.
Плюс кандидаты в публичные списки (--extra ID ID …) — проверка без подключения.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from icalendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from collectors.llmlist import visible_text  # noqa: E402
from collectors.sources.talks_cam import LISTS  # noqa: E402


def audit(http, list_id: int, start: date, end: date) -> dict:
    out = {"id": list_id, "name": LISTS.get(list_id), "url": f"https://talks.cam.ac.uk/list/index/{list_id}"}
    try:
        page, _ = visible_text(http.get(out["url"]).text)
        m = re.search(r"\|\s*([^|]{3,120}?)\s*\|\s*(?:Add to your list|Subscribe|RSS|iCal)", page)
        out["page_title"] = m.group(1).strip() if m else None
    except Exception as e:  # noqa: BLE001
        out["page_title"] = f"ошибка: {str(e)[:80]}"
    try:
        cal = Calendar.from_ical(http.get(f"https://talks.cam.ac.uk/show/ics/{list_id}/").content)
    except Exception as e:  # noqa: BLE001
        return out | {"error": str(e)[:120]}
    ds, titles = [], []
    for ev in cal.walk("VEVENT"):
        d = ev.get("dtstart").dt
        d = d.date() if isinstance(d, datetime) else d
        ds.append(d)
        titles.append((d.isoformat(), str(ev.get("summary"))[:90]))
    today = date.today()
    fut = sorted(x for x in titles if x[0] >= today.isoformat())
    return out | {"total": len(ds), "future": len(fut),
                  "window": sum(1 for d in ds if start <= d <= end),
                  "last_past": max((d for d in ds if d < today), default=None),
                  "next": fut[:5]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    ap.add_argument("--extra", nargs="*", type=int, default=[])
    args = ap.parse_args()
    s = date.fromisoformat(args.issue)
    http = PoliteClient()
    res = [audit(http, i, s, s + timedelta(days=10)) for i in list(LISTS) + args.extra]
    (ROOT / "data" / "talks_audit_6d.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    for r in res:
        print(r["id"], r.get("name"), "| page:", r.get("page_title"), "| total", r.get("total"), "future", r.get("future"),
              "window", r.get("window"), "last", r.get("last_past"), "next", (r.get("next") or [None])[0], r.get("error", ""))
