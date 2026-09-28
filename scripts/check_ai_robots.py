"""ИИ-запреты в robots.txt источников статей → таблица source_ai_policy (без сбора; то же делает run_collectors).

Запуск: python scripts/check_ai_robots.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import ai_policy, extract  # noqa: E402
from pipeline.db import connect  # noqa: E402


def main() -> None:
    con = connect()
    http = PoliteClient()
    out = {}
    for sid in sorted(extract.ARTICLE_SOURCES | extract.NO_LLM_SOURCES):
        row = con.execute("SELECT url FROM articles WHERE source_id=? ORDER BY article_id DESC LIMIT 1", (sid,)).fetchone()
        if row:
            out[sid] = ai_policy.check(con, http, sid, row["url"]) or "нет запрета"
    con.commit()
    http.close()
    print(json.dumps({"respect_ai_disallow": ai_policy.respect_ai_disallow(), "sources": out}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
