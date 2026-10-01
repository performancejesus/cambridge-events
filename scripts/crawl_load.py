"""Этап 7e, «Бережный сбор»: сколько запросов к каждому сайту в сутки — до общего слоя (30.09) и по новым правилам.

До (30.09, нижняя граница): запросы прогонов коллекторов за сутки (история data/raw/_run.json в git) + отметки времени
в базе (страницы событий, перепроверка статусов, обогащение, продавцы билетов, проверка ссылок, детские провайдеры,
страницы для модели) — в таблицах хранится только последнее время запроса адреса, поэтому это нижняя граница.
По новым правилам (оценка на сутки): один прогон коллекторов (запросы последнего прогона источника) + перепроверка
статусов только тех страниц, которых не было в сборе этого дня (одна и та же страница — раз в сутки, из общего кэша).
Факт 01.10 — журнал request_log общего слоя (data/http_state.db).

Запуск: python scripts/crawl_load.py → data/crawl_load_7e.json
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import http  # noqa: E402
from pipeline.knowledge import _registry_rows  # noqa: E402

DAY = "2026-09-30"
TABLES = [("detail_pages", "url", "fetched_at"), ("page_status", "url", "checked_at"), ("event_pages", "url", "fetched_at"),
          ("ticket_vendors", "page_url", "checked_at"), ("link_checks", "url", "checked_at"),
          ("kids_page_cache", "url", "fetched_at"), ("llm_list_cache", "url", "fetched_at")]


def host(u: str | None) -> str | None:
    m = re.match(r"https?://([^/]+)", u or "")
    return m.group(1).lower().removeprefix("www.") if m else None


def source_hosts() -> dict[str, str]:
    out = {}
    for r in _registry_rows():
        h = host(str(r.get("Endpoint для сбора") or "")) or host(str(r.get("URL") or ""))
        if h:
            out[r["ID"]] = h
    return out


def runs_on(day: str) -> list[dict]:
    from block_diagnosis import run_history
    return [h for h in run_history() if h["started_at"].startswith(day)]


def main(db: Path) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    con = sqlite3.connect(db)
    sh = source_hosts()
    before: dict[str, Counter] = defaultdict(Counter)
    for h in runs_on(DAY):
        hh = sh.get(h["source"])
        if hh and h["requests"]:
            before[hh]["коллекторы"] += h["requests"]
            before[hh]["прогонов"] += 1
    for table, ucol, tcol in TABLES:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
            continue
        for (u,) in con.execute(f"SELECT {ucol} FROM {table} WHERE {tcol} LIKE ?", (DAY + "%",)):
            hh = host(u)
            if hh and not (table == "detail_pages"):   # страницы событий коллектора уже в запросах прогонов
                before[hh][table] += 1
    # по новым правилам: последний прогон каждого источника + статусы страниц, которых не было в сборе
    last = {}
    for h in runs_on(DAY):
        last[h["source"]] = h
    plan: Counter = Counter()
    for sid, h in last.items():
        if sh.get(sid) and h["requests"]:
            plan[sh[sid]] += h["requests"]
    collected = {u for (u,) in con.execute("SELECT url FROM detail_pages")}
    for (u,) in con.execute("SELECT url FROM page_status WHERE checked_at LIKE ?", (DAY + "%",)):
        if u not in collected and host(u):
            plan[host(u)] += 1
    st = http.state()
    fact = Counter()
    fact_cache = Counter()
    for r in st.execute("SELECT host, result, count(*) FROM request_log WHERE ts >= '2026-10-01' GROUP BY host, result"):
        hh = r[0].lower().removeprefix("www.")
        if r[1] in ("network", "not_modified", "robots"):
            fact[hh] += r[2]
        elif r[1] == "cache":
            fact_cache[hh] += r[2]
    rows = []
    for hh in sorted(set(before) | set(plan) | set(fact), key=lambda x: -sum(before[x].values())):
        b = before.get(hh, Counter())
        total_b = sum(v for k, v in b.items() if k != "прогонов")
        rows.append({"host": hh, "before_total": total_b, "before_runs": b.get("прогонов", 0),
                     "before_detail": {k: v for k, v in b.items() if k not in ("прогонов",)},
                     "plan_per_day": plan.get(hh, 0), "fact_2026_10_01": fact.get(hh, 0),
                     "cache_hits_2026_10_01": fact_cache.get(hh, 0)})
    out = {"day_before": DAY, "rows": rows,
           "totals": {"before": sum(r["before_total"] for r in rows), "plan": sum(r["plan_per_day"] for r in rows),
                      "fact_2026_10_01": sum(fact.values()), "cache_hits_2026_10_01": sum(fact_cache.values())}}
    (ROOT / "data" / "crawl_load_7e.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    db = Path(sys.argv[sys.argv.index("--db") + 1]) if "--db" in sys.argv else ROOT / "data" / "events.db"
    r = main(db)
    print(r["totals"])
    for x in r["rows"][:30]:
        print(f"{x['host'][:38]:38} до {x['before_total']:4} (прогонов {x['before_runs']}) · план {x['plan_per_day']:4} · 01.10 {x['fact_2026_10_01']}")
