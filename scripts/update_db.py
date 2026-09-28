"""Этап 3: загрузка последнего прогона коллекторов (data/raw) в data/events.db.

Запуск: python scripts/update_db.py            # загрузить data/raw и пересчитать
        python scripts/update_db.py --no-load  # только пересчитать (после извлечения из статей)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import extract, importance, ingest, recurring, venues  # noqa: E402
from pipeline.db import connect  # noqa: E402


def main() -> None:
    con = connect()
    if "--no-load" in sys.argv:  # только дедупликация/сведение (например, после извлечения из статей)
        run_id = con.execute("SELECT max(run_id) FROM runs").fetchone()[0]
        stats = {"run_id": run_id}
    else:
        stats = ingest.load_run(con, ROOT / "data" / "raw")
        run_id = stats["run_id"]
    recurring.seed(con)                     # флаги билетов ежегодных событий нужны для статусов
    stats |= extract.keyword_news(con)       # Cambridge BID: только заголовки, без LLM
    stats |= extract.newsquest_prefilter(con)  # Newsquest: дубли между газетами и предфильтр — до модели
    stats |= venues.build(con)
    stats |= ingest.dedupe(con, run_id)
    stats |= ingest.apply_merges(con)        # data/manual_merges.json
    stats |= ingest.refresh(con, run_id)
    stats |= ingest.store_changes(con, run_id)
    stats |= importance.resolve_neighbours(con)   # 40–60 км вне графства: по уже известным оценкам (новые — после оценки)
    con.commit()
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
