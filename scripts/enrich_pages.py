"""Правки по черновику v5: страницы событий окна, по которым в данных нет фактов или цены, — одна загрузка у первоисточника
(pipeline/enrich.py, таблица event_pages). Запускать перед сборкой выпуска.

  python scripts/enrich_pages.py --issue 2026-10-01
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import enrich, issue  # noqa: E402
from pipeline.db import connect  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    args = ap.parse_args()
    sent = date.fromisoformat(args.issue)
    w = issue.Window(sent, sent, sent + timedelta(days=issue.WINDOW_DAYS))
    con = connect()
    pools = issue.build_pools(con, w)
    http = PoliteClient()
    st = {"candidates": 0, "ok": 0, "skipped_or_error": 0}
    for cid, c in pools.candidates.items():
        if c["kind"] != "event" or not (c.get("thin_data") or not c.get("price_text")) or c.get("zone") not in issue.LISTED_ZONES:
            continue
        st["candidates"] += 1
        res = enrich.fetch(con, http, c["event_ids"][0], c.get("url"), c["title"])
        st["ok" if res else "skipped_or_error"] += 1
    # этап 7c (правки по v9): открытия, найденные поиском (S148, без статьи), — страница первоисточника для факта в
    # описании (Arbury Social, Bridge Bagels); в event_pages под отрицательным id = −news_id
    for cid, c in pools.candidates.items():
        if c["kind"] == "venue_news" and c.get("source_type") == "search" and c.get("url"):
            st["candidates"] += 1
            res = enrich.fetch(con, http, -c["news_id"], c["url"], c["title"])
            st["ok" if res else "skipped_or_error"] += 1
    print(json.dumps(st))
