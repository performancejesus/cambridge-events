"""Еженедельная проверка ежегодных событий (таблица recurring_events).

Для каждого: есть ли уже событие в базе → официальная страница (если robots.txt разрешает) → статьи.
Найденная дата без события → событие: announced (ожидаются билеты) или scheduled (без билетов).
Дату, которой нет на сайте, владелец вносит в data/recurring_events.json (manual_start / manual_end).
Запуск: python scripts/check_recurring.py [--no-fetch]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import recurring  # noqa: E402
from pipeline.db import connect  # noqa: E402

# Pantheon (*.cam.ac.uk) отказывает Python-клиенту по отпечатку TLS: curl с тем же User-Agent (решение после этапа 1).
CURL_HOSTS = {"www.festival.cam.ac.uk", "www.opencambridge.cam.ac.uk"}


def main() -> None:
    con = connect()
    recurring.seed(con)
    http = PoliteClient(curl_hosts=CURL_HOSTS)
    run_id = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        report = recurring.check(con, http, run_id, fetch_pages="--no-fetch" not in sys.argv)
    finally:
        http.close()
    con.commit()
    for r in report:
        dates = f"{r['found_date'] or '…'}–{r['found_date_end']}" if r["found_date_end"] else (r["found_date"] or "")
        print(f"{r['rec_id']} {r['name'][:38]:38} мес.{r['month']:6} {r['status']:22} {dates:22} {str(r['source'] or '')[:70]}")


if __name__ == "__main__":
    main()
