"""Прогон 7e+: отметить выпуск отправленным — его пункты начинают учитываться в правиле «не повторять 4 недели»,
в отсчёте «Новых анонсов» и в ротации секций (pipeline/history.py). Черновики (status=draft) не учитываются.

Запуск: python scripts/mark_sent.py --issue 2026-10-08 --version v13
        python scripts/mark_sent.py --list            # выпуски и их статус
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import history  # noqa: E402
from pipeline.db import connect  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue")
    ap.add_argument("--version")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    con = connect()
    history.init(con)
    if a.list or not a.issue:
        for r in con.execute("SELECT issue_date, version, status, count(*) FROM issue_items GROUP BY 1, 2, 3 ORDER BY 1, 2"):
            print(*r)
    else:
        print(history.mark_sent(con, a.issue, a.version))
