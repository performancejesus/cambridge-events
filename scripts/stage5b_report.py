"""Этап 5b: отчёт — решения после этапа 5 и черновик v3 → docs/stage5b_report.md.

География: будущие события вне Кембриджшира в 40–60 км по прямой (правило после этапа 5) — по районам: сколько
ушло в out_of_zone, сколько осталось «до часа» (оценка ≥ 7), сколько не тронуто исключением West Suffolk.
Newsquest: воронка статей RSS → дубли → предфильтр → модель → полезные. Выпуск v3 — пункты по рубрикам и расход.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import extract, geo  # noqa: E402
from pipeline.db import connect  # noqa: E402
from stage5_report import district  # noqa: E402

STAGE_START = "2026-09-28T10:29:57+00:00"   # коммит брифа с «Решениями после этапа 5»
PAPERS = {"S116": "Hunts Post", "S117": "Cambs Times", "S118": "Wisbech Standard", "S119": "Ely Standard"}


def geography(con) -> list[str]:
    today = date.today().isoformat()
    rows = con.execute("""SELECT e.*, p.admin_county AS county, p.admin_district AS pdistrict FROM events e
        LEFT JOIN postcodes p ON replace(upper(p.postcode),' ','') = replace(upper(e.postcode),' ','')
        WHERE coalesce(e.date_end, e.date_start) >= ? AND e.status NOT IN ('past', 'cancelled') AND e.lat IS NOT NULL""",
                       (today,)).fetchall()
    by = defaultdict(Counter)
    kept_titles, exempt_titles = [], []
    for e in rows:
        dist = district(con, e)
        county = e["county"] or con.execute("SELECT county FROM places WHERE lat=? AND lon=?", (e["lat"], e["lon"])).fetchone()
        county = county if isinstance(county, str) or county is None else county[0]
        if geo.in_cambridgeshire(county, dist):
            continue
        km = geo.km(*geo.CENTRE, e["lat"], e["lon"])
        if not geo.NEIGHBOUR_KM < km <= geo.ZONES[2][0]:
            continue
        b = by[dist]
        b["km_min"] = min(b.get("km_min", 99), round(km, 1))
        b["km_max"] = max(b.get("km_max", 0), round(km, 1))
        if dist in geo.NEIGHBOUR_EXEMPT_DISTRICTS:
            b["exempt"] += 1
            exempt_titles.append(f"{e['title']} ({e['importance_score'] or 0:g})")
        elif e["zone"] == geo.OUT_OF_ZONE:
            b["out"] += 1
        else:
            b["kept"] += 1
            kept_titles.append(f"{e['title']} — {e['importance_score']:g}")
    out = sum(b["out"] for b in by.values())
    exempt = sum(b["exempt"] for b in by.values())
    L = ["## География вне Кембриджшира: 40–60 км только для важных", "",
         f"Правило: событие вне графства в {geo.NEIGHBOUR_KM:g}–60 км по прямой — «до часа» только при оценке "
         f"≥ {geo.NEIGHBOUR_MIN_SCORE:g}, иначе `out_of_zone` (`geo.zone` ставит метку «{geo.NEIGHBOUR_IF_IMPORTANT}», "
         "`importance.resolve_neighbours` решает после оценки; при каждом прогоне заново — выросла оценка, событие "
         "вернётся). Внутри графства — как раньше.", "",
         f"- Ушло в `out_of_zone` по правилу (будущие события): **{out}**; осталось благодаря оценке ≥ 7: "
         f"**{sum(b['kept'] for b in by.values())}**" + (f" ({'; '.join(kept_titles)})" if kept_titles else "") + ".",
         f"- Не тронуто исключением West Suffolk (Бери-Сент-Эдмундс): **{exempt}** — без исключения ушло бы "
         f"{out + exempt}. См. «Исключение для Бери» ниже.", "",
         "| Район | км по прямой | ушло в out_of_zone | осталось (≥ 7) | исключение |", "|---|---|---|---|---|"]
    for dist, b in sorted(by.items(), key=lambda x: (-x[1]["out"], x[0])):
        L.append(f"| {dist} | {b['km_min']:g}–{b['km_max']:g} | {b['out'] or '—'} | {b['kept'] or '—'} | {b['exempt'] or '—'} |")
    stev = con.execute("""SELECT count(*) FROM events e JOIN postcodes p ON replace(upper(p.postcode),' ','') =
        replace(upper(e.postcode),' ','') WHERE p.admin_district='Stevenage' AND e.zone NOT IN ('out_of_zone')
        AND coalesce(e.date_end, e.date_start) >= ?""", (today,)).fetchone()[0]
    L += ["", "**Исключение для Бери (на подтверждение).** Бери-Сент-Эдмундс стоит ровно на границе: площадки — "
          "40,3–40,7 км по прямой, и без исключения из выпуска ушли бы все события West Suffolk в этой полосе "
          f"({exempt}, среди них Martin Kemp 6.8, Gilbert O'Sullivan 6.6, Jack Dee 6.3 — все ниже 7). Это противоречит "
          "остальному брифу: вместимость The Apex и Theatre Royal Bury добавлена по вашему решению, а на этапе 6 "
          "Theatre Royal получает собственный коллектор как «один из главных театров зоны»; по дороге (A14) до Бери "
          "~40 минут. Поэтому West Suffolk исключён из правила (`geo.NEIGHBOUR_EXEMPT_DISTRICTS`). Если исключение не "
          "нужно — убрать строку, и события уйдут при следующем прогоне.",
          "",
          f"**Стивенидж правилом не отсекается:** его площадки — 39,6–40,6 км, т.е. большая часть внутри 40 км "
          f"(сейчас в зоне {stev} событий). Прямая линия не отделяет Стивенидж от Бери; варианты — исключения по районам "
          "(Stevenage — в правило 40–60) или время в пути вместо расстояния. В выпуске слабые события «за городом» "
          "режет порог < 3 (правки по v2).", ""]
    return L


def newsquest(con) -> list[str]:
    src = sorted(PAPERS)
    q = ",".join("?" * len(src))
    arts = con.execute(f"SELECT * FROM articles WHERE source_id IN ({q})", src).fetchall()
    st = Counter(a["extract_status"] for a in arts)
    reasons = Counter()
    for a in arts:
        if a["extract_status"] == "filtered":
            r = json.loads(a["result_json"] or "{}").get("prefilter", "")
            reasons["криминал / суд / авария / продажа домов в заголовке" if r.startswith("в заголовке") else "нет ключевых слов"] += 1
    per_paper = Counter(a["source_id"] for a in arts)
    unique = len(arts) - st["duplicate"]
    to_model = sum(st[k] for k in ("useful", "empty", "error", "pending"))
    cost = con.execute("""SELECT count(*), sum(cost_usd), sum(input_tokens), sum(output_tokens) FROM llm_usage
        WHERE purpose='article_extract_batch' AND article_id IN (SELECT article_id FROM articles WHERE source_id IN ({}))""".format(q),
                       src).fetchone()
    pubs = sorted(a["published"] for a in arts if a["published"])
    days = max(1, (date.fromisoformat(pubs[-1][:10]) - date.fromisoformat(pubs[0][:10])).days) if pubs else 7
    got = Counter()
    for a in arts:
        if a["extract_status"] in ("useful", "empty") and a["result_json"]:
            r = json.loads(a["result_json"])
            got["события"] += len([e for e in r.get("events", []) if e.get("date_start")])
            got["открытия/закрытия"] += len(r.get("venue_news", []))
            got["отмены/старт продаж"] += len(r.get("cancellations", [])) + len(r.get("ticket_sales", []))
    useful = [a["title"] for a in arts if a["extract_status"] == "useful"]
    L = ["## Газеты Newsquest (S116–S119)", "",
         "RSS `/news/rss/` четырёх газет (по 50 последних статей). До модели: (1) дедупликация между газетами — номер "
         "материала из URL (`/news/26586199.olly-murs-…/` — один номер во всех четырёх газетах) и нормализованный "
         "заголовок; (2) предфильтр по ключевым словам в заголовке и анонсе RSS (`extract.PREFILTER_RE`: event, festival, "
         "fair, concert, show, opening, opens, to open, closing, market, tickets, cancelled, postponed, theatre, perform, "
         "restaurant, café, shop, welcome, half-term …) и стоп-слова в заголовке (`PREFILTER_NEG_RE`: court, jailed, police, "
         "crash, died, for sale …); (3) Haiku через Message Batches API (−50 %), страница статьи — как у остальных газет.", "",
         "| Шаг | Статей | Отсеяно |", "|---|---|---|",
         f"| Статьи RSS ({', '.join(f'{PAPERS[s]} {per_paper[s]}' for s in src)}) | {len(arts)} | — |",
         f"| 1. После дедупликации между газетами | {unique} | {st['duplicate']} (дубли) |",
         f"| 2. После предфильтра | {to_model} | {st['filtered']} ({'; '.join(f'{k} — {v}' for k, v in reasons.items())}) |",
         f"| 3. Отправлено в модель (Haiku, Batch API) | {to_model} | — |",
         f"| Полезных (есть событие, открытие, отмена) | {st['useful']} | {st['empty']} пустых |", "",
         f"Извлечено: " + ", ".join(f"{k} — {v}" for k, v in got.items()) + ".", "",
         f"Расход: {cost[0]} запросов, {cost[2] or 0} + {cost[3] or 0} токенов = **${cost[1] or 0:.4f}** за статьи "
         f"{pubs[0][:10] if pubs else '?'} … {pubs[-1][:10] if pubs else '?'} ({days} дн.) → **≈ ${(cost[1] or 0) / days * 7:.2f} в неделю** "
         f"(цель ≤ $0.30). Без дедупликации и предфильтра в модель ушло бы {len(arts)} статей "
         f"(≈ ${len(arts) * extract.estimate(con, 1)['cost_per_article_usd'] * extract.BATCH_DISCOUNT:.2f} через Batch, "
         f"≈ ${len(arts) * extract.estimate(con, 1)['cost_per_article_usd']:.2f} обычными запросами).", "",
         "Полезные статьи: " + "; ".join(useful) + ".", ""]
    return L


def issue_counts() -> list[str]:
    ru = (ROOT / "issues" / "issue_2026-10-01_v3_ru.md").read_text()
    m = re.search(r"\*\*Пунктов по рубрикам\*\*\n\n(.*?)\n\n", ru, re.S)
    cost = re.search(r"\*\*Расход Claude API на черновик\*\*\n\n- (.*?)\n", ru)
    L = ["## Черновик v3 (1–11 октября)", "",
         "`issues/issue_2026-10-01_v3_en.md`, `_ru.md`; ответ модели — `_v3_model.json`.", "",
         "Пунктов по рубрикам:", "", m.group(1) if m else "—", "",
         f"Расход на выпуск: {cost.group(1) if cost else '—'}.", ""]
    return L


def costs(con) -> list[str]:
    rows = con.execute("""SELECT purpose, model, count(*) n, sum(cost_usd) c FROM llm_usage WHERE called_at >= ?
        GROUP BY 1, 2 ORDER BY c DESC""", (STAGE_START,)).fetchall()
    total = sum(r["c"] for r in rows)
    L = ["## Расход Claude API на этап", "", "| Назначение | Модель | Запросов | $ |", "|---|---|---|---|"]
    L += [f"| {r['purpose']} | {r['model']} | {r['n']} | {r['c']:.4f} |" for r in rows]
    L += [f"| **итого** | | | **{total:.4f}** |", "",
          f"Всего за проект: ${con.execute('SELECT sum(cost_usd) FROM llm_usage').fetchone()[0]:.2f}.", ""]
    return L


def main() -> None:
    con = connect()
    today = date.today().isoformat()
    L = [f"# Этап 5b — решения после этапа 5 и черновик v3 ({today})", ""]
    L += geography(con) + newsquest(con)
    notes = ROOT / "docs" / "stage5b_notes.md"
    if notes.exists():
        L += [notes.read_text().strip(), ""]
    L += issue_counts() + costs(con)
    (ROOT / "docs" / "stage5b_report.md").write_text("\n".join(L).rstrip() + "\n")
    print("docs/stage5b_report.md")


if __name__ == "__main__":
    main()
