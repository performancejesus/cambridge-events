"""Этап 6d: продавцы билетов — все события окна выпуска и отдельно пункты выпусков v5/v6 (и v7, если собран).

  python scripts/ticket_vendors.py --issue 2026-10-01     # → ticket_vendors, data/ticket_vendors_6d.json
"""
import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import issue, vendors  # noqa: E402
from pipeline.db import connect  # noqa: E402


def event_ids_of(cid: str, pools) -> list[int]:
    if cid in pools.candidates:
        return list(pools.candidates[cid]["event_ids"])
    if cid[0] in "EAHC" and cid[1:].isdigit():
        return [int(cid[1:])]
    return []


def issue_items(stem: str, pools) -> list[dict]:
    p = ROOT / "issues" / f"{stem}_model.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    res = (d.get("result_post") or {}).get("result") or d["result"]
    out = []
    for sec in res["sections"]:
        for it in sec["items"]:
            ev = [e for cid in it["ids"] for e in event_ids_of(cid, pools)]
            if ev:
                out.append({"rubric": sec["rubric"], "title": it["title_en"], "event_ids": ev,
                            "importance": max((pools.candidates.get(c, {}).get("importance") or 0) for c in it["ids"])})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    args = ap.parse_args()
    s = date.fromisoformat(args.issue)
    w = issue.Window(s, s, s + timedelta(days=issue.WINDOW_DAYS))
    con = connect()
    pools = issue.build_pools(con, w)
    http = PoliteClient()
    window = sorted({e for c in pools.candidates.values() if c["kind"] == "event" and c.get("zone") in issue.LISTED_ZONES
                     for e in c["event_ids"]})
    items = {v: issue_items(f"issue_{args.issue}_{v}", pools) for v in ("v5", "v6", "v7")}
    todo = sorted(set(window) | {e for its in items.values() for it in its for e in it["event_ids"]})
    res = {}
    for n, eid in enumerate(todo):
        urls = [r[0] for r in con.execute("SELECT url FROM events WHERE event_id=?", (eid,))]
        urls += [r[0] for r in con.execute("SELECT url FROM event_sources WHERE event_id=? AND url IS NOT NULL", (eid,))]
        res[eid] = vendors.classify(con, http, eid, urls)
        if n % 25 == 0:
            print(f"{n}/{len(todo)}", file=sys.stderr)
    imp = {e: (con.execute("SELECT importance_score FROM events WHERE event_id=?", (e,)).fetchone()[0] or 0) for e in todo}
    out = {"window_events": len(window), "window_ids": window,
           "window_by_vendor": Counter(res[e]["vendor"] for e in window).most_common(),
           "items": {v: [it | {"vendor": res[it["event_ids"][0]]["vendor"]} for it in its] for v, its in items.items()},
           "events": {e: res[e] | {"importance": imp[e]} for e in todo}}
    (ROOT / "data" / "ticket_vendors_6d.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(out["window_by_vendor"], ensure_ascii=False))
