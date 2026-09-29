"""Этап 6b: отчёт docs/stage6b_report.md (аудит пропусков через Keenable, газеты с ИИ-запретом, провайдеры детских
программ, выпуск v5, расход). Все цифры — из базы (keenable_*, search_*, newspaper_primary, llm_usage) и файлов выпуска.

  python scripts/stage6b_report.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gap_audit import AGGREGATORS, LISTED, QUERIES  # noqa: E402
from newspaper_primary import reviewed  # noqa: E402
from pipeline import domains, keenable  # noqa: E402
from pipeline.db import connect  # noqa: E402

OUT = ROOT / "docs" / "stage6b_report.md"
STAGE_START = "2026-09-28T20:"          # расход этапа: вызовы Claude API после начала этапа 6b
GROUP_RU = {"categories": "категории", "towns": "городки", "openings": "открытия", "open_spaces": "поля и парки",
            "churches": "церкви", "family_places": "семейные места", "kids_providers": "детские программы"}
CAT_RU = {"concert": "концерты", "church_music": "церковная музыка", "theatre": "театр", "comedy": "комедия",
          "family": "семейное", "talk": "лекции", "exhibition": "выставки", "film": "кино", "market_fair": "рынки и ярмарки",
          "festival": "фестивали", "food_drink": "еда и напитки", "sport": "спорт", "nightlife": "вечеринки",
          "heritage_outdoor": "прогулки и природа", "other": "другое", "none": "—", None: "—"}
VERIFY_RU = {None: "не проверялось (вне зоны или позже 31.12)", "verified": "подтверждено на странице", "name_only": "название есть, даты рядом нет",
             "not_found": "на странице не найдено", "disallowed": "robots.txt закрывает", "fetch_error": "страница не открылась",
             "skipped": "не проверялось (позже 31.12 или вне зоны)"}


def table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return out


def main() -> None:
    con = connect()
    L: list[str] = ["# Этап 6b — аудит пропусков через Keenable (2026-09-28)", ""]
    reg = {h: [x for x in v if x != "S148"] for h, v in domains.registry_hosts(con).items()}   # S148 — сам поиск
    review = json.loads((ROOT / "data" / "search_review.json").read_text())
    reject = {int(k) for k in review["reject"]}
    rb = domains.robots(con)

    # --- ключи и запросы ---
    use = keenable.usage(con)
    total_req = sum(v["requests"] for v in use.values()) + 1
    L += ["## Проверка ключей и тестовый запрос", "",
          "- `KEENABLE_API_KEY` и `EVENTS_ANTHROPIC_KEY` заданы (значения не выводились).",
          "- Тестовый запрос `POST https://api.keenable.ai/v1/search` («Cambridge events October 2026», 5 результатов) — "
          "**HTTP 200** за 0,44 с. Клиент — `pipeline/keenable.py` (заголовок `X-API-Key`, кэш `keenable_cache`, учёт "
          "`keenable_usage`); `/v1/fetch` не используется — страницы читает наш бот с учётом robots.txt.", ""]

    # --- 1. запросы ---
    groups = ["categories", "towns", "openings", "open_spaces", "churches", "family_places"]
    L += ["## 1. Запросы", "",
          f"Аудит — {sum(len(QUERIES[g]) for g in groups)} запросов (`data/keenable_queries.json`), по 10 результатов: "
          + ", ".join(f"{GROUP_RU[g]} — {len(QUERIES[g])}" for g in groups)
          + f". Отдельно — {len(QUERIES['kids_providers'])} запросов о провайдерах детских программ (для 6c) и "
          f"{use.get('newspaper_primary', {}).get('requests', 0)} запросов о первоисточниках газетных пунктов (п. 5).", ""]
    pages = con.execute("SELECT count(*) FROM search_results WHERE purposes LIKE '%gap_audit%'").fetchone()[0]
    ai_pages = con.execute("SELECT count(*) FROM search_results WHERE purposes LIKE '%gap_audit%' AND extracted=2").fetchone()[0]
    area = Counter(r[0] for r in con.execute("SELECT area FROM search_results WHERE purposes LIKE '%gap_audit%' AND extracted=1"))
    L += [f"Уникальных страниц в выдаче аудита — {pages}. Из них {ai_pages} — на сайтах, чей robots.txt закрыт для ИИ-агентов "
          "Anthropic (газеты Cambridge News, Cambridge Independent, Peterborough Telegraph, Newsquest, talks.cam, BBC и др.): "
          "их сниппеты в модель не передавались. Остальные разобраны Haiku по заголовку и сниппету (`prompts/search_extract.md`): "
          f"о зоне — {area['in_area']}, о другом месте (в т.ч. Cambridge, Massachusetts) — {area['elsewhere']}, "
          f"неясно — {area['unclear']}.", ""]

    # --- 2. сравнение с базой ---
    st = Counter((r[0], r[1]) for r in con.execute("""SELECT i.kind, i.status FROM search_items i JOIN search_results s
        USING(url) WHERE s.purposes LIKE '%gap_audit%'"""))
    ev = {k[1]: v for k, v in st.items() if k[0] == "event"}
    op = {k[1]: v for k, v in st.items() if k[0] in ("opening", "closure")}
    L += ["## 2. Сравнение с базой", "",
          "Из сниппетов извлечены конкретные события и открытия; каждое сравнивалось с базой (название + даты, нечётко; "
          "затем — то же название на другую дату ±120 дней; открытия — с `venue_news` и списками арендаторов ТЦ).", ""]
    L += table(["", "события", "открытия/закрытия"], [
        ["уже в базе", ev.get("in_db", 0), op.get("in_db", 0)],
        ["в базе, но на другую дату (ошибка даты в сниппете)", ev.get("in_db_other_date", 0), "—"],
        ["в списке арендаторов ТЦ (база, не новость)", "—", op.get("in_store_list", 0)],
        ["**нет в базе (кандидат в пропуски)**", f"**{ev.get('gap', 0)}**", f"**{op.get('gap', 0)}**"],
        ["прошедшие", ev.get("past", 0), "—"], ["без даты", ev.get("no_date", 0), "—"],
        ["вне зоны / неясно", ev.get("out_of_zone", 0) + ev.get("unclear", 0), op.get("out_of_zone", 0)]])
    covered = ev.get("in_db", 0) + ev.get("in_db_other_date", 0)
    L += ["", f"Покрытие будущих событий зоны, которые нашёл поиск: {covered} из {covered + ev.get('gap', 0)} "
          f"({covered / max(1, covered + ev.get('gap', 0)):.0%}) уже в базе — по сырым кандидатам (в них много ошибок "
          "извлечения из сниппетов); по подтверждённым пропускам — см. ниже.", ""]

    gaps = con.execute("SELECT * FROM search_gaps").fetchall()
    vst = Counter(g["verify"] for g in gaps)
    L += [f"Одинаковые пункты с разных страниц склеены: **{len(gaps)} пропусков** "
          f"({sum(g['kind'] == 'event' for g in gaps)} событий, {sum(g['kind'] != 'event' for g in gaps)} открытий/закрытий). "
          "Каждый проверен на странице нашим ботом (robots.txt, без модели): название есть на странице, и ближайшая к "
          "названию дата — нужная (у листингов на странице много дат подряд; первая версия проверки «дата где-то рядом» "
          "подтверждала, например, органные концерты King's на каждое воскресенье).", ""]
    L += table(["проверка", "пропусков"], [[VERIFY_RU.get(k, k), v] for k, v in vst.most_common()])
    rej = [g for g in gaps if g["verify"] == "verified" and g["gap_id"] in reject]
    L += ["", f"Подтверждённые я просмотрел вручную и отклонил {len(rej)} (`data/search_review.json`): "
          + "; ".join(f"{g['name'][:40]} — {review['reject'][str(g['gap_id'])][:70]}" for g in rej) + ".",
          "Дальше «пропуск» = подтверждённый на странице и не отклонённый; остальные — кандидаты, не факты.", ""]

    # по категориям
    ver = [g for g in gaps if g["verify"] == "verified" and g["gap_id"] not in reject]
    win = [g for g in ver if g["kind"] == "event" and "2026-10-01" <= g["date_start"] <= "2026-10-11"]
    cat = Counter(CAT_RU.get(g["category"], g["category"]) for g in ver if g["kind"] == "event")
    cat_all = Counter(CAT_RU.get(g["category"], g["category"]) for g in gaps if g["kind"] == "event")
    L += ["### Пропуски по категориям", "",
          f"Подтверждённых событий-пропусков — {sum(cat.values())} (из них в окне выпуска 1–11 октября — {len(win)}), "
          f"открытий/закрытий — {sum(g['kind'] != 'event' for g in ver)}.", ""]
    L += table(["категория", "подтверждено", "кандидатов всего"],
               [[k, cat.get(k, 0), v] for k, v in cat_all.most_common()])
    grp = Counter()
    for g in ver:
        for x in json.loads(g["groups_"]):
            grp[GROUP_RU.get(x, x)] += 1
    L += ["", "По группам запросов (подтверждённые; пропуск может прийти из нескольких групп): "
          + ", ".join(f"{k} — {v}" for k, v in grp.most_common()) + ".", ""]

    # --- 3. домены ---
    hosts: dict[str, dict] = defaultdict(lambda: {"all": 0, "ver": 0, "names": []})
    for g in gaps:
        for h in set(json.loads(g["hosts"])):
            hosts[h]["all"] += 1
            if g["verify"] == "verified" and g["gap_id"] not in reject:
                hosts[h]["ver"] += 1
                if len(hosts[h]["names"]) < 3 and g["name"] not in hosts[h]["names"]:
                    hosts[h]["names"].append(g["name"])
    top = sorted(hosts.items(), key=lambda kv: (-kv[1]["ver"], -kv[1]["all"]))[:20]
    L += ["## 3. Откуда пропуски — топ-20 доменов", "",
          "Домен считается для пропуска, если он был среди страниц, где пропуск найден. «Реестр» — есть ли домен среди "
          "источников реестра v0.6 (URL, endpoint или ссылки собранных событий).", ""]
    rows = []
    for h, x in top:
        r = rb.get(h)
        robots = "—" if not r else ("открыт" if r["bot_allowed"] else "закрыт") + (", ИИ-запрет" if r["ai_blocked"] else "")
        kind = "агрегатор" if h in AGGREGATORS else "первоисточник/сайт"
        rows.append([h, x["ver"], x["all"], ", ".join(reg.get(h, [])) or "нет", robots, kind,
                     "; ".join(n[:40] for n in x["names"])])
    L += table(["домен", "подтв.", "всего", "реестр", "robots.txt", "тип", "примеры"], rows)
    L += [""]
    L += (ROOT / "docs" / "stage6b_notes.md").read_text().splitlines() if (ROOT / "docs" / "stage6b_notes.md").exists() else []

    # --- 5. газеты ---
    rows = reviewed(con)
    by = Counter(r["best_type"] for r in rows)
    ok = by["primary"] + by["aggregator"]
    cu = [r for r in rows if r["claude_user_blocked"]]
    cu_ok = sum(r["best_type"] in ("primary", "aggregator") for r in cu)
    tr = [r for r in rows if not r["claude_user_blocked"]]
    tr_ok = sum(r["best_type"] in ("primary", "aggregator") for r in tr)
    verified_links = sum("страница проверена: название и дата" in (r["note"] or "") for r in rows)
    L += ["## 5. Зависимость от газет с ИИ-запретом", "",
          f"Пункты, которые сейчас есть **только** в статьях Cambridge News (S004, S093), Cambridge Independent (S003, S092), "
          f"Peterborough Telegraph (S010) и Newsquest (S116–S119): {sum(r['kind'] == 'event' for r in rows)} будущих событий (дата ≥ 28.09) "
          f"и {sum(r['kind'].startswith('venue') for r in rows)} открытий/закрытий, всего **{len(rows)}**. Для каждого — "
          "запрос в Keenable (название + место + месяц); результаты с газетных сайтов и сайтов с ИИ-запретом отброшены до "
          "модели, совпадение с пунктом Haiku оценивал по заголовку и сниппету (`prompts/primary_match.md`), затем ручная "
          "проверка спорных оценок (`data/newspaper_primary_review.json`, 5 поправок).", ""]
    L += table(["нашлось", "пунктов", "доля"], [
        ["на первоисточнике (площадка, организатор, бренд, ТЦ, совет)", by["primary"], f"{by['primary'] / len(rows):.0%}"],
        ["только на агрегаторе", by["aggregator"], f"{by['aggregator'] / len(rows):.0%}"],
        ["только в других СМИ (не первоисточник)", by["other_media"], f"{by['other_media'] / len(rows):.0%}"],
        ["нигде, кроме газеты", by["none"], f"{by['none'] / len(rows):.0%}"]])
    L += ["", f"**Итог: {ok} из {len(rows)} ({ok / len(rows):.0%}) «газетных» пунктов находятся через первоисточник или "
          f"агрегатор; теряется {len(rows) - ok} ({(len(rows) - ok) / len(rows):.0%}).** По режимам флага:",
          f"- `claude_user_only` (Newsquest): {len(cu)} пунктов, находится {cu_ok}, теряется {len(cu) - cu_ok};",
          f"- газеты с запретом ботов обучения/поиска (S003, S004, S010, S092, S093): {len(tr)} пунктов, находится {tr_ok}, "
          f"теряется {len(tr) - tr_ok}.",
          f"- Для {verified_links} событий первоисточник дополнительно проверен на странице (название и ближайшая к нему дата) и "
          "добавлен к событию как ссылка S148 — теперь основная ссылка пункта ведёт на первоисточник, а не на газету.", ""]
    L += ["<details><summary>Все газетные пункты</summary>", ""]
    L += table(["пункт", "дата", "газета", "нашлось", "где", "в реестре", "заметка"],
               [[r["name"][:50], r["date"] or "—", r["sources"], r["best_type"], r["best_host"] or "—",
                 r["in_registry"] or "—", (r["note"] or "")[:110]] for r in rows])
    L += ["", "</details>", ""]

    # --- 6c ---
    kp = json.loads((ROOT / "data" / "kids_providers.json").read_text())
    provs = kp["providers"]
    types = Counter(p["type"].split(" (")[0] for p in provs)
    L += ["## Провайдеры детских программ и лагерей (для этапа 6c)", "",
          f"{len(QUERIES['kids_providers'])} запросов (каникулярные лагеря и клубы, спорт, плавание, драма, STEM, лесные "
          "школы, HAF, справочник семейных услуг, спорт университетов, частные школы, городки зоны). После отсева шума — "
          f"**{len(provs)} сайтов**, из них {sum(not p['type'].startswith(('справочник', 'туристический')) for p in provs)} "
          f"провайдеров и {sum(p['type'].startswith(('справочник', 'туристический')) for p in provs)} справочников/"
          f"туристических сайтов; {sum(p['in_kids_programmes'] for p in provs)} уже есть в срезе 6-v4; "
          f"закрыто для бота — {sum('закрыт' in p['robots'] for p in provs)}. Полный список с типом, каникулами и "
          "robots.txt — `data/kids_providers.json`.", "",
          "По типам: " + ", ".join(f"{k} — {v}" for k, v in types.most_common()) + ".", ""]
    oct_ = [p for p in provs if {"october_half_term", "christmas"} & set(p["holidays"]) and not p["in_kids_programmes"]]
    L += [f"Сайты, где поиск упоминал октябрьские или рождественские программы и которых нет в срезе, — {len(oct_)}; "
          "страницы проверены (robots.txt, текст страницы → Haiku, только то, что написано):", ""]
    L += table(["провайдер", "тип", "результат"],
               [[p["provider"], p["type"], p.get("check", "—")] for p in oct_])
    L += ["", "В `kids_programmes` добавлены K24 (Culford, октябрьские каникулы, 5–12 лет — проверено, без цены и часов) и "
          "K25 (Primary Sports Stars, Mildenhall — не проверено: страница записи без JavaScript пустая).", ""]
    L += ["<details><summary>Все провайдеры</summary>", ""]
    hol_ru = {"october_half_term": "окт", "christmas": "Рожд", "february_half_term": "фев", "easter": "Пасха",
              "may_half_term": "май", "summer": "лето", "term_time": "в четверть"}
    L += table(["провайдер", "сайт", "тип", "каникулы", "robots.txt", "в срезе 6-v4"],
               [[p["provider"], p["host"], p["type"], ", ".join(hol_ru.get(h, h) for h in p["holidays"]) or "—",
                 p["robots"], "да" if p["in_kids_programmes"] else ""] for p in provs])
    L += ["", "</details>", ""]

    # --- выпуск v5 ---
    v5 = ROOT / "docs" / "stage6b_issue.md"
    if v5.exists():
        L += v5.read_text().splitlines()

    # --- расход ---
    L += ["## Расход", ""]
    L += table(["Keenable", "запросов", "успешных", "результатов"],
               [[k, v["requests"], v["ok"], v["results"]] for k, v in use.items()] +
               [["тестовый запрос (до клиента)", 1, 1, 5], ["**итого**", f"**{total_req}**", "", ""]])
    L += ["", f"Бесплатный лимит Keenable — 100 000 запросов в месяц: этап израсходовал {total_req} "
          f"({total_req / 1000:.2f}% месячного лимита). Ответы закэшированы — повторный прогон аудита запросов не тратит.", ""]
    rows = con.execute("""SELECT purpose, model, count(*), sum(input_tokens), sum(output_tokens), sum(cost_usd) FROM llm_usage
        WHERE called_at >= ? GROUP BY 1, 2 ORDER BY 6 DESC""", (STAGE_START,)).fetchall()
    L += table(["Claude API — назначение", "модель", "запросов", "вход", "выход", "$"],
               [[r[0], r[1], r[2], r[3], r[4], f"{r[5]:.4f}"] for r in rows] +
               [["**итого**", "", sum(r[2] for r in rows), "", "", f"**{sum(r[5] for r in rows):.4f}**"]])
    total = con.execute("SELECT sum(cost_usd) FROM llm_usage").fetchone()[0]
    L += ["", "Выпуск v5 собирался дважды ($0.56 + $0.58): после первой сборки выяснилось, что описания находок 6b — фрагменты "
          "страниц со скриптами; описания пересобраны из чистого текста, выпуск собран заново, первый ответ не используется. "
          "«add sport» — пересборка одной рубрики после исправления Town & Gown 10K.",
          f"Всего за проект: ${total:.2f}.", ""]
    OUT.write_text("\n".join(L).rstrip() + "\n")
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
