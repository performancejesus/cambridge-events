"""Этап 3: отчёт по базе events.db → docs/stage3_report.md."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import extract  # noqa: E402
from pipeline.db import connect  # noqa: E402

REPORT = ROOT / "docs" / "stage3_report.md"
NOTES = ROOT / "docs" / "stage3_notes.md"
TODAY = date.today().isoformat()


def one(con, q, *a):
    return con.execute(q, a).fetchone()[0]


def pct(a, b):
    return f"{round(100 * a / b)}%" if b else "—"


def main() -> None:
    con = connect()
    L = [f"# Этап 3 — нормализация, хранилище, извлечение ({TODAY})", "",
         "База: `data/events.db`. Прогонов в базе: " + str(one(con, "SELECT count(DISTINCT run_id) FROM runs")) + ".", ""]

    raw_ev = one(con, "SELECT count(*) FROM raw_items WHERE kind='event' AND event_id IS NOT NULL")
    ev = one(con, "SELECT count(*) FROM events WHERE source_type='feed'")
    fut = one(con, "SELECT count(*) FROM events WHERE coalesce(date_end,date_start) >= ?", TODAY)
    multi = one(con, "SELECT count(*) FROM (SELECT event_id FROM event_sources GROUP BY event_id HAVING count(DISTINCT source_id) > 1)")
    L += ["## Дедупликация", "",
          f"- Записей-событий от источников (актуальных, связанных): **{raw_ev}** → уникальных событий из фидов: **{ev}** "
          f"(склеено {raw_ev - ev}); всего событий в базе: {one(con, 'SELECT count(*) FROM events')}, из них будущих: {fut}.",
          f"- Событий, найденных в нескольких источниках: {multi}.", "",
          "| Пара источников | Общих событий |", "|---|---|"]
    for a, b, n in con.execute("""SELECT x.source_id, y.source_id, count(DISTINCT x.event_id) FROM event_sources x
            JOIN event_sources y ON x.event_id=y.event_id AND x.source_id < y.source_id GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10"""):
        L.append(f"| {a} × {b} | {n} |")

    L += ["", "## Площадки, геокодирование, цены", ""]
    fe = "coalesce(date_end,date_start) >= ?"
    L += [f"- Справочник площадок: {one(con, 'SELECT count(*) FROM venues')} "
          f"(вручную {one(con, 'SELECT count(*) FROM venues WHERE origin=?', 'manual')}, из событий {one(con, 'SELECT count(*) FROM venues WHERE origin=?', 'events')}), "
          f"с координатами {one(con, 'SELECT count(*) FROM venues WHERE lat IS NOT NULL')}.",
          f"- Будущие события с postcode: {pct(one(con, f'SELECT count(*) FROM events WHERE postcode IS NOT NULL AND {fe}', TODAY), fut)}, "
          f"с координатами и зоной: {pct(one(con, f'SELECT count(*) FROM events WHERE zone IS NOT NULL AND {fe}', TODAY), fut)}.",
          f"- talks.cam: postcode у {pct(one(con, 'SELECT count(*) FROM events e WHERE postcode IS NOT NULL AND EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id=e.event_id AND s.source_id=?) AND ' + fe, 'S047', TODAY), one(con, 'SELECT count(*) FROM events e WHERE EXISTS (SELECT 1 FROM event_sources s WHERE s.event_id=e.event_id AND s.source_id=?) AND ' + fe, 'S047', TODAY))} будущих событий (было 6% в сырых данных).",
          "- Зоны будущих событий: " + ", ".join(f"{z or 'не определена'} — {n}" for z, n in con.execute(f"SELECT zone, count(*) FROM events WHERE {fe} GROUP BY zone ORDER BY 2 DESC", (TODAY,))) + ".",
          f"- Цена известна у {pct(one(con, f'SELECT count(*) FROM events WHERE price_from IS NOT NULL AND {fe}', TODAY), fut)} будущих событий; "
          f"бесплатных (price_from = 0): {one(con, f'SELECT count(*) FROM events WHERE price_from = 0 AND {fe}', TODAY)}.", ""]

    L += ["## Жизненный цикл", "", "| Статус | Событий |", "|---|---|"]
    for s, n in con.execute("SELECT status, count(*) FROM events GROUP BY status ORDER BY 2 DESC"):
        L.append(f"| {s} | {n} |")
    L += ["", f"Записей в status_history: {one(con, 'SELECT count(*) FROM status_history')}.", ""]

    run = json.loads((ROOT / "data" / "raw" / "_run.json").read_text())
    L += ["## Инкрементальный сбор (последний прогон)", "", "| ID | Ссылок | Из кэша | Запрошено | Запросов всего |", "|---|---|---|---|---|"]
    for sid, r in run.items():
        if r.get("stats") and "cached" in r["stats"]:
            st = r["stats"]
            L.append(f"| {sid} | {st['links']} | {st['cached']} | {st['fetched']} | {r['requests']} |")
    failed = {k: v for k, v in run.items() if not v["ok"]}
    L += ["", f"Коллекторов в прогоне: {len(run)}, упало: {len(failed)}" + (" — " + "; ".join(f"{k}: {v['error'][:120]}" for k, v in failed.items()) if failed else "") + ".", ""]

    L += ["## Статьи и извлечение через Claude API", ""]
    L += ["| Источник | Статей | pending | useful | empty | error |", "|---|---|---|---|---|---|"]
    for sid, n, p, u, e, er in con.execute("""SELECT source_id, count(*), sum(extract_status='pending'), sum(extract_status='useful'),
            sum(extract_status='empty'), sum(extract_status='error') FROM articles GROUP BY source_id ORDER BY source_id"""):
        L.append(f"| {sid} | {n} | {p} | {u} | {e} | {er} |")
    cost = one(con, "SELECT coalesce(sum(cost_usd),0) FROM llm_usage")
    calls = one(con, "SELECT count(*) FROM llm_usage")
    est = extract.estimate(con, len(extract.pending(con)))
    L += ["", f"- Вызовов Claude API: {calls}, расход: **${cost:.4f}** (модель {extract.MODEL}).",
          f"- Ожидают извлечения: {est['articles']} статей; оценка ≈ ${est['total_usd']} "
          f"(~{est['input_tokens_per_article']} входных токенов и ${est['cost_per_article_usd']} на статью).",
          f"- Событий из статей: {one(con, 'SELECT count(*) FROM events WHERE source_type=?', 'article')}; "
          f"открытий/закрытий из статей: {one(con, 'SELECT count(*) FROM venue_news WHERE source_type=?', 'article')}; "
          f"отмен/переносов/старта продаж: {one(con, 'SELECT count(*) FROM event_updates')}.", ""]

    L += ["## Новое в городе (venue_news)", "",
          f"- Всего записей: {one(con, 'SELECT count(*) FROM venue_news')}; по спискам ТЦ: {one(con, 'SELECT count(*) FROM venue_news WHERE source_type=?', 'store_list')}.",
          "- Магазинов в списках ТЦ: " + ", ".join(f"{s} — {n}" for s, n in con.execute("SELECT source_id, count(*) FROM raw_items WHERE kind='store' AND disappeared_at IS NULL GROUP BY 1")) + ".", ""]

    L += ["## Ежегодные события", "", "| ID | Событие | Месяц | Статус | Дата | Где найдено |", "|---|---|---|---|---|---|"]
    for r in con.execute("SELECT * FROM recurring_events ORDER BY rec_id"):
        st = "дата найдена" if r["found_date"] else ("вручную" if r["check_method"] == "manual" else "ожидаем")
        L.append(f"| {r['rec_id']} | {r['name']} | {r['expected_month']} | {st} | {r['found_date'] or '—'} | {(r['found_source'] or '—')[:80]} |")

    L += ["", "## Контрольные примеры", "", "| Пример | Статус | Детали |", "|---|---|---|"]

    def ev_like(pat, extra=""):
        return con.execute(f"SELECT * FROM events WHERE title LIKE ? {extra} ORDER BY date_start", (pat,)).fetchall()

    united = [e for e in con.execute("""SELECT e.* FROM events e JOIN event_sources s USING(event_id)
        WHERE s.source_id='S018' AND e.date_start >= ? ORDER BY e.date_start""", (TODAY,))]
    L.append(f"| Домашние матчи Cambridge United | {'✅' if united else '❌'} | {len(united)} будущих, ближайший {united[0]['date_start']} {united[0]['title'][:40] if united else ''} |")
    for name, pat, extra in [("Mill Road Winter Fair", "%Mill Road Winter Fair%", ""),
                             ("Town and Gown 10k", "%Town and Gown 10%", ""),
                             ("Whittlesea Straw Bear", "%Straw Bear%", ""),
                             ("Thriplow Daffodil Weekend", "%Thriplow%", ""),
                             ("Cambridge Oktoberfest", "%Oktoberfest%", "AND (title LIKE '%Cambridge%' OR venue_name LIKE '%Jesus Green%')")]:
        rows = ev_like(pat, extra)
        rec = con.execute("SELECT * FROM recurring_events WHERE name LIKE ?", (pat,)).fetchone()
        if rows:
            e = rows[-1]
            det = f"{e['date_start']}, статус {e['status']}, источник: {e['source_type']}"
            mark = "✅"
        elif rec:
            det = f"ежегодное {rec['rec_id']}: " + ("вносится вручную" if rec["check_method"] == "manual" else "дата пока не объявлена — ожидаем")
            mark = "⏳"
        else:
            det, mark = "не найдено", "❌"
        L.append(f"| {name} | {mark} | {det} |")
    talks = one(con, "SELECT count(*) FROM events e JOIN event_sources s USING(event_id) WHERE s.source_id='S047' AND e.date_start >= ?", TODAY)
    L.append(f"| Публичные лекции talks.cam | {'✅' if talks else '❌'} | {talks} будущих |")
    for name, pat in [("Uniqlo, Grand Arcade", "%niqlo%"), ("Catte Latte, 184 Mill Road", "%Catte Latte%"), ("Hungarian Soul, 94 Mill Road", "%Hungarian Soul%")]:
        vn = con.execute("SELECT * FROM venue_news WHERE name LIKE ?", (pat,)).fetchone()
        arts = con.execute("SELECT * FROM articles WHERE title LIKE ? OR summary LIKE ?", (pat, pat)).fetchall()
        store = con.execute("SELECT * FROM raw_items WHERE kind='store' AND title LIKE ?", (pat,)).fetchone()
        if vn:
            L.append(f"| {name} | ✅ | venue_news: {vn['stage']} {vn['date'] or ''} ({vn['source_id']}) |")
        else:
            bits = [f"статья {a['source_id']} {str(a['published'])[:10]}: {a['extract_status']}" for a in arts[:2]]
            if store:
                bits.append(f"есть в списке магазинов {store['source_id']} с первого прогона (база, не «новый»)")
            L.append(f"| {name} | {'⏳' if arts else '❌'} | {'; '.join(bits) or 'не найдено'} |")
    if NOTES.exists():
        L += ["", NOTES.read_text().strip()]
    REPORT.write_text("\n".join(L) + "\n")
    print(f"Отчёт: {REPORT}")


if __name__ == "__main__":
    main()
