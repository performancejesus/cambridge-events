"""Этап 7e: курсы и мастер-классы для взрослых (рубрика «Научиться») — провайдеры из data/course_providers.json.

Запуск: python scripts/courses_collect.py [host ...]   → таблица courses (S184), «Не разобрано» для закрытых
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import courses  # noqa: E402
from pipeline.db import connect  # noqa: E402

if __name__ == "__main__":
    con = connect()
    http = PoliteClient(purpose="courses_collect")
    try:
        print(json.dumps(courses.collect(con, http, set(sys.argv[1:]) or None), ensure_ascii=False, indent=1))
    finally:
        http.close()
