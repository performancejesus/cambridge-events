"""Этап 7e (уточнение 01.10): диагностика закрывшихся для нашего бота сайтов — без обращений к самим сайтам.

По каждому домену: когда первая ошибка (пустой ответ, заглушка, 403/307, неразборчивый ответ), сколько наших запросов к
домену было за сутки до неё и какими модулями, не менялись ли User-Agent и способ запроса (по git), исходящий IP.

Источники данных: таблица runs (прогоны коллекторов), история data/raw/_run.json в git (запросов за прогон по
источнику), отметки времени в базе — detail_pages (страницы событий коллектора), page_status (перепроверка статусов),
event_pages (обогащение), ticket_vendors (продавцы билетов), link_checks (проверка ссылок выпуска), unparsed_sources
(проверки «Не разобрано»), kids_page_cache / llm_list_cache (страницы для модели). В таблицах хранится только последнее
время запроса каждого адреса — счёт по ним нижняя граница.

Запуск: python scripts/block_diagnosis.py [--db путь к снимку базы] → data/block_diagnosis_7e.json
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SITES = [  # домен, источник, что это
    ("junction.co.uk", "S012", "Cambridge Junction"),
    ("cambridgeppf.org", "S131", "Cambridge Past, Present & Future"),
    ("visitcambridge.org", "S001", "Visit Cambridge"),
    ("visitwestnorfolk.com", "S183", "Visit West Norfolk"),
    ("cus.org", "S049", "Cambridge Union"),
    ("dow.cam.ac.uk", "S163", "Heong Gallery (Downing College)"),
    ("theatreroyal.org", "S126", "Theatre Royal Bury St Edmunds"),
]
TABLES = [  # таблица, колонка адреса, колонка времени, модуль
    ("detail_pages", "url", "fetched_at", "коллектор: страницы событий"),
    ("page_status", "url", "checked_at", "recheck_status (статусы)"),
    ("event_pages", "url", "fetched_at", "enrich_pages (обогащение)"),
    ("ticket_vendors", "page_url", "checked_at", "ticket_vendors (продавцы)"),
    ("link_checks", "url", "checked_at", "проверка ссылок выпуска (правило 7)"),
    ("unparsed_sources", "url", "last_checked", "проверки «Не разобрано» / places_7d --probe"),
    ("kids_page_cache", "url", "fetched_at", "kids_collect (страницы провайдеров)"),
    ("llm_list_cache", "url", "fetched_at", "коллектор: страница → модель"),
]


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")[:25]).replace(tzinfo=None)


def run_history() -> list[dict]:
    """Все прогоны из истории data/raw/_run.json: источник → запросов, событий, ошибка, время начала."""
    out, seen = [], set()
    commits = subprocess.run(["git", "log", "--format=%h", "--", "data/raw/_run.json"], cwd=ROOT,
                             capture_output=True, text=True).stdout.split()
    for c in commits:
        try:
            d = json.loads(subprocess.run(["git", "show", f"{c}:data/raw/_run.json"], cwd=ROOT,
                                          capture_output=True, text=True).stdout)
        except ValueError:
            continue
        for sid, e in d.items():
            if sid.startswith("_") or not isinstance(e, dict):
                continue
            key = (sid, e.get("started_at"))
            if key in seen or not e.get("started_at"):
                continue
            seen.add(key)
            out.append({"source": sid, "started_at": e["started_at"], "ok": e.get("ok"), "events": e.get("events"),
                        "requests": e.get("requests"), "error": (e.get("error") or "")[:120]})
    return sorted(out, key=lambda x: x["started_at"])


def git_changes(paths: list[str]) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%ad %h %s", "--date=format:%Y-%m-%d %H:%M", "--", *paths], cwd=ROOT,
                         capture_output=True, text=True).stdout.splitlines()
    return [x[:140] for x in out]


def ua_changes() -> list[str]:
    log = subprocess.run(["git", "log", "-p", "--format=COMMIT %h %ad", "--date=format:%Y-%m-%d", "--",
                          "collectors/http.py"], cwd=ROOT, capture_output=True, text=True).stdout
    out, cur = [], None
    for line in log.splitlines():
        if line.startswith("COMMIT "):
            cur = line[7:]
        elif line.startswith(("+USER_AGENT", "-USER_AGENT", "+DELAY_SECONDS", "-DELAY_SECONDS", "+CURL_SUFFIXES",
                              "-CURL_SUFFIXES")):
            out.append(f"{cur}: {line[:110]}")
    return out


def main(db_path: Path) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    hist = run_history()
    result = {"built": datetime.now().isoformat(timespec="seconds"), "db": str(db_path), "user_agent_changes": ua_changes(),
              "outgoing_ip_7e": "160.79.106.128–131 (AS396982 Google LLC, Columbus, US; адрес меняется между запросами)",
              "sites": []}
    for host, sid, name in SITES:
        runs = [dict(r) for r in con.execute("SELECT run_id, ok, items, error FROM runs WHERE source_id=? ORDER BY run_id",
                                             (sid,))]
        good = [r for r in runs if r["ok"] and r["items"]]
        bad = [r for r in runs if not (r["ok"] and r["items"]) and (not good or r["run_id"] > good[0]["run_id"])]
        first_bad = next((r for r in runs if good and r["run_id"] > good[0]["run_id"] and not (r["ok"] and r["items"])), None) \
            or (bad[0] if bad else None)
        site = {"host": host, "source": sid, "name": name, "runs": runs, "first_error": first_bad,
                "last_ok": max((r["run_id"] for r in good), default=None)}
        if first_bad:
            t1 = ts(first_bad["run_id"])
            t0 = t1 - timedelta(hours=24)
            by_module: dict[str, int] = {}
            for table, ucol, tcol, module in TABLES:
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                    continue
                n = con.execute(f"SELECT count(*) FROM {table} WHERE {ucol} LIKE ? AND {tcol} >= ? AND {tcol} < ?",
                                (f"%{host}%", t0.isoformat(), t1.isoformat() + "+99")).fetchone()[0]
                if n:
                    by_module[module] = n
            coll = [h for h in hist if h["source"] == sid and t0.isoformat() <= h["started_at"][:19] < t1.isoformat()]
            by_module["коллектор: прогонов за сутки"] = len(coll)
            by_module["коллектор: запросов в этих прогонах (списки и страницы)"] = sum(h["requests"] or 0 for h in coll)
            site["window"] = [t0.isoformat(), t1.isoformat()]
            site["requests_24h_before"] = by_module
            # отметка «страниц событий за сутки» входит в запросы прогонов — в сумму её не добавляем
            site["requests_24h_total_min"] = by_module["коллектор: запросов в этих прогонах (списки и страницы)"] + sum(
                v for k, v in by_module.items() if not k.startswith("коллектор"))
        site["collector_history"] = [h for h in hist if h["source"] == sid]
        site["code_changes"] = git_changes([f"collectors/sources/{m}.py" for m in
                                            ("junction", "cppf", "visit_cambridge", "stage7d", "cambridge_union",
                                             "stage6c", "theatre_royal_bury")
                                            if (host, m) in {("junction.co.uk", "junction"), ("cambridgeppf.org", "cppf"),
                                                             ("visitcambridge.org", "visit_cambridge"),
                                                             ("visitwestnorfolk.com", "stage7d"), ("cus.org", "cambridge_union"),
                                                             ("dow.cam.ac.uk", "stage6c"), ("theatreroyal.org", "theatre_royal_bury")}])[:6]
        result["sites"].append(site)
    out = ROOT / "data" / "block_diagnosis_7e.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    return result


if __name__ == "__main__":
    db = Path(sys.argv[sys.argv.index("--db") + 1]) if "--db" in sys.argv else ROOT / "data" / "events.db"
    r = main(db)
    for s in r["sites"]:
        print(s["host"], s["source"], "last ok:", s["last_ok"], "first error:", (s["first_error"] or {}).get("run_id"),
              (s["first_error"] or {}).get("error"))
        print("   24h before:", s.get("requests_24h_before"), "total≥", s.get("requests_24h_total_min"))
        for h in s["collector_history"][-8:]:
            print("     run", h["started_at"], "ok", h["ok"], "ev", h["events"], "req", h["requests"], h["error"][:60])
    print(r["user_agent_changes"])
