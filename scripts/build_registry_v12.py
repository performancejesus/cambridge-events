"""Этап 7e: data/cambridge_event_sources_v0.12.xlsx из v0.11 (v0.11 не изменяется).

- Лист «Источники»: бережный сбор — заметки о закрывшихся для бота доменах и диагностике (S001, S012, S131, S183, S049,
  S163, S126); снятые ограничения окна (S008, S048, S105, S168 и др.); Visit Ely (S113) — страница собственных событий;
  новые S184 (курсы и мастер-классы для взрослых) и S185 (детские секции и клубы).
- Новые листы: «Курсы» (провайдеры «Научиться»), «Секции» (клубы и провайдеры регулярных секций), «Нагрузка на сайты»
  (запросов в сутки до общего слоя и по новым правилам), «Ежегодные» (recurring_events со статусом).
- Лист «Не разобрано» — свежая выгрузка unparsed_sources.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_registry_v04 import HEADER_FILL, HEADER_FONT  # noqa: E402
from pipeline import recurring, unparsed  # noqa: E402
from pipeline.db import connect  # noqa: E402

SRC = ROOT / "data" / "cambridge_event_sources_v0.11.xlsx"
DST = ROOT / "data" / "cambridge_event_sources_v0.12.xlsx"
T = "2026-10-01"
NOTES = {
    "S001": "Этап 7e: заглушка Sucuri на страницах событий с прогона 30.09 21:25 (до этого 98 событий; за сутки до закрытия — "
            "≈39 наших запросов). Домен на паузе 24 ч (общий слой бережного сбора), затем один запрос к главной. Без источника "
            "теряем 40 будущих событий, которые были только здесь (15 в окне 8–18 октября, ни одного с оценкой ≥ 5; в v10–v11 — "
            "1 пункт). Замена: сайты площадок (Kettle's Yard, Hot Numbers), Ents24/Skiddle, еженедельный слой Keenable.",
    "S012": "Этап 7e: 0 событий с прогона 30.09 13:25 — на месте списка JS-проверка («перезагрузка через 5 секунд», 7c). За сутки "
            "до этого — не меньше 82 наших запросов (35 — коллектор, 42 — ticket_vendors, статусы, обогащение; 28.09 — прогон на "
            "275 запросов с паузой 2 с). 01.10 00:05 главная /whats-on/ открылась нормально (40 ссылок). Вывод: вероятнее всего из-за "
            "нашей частоты (временный лимит Cloudflare). Пауза 24 ч, дальше — пауза 10 с и страница не чаще раза в сутки.",
    "S131": "Этап 7e: 0 событий с 30.09 13:25 (JS-проверка LiteSpeed). Наших запросов за сутки до — около 20. 01.10 00:06 список "
            "/events-list/ открылся (287 карточек). Вывод: неясно — частота низкая; защита сайта сработала временно. Пауза 24 ч.",
    "S183": "Этап 7e: Sucuri пропускает через раз (30.09 21:46 — заглушка, 22:05 — 7 событий): закрылся сам, не из-за частоты "
            "(2 запроса за прогон). Пауза 24 ч, затем один запрос к главной.",
    "S049": "Этап 7e: robots.txt cus.org закрыл wp-json (30.09) — решение владельца сайта, не обходим. Остаются Varsity (S176) и "
            "termcard на Issuu (S177).",
    "S163": "Этап 7e: HTTP 307 (вероятно, редирект на проверку бот-защиты) с 30.09 21:25; наших запросов за сутки — около 6. "
            "Закрылся сам. Пауза 24 ч.",
    "S126": "Этап 7e: wp-json отвечает не JSON с 30.09 08:37 (за сутки до — около 10 запросов): изменение сайта или защита — "
            "неясно. Пауза 24 ч, затем проверка главной.",
    "S113": "Этап 7e: кроме календаря /whats-on/ — страница собственных событий Visit Ely /visit-ely-events/ (Eel Festival, "
            "Autumn and Orchard Fayre 10–11 октября 2026 — раньше не собиралась).",
    "S008": "Этап 7e: лимит 5 страниц снят (до 20, до первой страницы без новых событий) — база, а не окно выпуска.",
    "S048": "Этап 7e: 3 недели вперёд → все недели календаря (до 26, до трёх пустых подряд).",
    "S105": "Этап 7e: 3 месяца → все месяцы календаря (до 12, до двух пустых подряд).",
    "S168": "Этап 7e: дневник Camdram — 52 недели вперёд (было 12).",
    "S006": "Этап 7e: страница города на Ents24 показывает только ближайший месяц, «Show more» — скриптом; дальний горизонт — "
            "из коллекторов площадок.",
    "S007": "Этап 7e: как у Ents24 — только ближайшие недели на странице города; дальний горизонт — из коллекторов площадок.",
}
NEW = [
    ("S184", "Курсы", "Курсы и мастер-классы для взрослых (21 провайдер, data/course_providers.json)",
     "Провайдеры (HTML, карта сайта + микроразметка)", "https://cambridgecookery.com/", "data/course_providers.json",
     "кулинария (Cambridge Cookery, White Cottage Bakery), керамика, рисование, витраж, вино (WSET), фотография, танцы, "
     "Hills Road, ICE, Botanic Garden; взрослые новички в спорте (walking football)",
     "Видимый текст → Haiku (кэш по тексту); Cambridge Cookery — карта сайта EventON + JSON-LD и микроразметка цены",
     "Еженедельно + перепроверка раз в месяц", "разрешено (закрытые — «Не разобрано»)",
     "Этап 7e: таблица courses (вся доступная программа, архив past/gone); рубрика «Научиться» — без модели. Cambridge, MA "
     "(cambridgeculinary.com и др.) — не наши.", "Центр"),
    ("S185", "Семьи", "Детские секции и клубы (data/kids_providers_extra.json, тип «секция»)", "Клубы (HTML)",
     "https://cambridgerugby.co.uk/mini-youth/", "data/kids_providers_extra.json",
     "футбол, нетбол, регби, хоккей, крикет, плавание, гимнастика, шахматы, танцы, баскетбол, единоборства, лёгкая атлетика",
     "Видимый текст → Haiku (kids_collect: набор, пробное занятие, вид спорта)", "Раз в месяц и к началу триместров",
     "разрешено", "Этап 7e: в базу — все секции; в выпуск («Секции: идёт набор») — только с набором; доджбол в зоне не найден, "
     "FA Full-Time закрыт — не обходим.", "Центр"),
]


def sheet(wb, name: str, header: list[str], rows: list[list], widths: list[int]) -> None:
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name)
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w


def main() -> None:
    shutil.copy(SRC, DST)
    wb = openpyxl.load_workbook(DST)
    ws = wb["Источники"]
    hdr = [c.value for c in ws[1]]
    ci = {h: hdr.index(h) + 1 for h in hdr if h}
    rows = {ws.cell(r, 1).value: r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value}
    for sid, note in NOTES.items():
        if sid not in rows:
            continue
        r = rows[sid]
        ws.cell(r, ci["Заметки"], ((ws.cell(r, ci["Заметки"]).value or "") + " " + note).strip())
        ws.cell(r, ci["Проверено"], T)
    for sid, cat, name, typ, url, endpoint, covers, how, freq, robots, note, zone in NEW:
        if sid in rows:
            continue
        ws.append([None] * len(hdr))
        r = ws.max_row
        for k, v in {"ID": sid, "Категория": cat, "Источник": name, "Тип источника": typ, "URL": url,
                     "Endpoint для сбора": endpoint, "Что покрывает": covers, "Зона": zone, "Способ сбора": how,
                     "Частота": freq, "Приоритет": 2, "URL проверен": "да", "Заметки": note, "robots.txt": robots,
                     "Проверено": T}.items():
            ws.cell(r, ci[k], v)
    con = connect()
    cp = json.loads((ROOT / "data" / "course_providers.json").read_text())
    counts = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT provider_host, count(*), sum(status='active') FROM courses GROUP BY provider_host")}
    sheet(wb, "Курсы", ["Провайдер", "Сайт", "Вид", "Страницы", "Записей в базе", "Активных", "Статус"],
          [[p["name"], p["host"], p["category"], ", ".join(p.get("sitemaps") or p["urls"]),
            counts.get(p["host"], (0, 0))[0], counts.get(p["host"], (0, 0))[1], "подключён"] for p in cp["providers"]]
          + [[n, h, "", u, 0, 0, f"«Не разобрано»: {unparsed.PROBLEM_RU.get(pr, pr)}"] for h, n, u, pr in cp["blocked"]],
          [45, 30, 12, 60, 12, 10, 40])
    ex = json.loads((ROOT / "data" / "kids_providers_extra.json").read_text())["providers"]
    sec = {r[0]: r[1:] for r in con.execute("""SELECT provider_host, count(*), sum(recruiting='open'), sum(trial_free)
                                               FROM kids_programmes WHERE kind='regular' AND coalesce(status,'active')='active'
                                               GROUP BY provider_host""")}
    sheet(wb, "Секции", ["Клуб / провайдер", "Сайт", "Вид", "Секций в базе", "Идёт набор", "Пробное бесплатно", "Страницы"],
          [[p["provider"], p["host"], p["type"], *(sec.get(p["host"]) or (0, 0, 0)), ", ".join(p["urls"])]
           for p in ex if "секция" in p["type"] or p["host"] in sec],
          [45, 30, 25, 12, 12, 16, 60])
    load = json.loads((ROOT / "data" / "crawl_load_7e.json").read_text()) if (ROOT / "data" / "crawl_load_7e.json").exists() else {"rows": []}
    sheet(wb, "Нагрузка на сайты", ["Сайт", "Запросов 30.09 (до общего слоя, ≥)", "Прогонов коллектора 30.09",
                                    "По новым правилам, в сутки", "01.10 фактически (сеть)", "01.10 из кэша"],
          [[x["host"], x["before_total"], x["before_runs"], x["plan_per_day"], x["fact_2026_10_01"],
            x["cache_hits_2026_10_01"]] for x in load["rows"]], [38, 18, 14, 16, 16, 12])
    recs = []
    for r in con.execute("SELECT * FROM recurring_events WHERE rec_id NOT LIKE 'H-%' ORDER BY rec_id"):
        stage, _ = recurring.stage_of(con, r)
        recs.append([r["rec_id"], r["name"], "необычная традиция" if "quirky" in (r["tags"] or "") else "",
                     r["expected_month"], stage, r["manual_start"] or r["found_date"], r["manual_end"] or r["found_date_end"],
                     r["status_note"] or "", r["official_url"], r["note"] or ""])
    sheet(wb, "Ежегодные", ["ID", "Событие", "Тег", "Месяц", "Статус", "Начало", "Окончание", "Заметка о статусе",
                            "Официальная страница", "Примечание"], recs, [6, 45, 18, 10, 16, 12, 12, 50, 50, 60])
    if "Не разобрано" in wb.sheetnames:
        del wb["Не разобрано"]
    un = wb.create_sheet("Не разобрано")
    un.append(["ID", "Источник", "URL", "Тип проблемы", "Подробности", "С какой даты", "Что теряем", "Что делать",
               "Последняя проверка", "Статус"])
    for c in un[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
    unparsed.init(con)
    for r in con.execute("SELECT * FROM unparsed_sources ORDER BY status, key"):
        un.append([r["key"], r["name"], r["url"], unparsed.PROBLEM_RU.get(r["problem"], r["problem"]), r["detail"],
                   r["since"], r["losing"], r["action"], (r["last_checked"] or "")[:10],
                   "открыто" if r["status"] == "open" else "решено"])
    for letter, width in zip("ABCDEFGHIJ", (22, 40, 50, 28, 50, 12, 45, 35, 12, 10)):
        un.column_dimensions[letter].width = width
    help_ws = wb["Как пользоваться"]
    help_ws.append([f"v0.12 ({T}): этап 7e — база знаний (организации, курсы, места с постоянной информацией), бережный "
                    "сбор (лист «Нагрузка на сайты»), курсы для взрослых (S184, лист «Курсы»), детские секции (S185, лист "
                    "«Секции»), ежегодные события и необычные традиции (лист «Ежегодные»)."])
    help_ws.cell(help_ws.max_row, 1).font = Font(italic=True)
    wb.save(DST)
    print(DST.relative_to(ROOT))


if __name__ == "__main__":
    main()
