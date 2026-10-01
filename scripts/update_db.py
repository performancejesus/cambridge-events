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

from pipeline import evergreen, extract, importance, ingest, kids, open_spaces, recurring, roundups, venues  # noqa: E402
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
    stats |= ingest.merge_same(con)          # дубли внутри одного источника
    stats |= ingest.merge_mlc(con)           # этап 7d: дубли musiclivecambridge (slug + дата + площадка)
    stats |= ingest.refresh(con, run_id)
    stats |= ingest.store_changes(con, run_id)
    stats |= open_spaces.tag(con)             # события на лугах, в парках, на площадях
    stats |= evergreen.tag(con)               # постоянные продукты для туристов — не события
    stats |= roundups.tag(con)                # подборки («Things to do…») — не события, разбираются отдельно
    stats |= kids.load(con)                   # детские программы на каникулы (data/kids_programmes.json)
    stats |= importance.resolve_neighbours(con)   # 40–60 км вне графства: по уже известным оценкам (новые — после оценки)
    from pipeline import knowledge           # этап 7e: база знаний — last_verified_at, архив, организации, перепроверка
    stats["knowledge"] = knowledge.migrate(con)
    con.commit()
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
