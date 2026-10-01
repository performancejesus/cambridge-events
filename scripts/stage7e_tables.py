"""Этап 7e: таблицы отчёта docs/stage7e_report.md (Markdown) — из базы, журнала запросов и выпуска v12.

Запуск: python scripts/stage7e_tables.py > scratchpad/tables.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import knowledge, recurring  # noqa: E402
from pipeline.db import connect  # noqa: E402

V12 = ROOT / "issues" / "issue_2026-10-08_v12_model.json"


def md(rows: list[list], head: list[str]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join("" if x is None else str(x).replace("|", "/") for x in r) + " |" for r in rows]
    return "\n".join(out)


def issue_ids() -> dict[str, str]:
    d = json.loads(V12.read_text())["result_post"]["result"]
    out = {}
    for sec in d["sections"]:
        for it in sec["items"]:
            for i in it["ids"]:
                out[i] = sec["rubric"]
    return out


def main() -> None:
    con = connect()
    placed = issue_ids() if V12.exists() else {}
    print("## Сущности\n")
    print(md([[r["entity"], r["table"], r["total"], r["future"], r["permanent"], r["archive"], r["farthest"],
               r["verified"]] for r in knowledge.summary(con)],
             ["Сущность", "Таблица", "Записей", "Будущих", "Постоянных", "Архивных", "Самая дальняя дата",
              "С last_verified_at"]))
    print("\n## Ежегодные\n")
    rows = []
    placed_ev = {}
    for cid, rub in placed.items():
        if cid[0] in "EA" and cid[1:].isdigit():
            placed_ev[int(cid[1:])] = rub
    for r in con.execute("SELECT * FROM recurring_events WHERE rec_id NOT LIKE 'H-%' ORDER BY rec_id"):
        stage, _ = recurring.stage_of(con, r)
        start = r["manual_start"] or r["found_date"]
        end = r["manual_end"] or r["found_date_end"]
        dates = f"{start}" + (f" – {end}" if end and end != start else "") if start else (f"… – {end}" if end else "—")
        tags = "традиция" if "quirky" in (r["tags"] or "") else ""
        rows.append([r["rec_id"], r["name"], tags, stage, dates, (r["status_note"] or r["note"] or "")[:160],
                     placed_ev.get(r["event_id"], "")])
    print(md(rows, ["ID", "Событие", "Тег", "Статус", "Даты", "Заметка", "В v12"]))
    print("\n## Курсы\n")
    cp = json.loads((ROOT / "data" / "course_providers.json").read_text())
    rows = []
    for p in cp["providers"]:
        n = con.execute("SELECT count(*), sum(status='active'), sum(status='active' AND date_start IS NULL) FROM courses "
                        "WHERE provider_host=?", (p["host"],)).fetchone()
        ins = sum(1 for cid in placed if cid.startswith(f"K:{p['host']}:"))
        rows.append([p["name"], p["category"], n[0], n[1] or 0, n[2] or 0, ins, "подключён" if n[0] else
                     "подключён, занятий на странице не найдено"])
    for h, name, url, pr in cp["blocked"]:
        rows.append([name, "", 0, 0, 0, 0, f"«Не разобрано»: {pr}"])
    ev = sum(1 for cid, rub in placed.items() if rub == "learn" and cid.startswith("E"))
    rows.append(["События базы, которые сами являются занятием (Eventbrite, Kettle's Yard, музеи…)", "", "—", "—", "—", ev,
                 "кандидаты рубрики"])
    print(md(rows, ["Источник", "Вид", "Записей в базе", "Активных", "Без даты (постоянные)", "В v12", "Решение"]))
    print("\n## Секции\n")
    ex = json.loads((ROOT / "data" / "kids_providers_extra.json").read_text())["providers"]
    names = {p["host"]: p["provider"] for p in ex}
    rows = []
    for r in con.execute("""SELECT provider_host, max(provider), count(*), sum(recruiting='open'), sum(trial_free),
                            group_concat(DISTINCT category) FROM kids_programmes WHERE kind='regular'
                            AND coalesce(status,'active')='active' GROUP BY provider_host ORDER BY 3 DESC"""):
        ins = sum(1 for cid in placed if cid.startswith("S:") and f":{r[0]}:" in cid)
        rows.append([names.get(r[0], r[1]), r[0], r[5], r[2], r[3] or 0, r[4] or 0, ins])
    print(md(rows, ["Провайдер", "Сайт", "Виды", "Секций в базе", "Идёт набор", "Пробное бесплатно", "В v12"]))
    print("\n## Нагрузка\n")
    load = json.loads((ROOT / "data" / "crawl_load_7e.json").read_text())
    print(md([[x["host"], x["before_total"], x["before_runs"], x["plan_per_day"], x["fact_2026_10_01"],
               x["cache_hits_2026_10_01"]] for x in load["rows"][:40]],
             ["Сайт", "30.09, запросов (≥)", "Прогонов коллектора 30.09", "По новым правилам, в сутки", "01.10 сеть",
              "01.10 из кэша"]))
    print(json.dumps(load["totals"], ensure_ascii=False))


if __name__ == "__main__":
    main()
