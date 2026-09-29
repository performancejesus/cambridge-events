"""Этап 6c: разбор подборок («Things to do in Cambridge for Halloween») на отдельные события.

Для каждой подборки (events.roundup = 1) с датами в ближайшие 45 дней: страница подборки (robots.txt; сайты с
ИИ-запретом в модель не передаются) → Haiku перечисляет события со ссылками → каждое сравнивается с базой; нового
нет в базе — проверяется на его собственной странице (название и ближайшая дата, без модели). Подтверждённые —
источник S165 «Разбор подборок» (data/raw/S165_roundups.json, частичный прогон update_db).

  python scripts/split_roundups.py && python scripts/update_db.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from collectors.base import RawEvent  # noqa: E402
from collectors.http import PoliteClient  # noqa: E402
from collectors.llmlist import LlmListCollector  # noqa: E402
from gap_audit import _words, match_event, match_other_date, near, page_text  # noqa: E402
from pipeline import domains  # noqa: E402
from pipeline.db import connect  # noqa: E402

SID = "S165"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "roundups_6c.json"


class Roundup(LlmListCollector):
    source_id, name = SID, "Разбор подборок"


def main() -> None:
    con = connect()
    http = PoliteClient()
    rb = domains.robots(con)
    horizon = (date.today() + timedelta(days=45)).isoformat()
    report, found = [], []
    for r in con.execute("""SELECT * FROM events WHERE roundup=1 AND coalesce(date_end, date_start) >= date('now')
                            AND date_start <= ?""", (horizon,)).fetchall():
        h = domains.host(r["url"] or "")
        if (rb.get(h) or {"ai_blocked": ""})["ai_blocked"]:
            report.append({"roundup": r["title"], "url": r["url"], "result": "ИИ-запрет — список не передаётся в модель"})
            continue
        c = Roundup()
        c.pages = [(r["url"], f"This page is a round-up article ('{r['title']}'). List every separate event it names "
                              "with its own date: title, date, time, venue, price, and its own link (url) if the page "
                              "gives one. Skip evergreen attractions without a date.")]
        items = c.collect(http)
        rows = []
        for e in items:
            it = {"name": e.title, "date_start": e.start[:10], "date_end": (e.end or e.start)[:10]}
            mid, note = match_event(con, it)
            if not mid:
                mid, note = match_other_date(con, it)
            status, vurl = ("in_db", None) if mid else ("gap", None)
            if not mid and e.url and e.url != r["url"]:
                try:
                    text = page_text(http, e.url)
                    words = [w for w in sorted(_words(e.title)) if w in text]
                    if words and near(text, words, e.start[:10]):
                        status, vurl = "verified", e.url
                    else:
                        status = "not_verified"
                except Exception as ex:  # noqa: BLE001
                    status, note = "fetch_error", str(ex)[:80]
            elif not mid:
                status = "no_own_page"
            rows.append({"title": e.title, "date": e.start[:16], "venue": e.venue, "url": e.url, "status": status,
                         "note": note})
            if status == "verified":
                found.append(RawEvent(source_id=SID, title=e.title, url=vurl, start=e.start, end=e.end,
                                      all_day=e.all_day, venue=e.venue, address="Cambridge", price=e.price,
                                      external_id=f"{r['event_id']}|{e.title}|{e.start[:10]}",
                                      summary=f"из подборки «{r['title']}»"))
        report.append({"roundup": r["title"], "url": r["url"], "items": rows, "cost_usd": c.stats["cost_usd"]})
    http.close()
    (RAW / f"{SID}_roundups.json").write_text(json.dumps([x.to_dict() for x in found], ensure_ascii=False, indent=1))
    run = json.loads((RAW / "_run.json").read_text())
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run[SID] = {"name": "Разбор подборок", "module": "roundups", "started_at": started, "ok": True,
                "events": len(found), "articles": 0, "stores": 0, "requests": 0, "seconds": 0}
    run["_run_id"] = started
    (RAW / "_run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1))
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    for x in report:
        from collections import Counter
        print(x["roundup"], Counter(i["status"] for i in x.get("items", [])), x.get("result", ""))


if __name__ == "__main__":
    main()
