"""Этап 6: отчёт → docs/stage6_report.md (+ docs/stage6_unique.json для реестра v0.6).

Семейные события — scripts/family_count.py (14 дней от даты прогона) на базе до этапа 6 (копия, путь — BEFORE_DB)
и на текущей. Новые уникальные события источника — будущие события в зоне, у которых все источники — из этапа 6
(до этапа их не было ни в одном источнике). Запросы и время — из data/raw/_run.json (последний прогон источника).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from family_count import family_events  # noqa: E402
from pipeline import ai_policy, geo  # noqa: E402
from pipeline.db import connect  # noqa: E402

STAGE_START = "2026-09-28T16:47:00+00:00"   # коммит брифа этапа 6
BEFORE_DB = Path(sys.argv[1]) if len(sys.argv) > 1 else None
LISTED = ("центр", "до 30 мин", "до часа", "Кембриджшир, дальше часа")
BLOCKS = [("P1", "HTML-источники P1 без коллектора"), ("family", "Семейные источники"),
          ("places", "Семейные места и аттракционы (новая категория, P2)"), ("open", "Поля, церкви, ярмарки"),
          ("P2", "Отложенные P2"), ("P3", "Источники P3")]


def main() -> None:
    con = connect()
    today = date.today()
    dec = {k: v for k, v in json.loads((ROOT / "data" / "p6_decisions.json").read_text()).items() if not k.startswith("_")}
    run = {k: v for k, v in json.loads((ROOT / "data" / "raw" / "_run.json").read_text()).items() if not k.startswith("_")}
    stage6 = {s for s, v in dec.items() if v[1] == "подключён"}

    events = con.execute("""SELECT e.event_id, e.zone, (SELECT group_concat(DISTINCT source_id) FROM event_sources s
        WHERE s.event_id = e.event_id) AS srcs FROM events e
        WHERE coalesce(e.date_end, e.date_start) >= ? AND e.status NOT IN ('past', 'cancelled')""",
                         (today.isoformat(),)).fetchall()
    unique, found, out_zone = Counter(), Counter(), Counter()
    for e in events:
        srcs = set((e["srcs"] or "").split(",")) - {""}
        mine = srcs & stage6
        if not mine:
            continue
        if e["zone"] not in LISTED:
            for s in mine:
                out_zone[s] += 1
            continue
        for s in mine:
            found[s] += 1
        if srcs <= stage6:
            for s in mine:
                unique[s] += 1
    (ROOT / "docs" / "stage6_unique.json").write_text(json.dumps(
        {s: {"unique": unique[s], "in_zone": found[s], "out_of_zone": out_zone[s]} for s in sorted(stage6)},
        ensure_ascii=False, indent=1))

    fam_after = family_events(sqlite3.connect(ROOT / "data" / "events.db"), today)
    fam_before = family_events(sqlite3.connect(BEFORE_DB), today) if BEFORE_DB else []
    fam_src = Counter(s for e in fam_after for s in e["sources"])

    L = [f"# Этап 6 — непокрытые P1, семейные источники, поля и церкви, отложенные P2, P3 ({today.isoformat()})", "",
         "Решения по источникам — `data/p6_decisions.json`, реестр — `data/cambridge_event_sources_v0.6.xlsx` "
         "(лист «Этап 6»). Новые уникальные — будущие события в зоне, которых не было ни в одном источнике до этапа 6.",
         "", "## Семейные события на ближайшие 14 дней", "",
         f"Окно: {today.isoformat()} … +14 дней, события в зоне. Семейное — явная пометка в данных: family / kids / "
         "children / ages / half-term и т.п. в названии, описании или категориях, либо семейная категория, которой "
         "источник сам размечает события (фильтры UCM «Families / Under 5s / 5+ / Family events», раздел Visit "
         "Cambridge family-friendly, раздел Families университетского What's On, Science Centre).", "",
         f"- **До этапа 6: {len(fam_before)}**" + (" — " + "; ".join(f"{e['title']} ({e['date']})" for e in fam_before)
                                                    if fam_before else "") + ".",
         f"- **После: {len(fam_after)}**. По источникам: " + ", ".join(f"{s} — {n}" for s, n in fam_src.most_common()) + ".",
         "", "<details><summary>Список</summary>", ""]
    L += [f"- {e['date']} — {e['title']} ({', '.join(e['sources'])})" for e in sorted(fam_after, key=lambda x: x["date"])]
    L += ["", "</details>", ""]

    total_req = total_sec = 0
    for key, title in BLOCKS:
        ids = [s for s, v in dec.items() if v[3] == key]
        if not ids:
            continue
        L += [f"## {title}", "", "| ID | Решение | Новых уникальных | Всего в зоне | Вне зоны | Запросов / сек | Примечание |",
              "|---|---|---|---|---|---|---|"]
        for sid in sorted(ids, key=lambda s: (-unique[s], s)):
            st, d, note, _ = dec[sid]
            r = run.get(sid, {})
            rq = f"{r.get('requests', '—')} / {r.get('seconds', '—')}" if r and d == "подключён" else "—"
            if r and d == "подключён":
                total_req += r.get("requests", 0)
                total_sec += r.get("seconds", 0)
            L.append(f"| {sid} | {d} | {unique[sid] or '—'} | {found[sid] or '—'} | {out_zone[sid] or '—'} | {rq} | {note} |")
        L.append("")
    L += ["## Нагрузка на ежедневный прогон", "",
          f"Новые коллекторы этапа 6 ({len(stage6)}): первый прогон — {total_req} запросов, {total_sec / 60:.0f} мин "
          "(пауза 2 с на хост; страницы событий Junction, Visit Cambridge, What's On, Theatre Royal, Science Centre, "
          "Eventbrite кэшируются на 7–14 дней, поэтому в обычный день запрашиваются только новые). В обычный день — "
          "примерно 35–45 списков + новые страницы событий (оценка: 60–100 запросов, 3–5 минут).", ""]

    ai = con.execute("SELECT * FROM source_ai_policy ORDER BY source_id").fetchall()
    L += ["## ИИ-запреты в robots.txt: флаг respect_ai_disallow", "",
          f"`data/pipeline_config.json` → `respect_ai_disallow: {str(ai_policy.respect_ai_disallow()).lower()}` (по брифу — "
          "до решения выключен). Включённый флаг переводит источники с ИИ-запретом в режим «заголовок + ссылка, без "
          "модели» (`extract.keyword_news`, как Cambridge BID). Список определяется автоматически при каждом прогоне "
          "коллекторов (`pipeline/ai_policy.py` → таблица `source_ai_policy`; отдельно — `scripts/check_ai_robots.py`).", "",
          "| Источник | Хост | ИИ-запрет | Агенты |", "|---|---|---|---|"]
    L += [f"| {r['source_id']} | {r['host']} | {'да' if r['ai_disallow'] else 'нет'} | {r['agents'] or '—'} |" for r in ai]
    notes = ROOT / "docs" / "stage6_notes.md"
    if notes.exists():
        L += ["", notes.read_text().strip()]
    rows = con.execute("""SELECT purpose, model, count(*) n, sum(cost_usd) c FROM llm_usage WHERE called_at >= ?
        GROUP BY 1, 2 ORDER BY c DESC""", (STAGE_START,)).fetchall()
    total = sum(r["c"] for r in rows)
    L += ["", "## Расход Claude API на этап", "", "| Назначение | Модель | Запросов | $ |", "|---|---|---|---|"]
    L += [f"| {r['purpose']} | {r['model']} | {r['n']} | {r['c']:.4f} |" for r in rows]
    L += [f"| **итого** | | | **{total:.4f}** |", "",
          f"Всего за проект: ${con.execute('SELECT sum(cost_usd) FROM llm_usage').fetchone()[0]:.2f}.", ""]
    (ROOT / "docs" / "stage6_report.md").write_text("\n".join(L).rstrip() + "\n")
    print("docs/stage6_report.md", len(fam_before), len(fam_after))


if __name__ == "__main__":
    main()
