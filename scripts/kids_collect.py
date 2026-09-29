"""Этап 6c: коллектор провайдеров детских программ (ежедневный прогон; модель — только при изменении страницы).

  python scripts/kids_collect.py              # все провайдеры → kids_programmes, «Не разобрано», data/kids_collect_6c.json
  python scripts/kids_collect.py host1 host2  # выбранные
  python scripts/kids_collect.py --reminders  # за 6 недель до каникул: сколько программ и у кого данных нет
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import kids_collect  # noqa: E402
from pipeline.db import connect  # noqa: E402

if __name__ == "__main__":
    con = connect()
    if "--reminders" in sys.argv:
        print(json.dumps(kids_collect.reminders(con), ensure_ascii=False, indent=1))
    else:
        only = set(a for a in sys.argv[1:] if not a.startswith("-")) or None
        print(json.dumps(kids_collect.collect(con, PoliteClient(), only), ensure_ascii=False, indent=1))
