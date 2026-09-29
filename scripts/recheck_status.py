"""Этап 7: перепроверка статусов отобранных событий (отмена, перенос, распродано, в продаже, сигналы срочности).

  python scripts/recheck_status.py --issue 2026-10-08     # → page_status, data/status_check_<дата>.json
  python scripts/update_db.py                             # пересчёт статусов с учётом страниц → status_history

Какие события: кандидаты окна выпуска с оценкой ≥ 4 и платные; события следующих 6 недель с оценкой ≥ 6 (кандидаты
«Успейте купить билеты»); пункты последнего собранного выпуска; события со статусом disappeared (пропали из источника
до своей даты). Страница: продавец билетов (этап 6d), иначе основная ссылка события (не газета).
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
from pipeline import issue, status_check  # noqa: E402
from pipeline.db import connect  # noqa: E402

NEWS = status_check.NEWS_HOSTS


def pick(con, w) -> dict[int, str]:
    """event_id → причина проверки."""
    out: dict[int, str] = {}
    listed = tuple(issue.LISTED_ZONES)
    q = f"zone IN ({','.join('?' * len(listed))})"
    for (eid,) in con.execute(f"""SELECT event_id FROM events WHERE date_start <= ? AND coalesce(date_end, date_start) >= ?
            AND {q} AND status NOT IN ('past','cancelled') AND (coalesce(importance_score,0) >= 4 OR price_from > 0)""",
                              (w.end.isoformat(), w.start.isoformat(), *listed)):
        out.setdefault(eid, "окно выпуска")
    for (eid,) in con.execute(f"""SELECT event_id FROM events WHERE date_start > ? AND date_start <= ? AND {q}
            AND status NOT IN ('past','cancelled') AND coalesce(importance_score,0) >= 6""",
                              (w.end.isoformat(), (w.issue + timedelta(weeks=6)).isoformat(), *listed)):
        out.setdefault(eid, "следующие 6 недель (Успейте купить)")
    for (eid,) in con.execute("SELECT event_id FROM events WHERE status='disappeared' AND date_start >= ?",
                              (w.issue.isoformat(),)):
        out.setdefault(eid, "пропало из источника")
    prev = sorted((ROOT / "issues").glob("issue_*_model.json"))
    if prev:
        d = json.loads(prev[-1].read_text())
        res = (d.get("result_post") or {}).get("result") or d["result"]
        for sec in res["sections"]:
            for it in sec["items"]:
                for cid in it["ids"]:
                    if cid[:1] in "EA" and cid[1:].isdigit():
                        out.setdefault(int(cid[1:]), f"пункт {prev[-1].stem[6:-6]}")
    return out


def page_url(con, eid: int) -> str | None:
    tv = con.execute("SELECT page_url, vendor FROM ticket_vendors WHERE event_id=?", (eid,)).fetchone() \
        if con.execute("SELECT name FROM sqlite_master WHERE name='ticket_vendors'").fetchone() else None
    if tv and tv[0] and tv[1] != "не определён":
        return tv[0]
    urls = [r[0] for r in con.execute("SELECT url FROM events WHERE event_id=?", (eid,))]
    urls += [r[0] for r in con.execute("SELECT url FROM event_sources WHERE event_id=? AND url IS NOT NULL", (eid,))]
    return next((u for u in urls if u and u.startswith("http") and not any(h in u for h in NEWS)), None)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    args = ap.parse_args()
    s = date.fromisoformat(args.issue)
    w = issue.Window(s, s, s + timedelta(days=issue.WINDOW_DAYS))
    con = connect()
    status_check.init(con)
    http = PoliteClient()
    todo = pick(con, w)
    before = {r[0]: r[1] for r in con.execute("SELECT event_id, status FROM events")}
    res = []
    for n, (eid, why) in enumerate(sorted(todo.items())):
        title = con.execute("SELECT title FROM events WHERE event_id=?", (eid,)).fetchone()[0]
        r = status_check.check(con, http, eid, page_url(con, eid), title)
        res.append(r | {"why": why, "title": title, "db_status": before.get(eid)})
        if n % 25 == 0:
            print(f"{n}/{len(todo)}", file=sys.stderr)
    ok = [r for r in res if r["result"] == "ok"]
    out = {"issue": args.issue, "checked": len(res), "page_opened": len(ok) + sum(1 for r in res if r["result"] == "not_found"),
           "status_readable": sum(1 for r in ok if r["status"] or r["urgency"]),
           "by_result": Counter(r["result"].split(":")[0] for r in res).most_common(),
           "by_status": Counter(r["status"] or "не читается" for r in ok).most_common(),
           "by_urgency": Counter(r["urgency"] for r in ok if r["urgency"]).most_common(),
           "by_reason": Counter(r["why"] for r in res).most_common(),
           "differs_from_db": [r for r in ok if r["status"] in ("cancelled", "postponed", "sold_out")
                               and r["status"] != r["db_status"]],
           "urgent": [r for r in ok if r["urgency"]],
           "events": res}
    (ROOT / "data" / f"status_check_{args.issue}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: out[k] for k in ("checked", "page_opened", "status_readable", "by_result", "by_status",
                                          "by_urgency")}, ensure_ascii=False))
    for r in out["differs_from_db"] + out["urgent"]:
        print(" ", r["status"], r["urgency"], "|", r["title"][:50], "|", r["evidence"][:100])
