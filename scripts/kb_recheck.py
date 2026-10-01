"""Этап 7e: перепроверка постоянных записей базы знаний по расписанию — раз в месяц и к началу триместров.

Постоянные записи: места (venues с kind), организации (провайдеры, клубы, операторы площадок), регулярные секции
(kids_programmes kind=regular), курсы (courses). У каждой — last_verified_at и next_check_at (pipeline/knowledge.py).

Запуск: python scripts/kb_recheck.py          # сколько записей пора перепроверить и когда следующая волна
        python scripts/kb_recheck.py --run    # перепроверить: места (страница «посетить»), провайдеры секций и курсов
Все запросы — через общий слой бережного сбора (страница не чаще раза в сутки, паузы, повтор после ошибки — завтра).
В расписании этапа 8: ежедневный прогон вызывает --run; основная часть записей становится «пора» раз в месяц и за две
недели до начала триместра (сентябрь, январь, апрель).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import courses, kids_collect, knowledge, places_profile  # noqa: E402
from pipeline.db import connect  # noqa: E402


def main() -> None:
    con = connect()
    knowledge.migrate(con)
    due = knowledge.due(con)
    nxt = {t: con.execute(f"SELECT min(next_check_at) FROM {t} WHERE next_check_at > ?", (date.today().isoformat(),)).fetchone()[0]
           for t, _, _ in knowledge.PERMANENT}
    out = {"due_now": {k: len(v) for k, v in due.items()}, "next_wave": nxt,
           "term_starts": [d.isoformat() for d in knowledge.term_starts() if d >= date.today()][:3]}
    if "--run" in sys.argv:
        http = PoliteClient(purpose="kb_recheck")
        try:
            out["places"] = places_profile.refresh(con, http, due_only=True)
            hosts = {r[0] for r in con.execute(
                f"SELECT DISTINCT provider_host FROM kids_programmes WHERE prog_id IN ({','.join('?' * len(due['kids_programmes']))})",
                due["kids_programmes"])} if due["kids_programmes"] else set()
            if hosts:
                out["kids_providers"] = kids_collect.collect(con, http, hosts)
            chosts = {r[0] for r in con.execute(
                f"SELECT DISTINCT provider_host FROM courses WHERE course_id IN ({','.join('?' * len(due['courses']))})",
                due["courses"])} if due["courses"] else set()
            if chosts:
                out["course_providers"] = courses.collect(con, http, chosts)
        finally:
            http.close()
        knowledge.schedule(con)
        con.commit()
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
