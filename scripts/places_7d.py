"""Этап 7d: места пунктов 1–4 брифа (музеи, усадьбы, фермы, Кингс-Линн, кинотеатры зоны).

  --probe          закрытые места — одна проверка страницы (robots.txt + одна загрузка честным User-Agent, без обхода
                   защиты) и запись в лист «Не разобрано» (unparsed_sources) с тем, что теряем и что делать;
  --table MODEL    таблица «место → источник → событий в базе на 60 дней вперёд → в выпуске → решение»
                   (MODEL — issues/<выпуск>_model.json) → data/places_7d.json (для отчёта).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import unparsed  # noqa: E402
from pipeline.db import connect  # noqa: E402

# место, группа, источник, как искать события в базе (регулярное выражение по площадке/адресу или источник), решение
PLACES = [
    ("Музеи университета (Zoology, Whipple, Sedgwick, MAA, Polar, Classical Archaeology)", "музеи", "S052",
     r"Museum of Zoology|Whipple|Sedgwick|Archaeology and Anthropology|Polar Museum|Classical Archaeology", None),
    ("Fitzwilliam Museum", "музеи", "S052", r"Fitzwilliam Museum", None),
    ("Kettle's Yard", "музеи", "S052", r"Kettle.?s Yard", None),
    ("Cambridge University Botanic Garden", "музеи", "S052", r"Botanic Garden", None),
    ("Museum of Cambridge", "музеи", "S130", r"Museum of Cambridge", None),
    ("Centre for Computing History", "музеи", "S134", r"Computing History", None),
    ("Cambridge Museum of Technology", "музеи", "S179 (новый)", r"Museum of Technology", None),
    ("Ely Museum", "музеи", "S180 (новый)", r"Ely Museum", None),
    ("Royston Museum", "музеи", "S153", r"Royston Museum", None),
    ("Oliver Cromwell's House (Ely)", "музеи", "—", r"Cromwell'?s House", "P:olivercromwellshouse.co.uk"),
    ("Wimpole Estate и Home Farm (National Trust)", "усадьбы", "S070 (NT, данные страницы)", r"Wimpole", None),
    ("Anglesey Abbey (National Trust)", "усадьбы", "S070 (NT, данные страницы)", r"Anglesey Abbey", None),
    ("Wicken Fen (National Trust)", "усадьбы", "S070 (NT, данные страницы)", r"Wicken Fen", None),
    ("Audley End House and Gardens (English Heritage)", "усадьбы", "S139 (API событий EH)", r"Audley End", None),
    ("Wandlebury (Cambridge PPF)", "усадьбы", "S131", r"Wandlebury", None),
    ("IWM Duxford", "музеи", "S053 → Visit Cambridge (S001)", r"\bDuxford\b", "S053"),
    ("Shepreth Wildlife Park", "фермы", "S135", r"Shepreth", "S135"),
    ("Gog Magog Hills Farm Shop", "фермы", "—", r"Gog Magog", "P:gogmagoghills.com"),
    ("Bury Lane Farm Shop (Melbourn)", "фермы", "S178 (новый)", r"Bury Lane", None),
    ("Lynn Museum", "Кингс-Линн", "—", r"Lynn Museum", "P:museums.norfolk.gov.uk"),
    ("Corn Exchange King's Lynn — театр и концерты", "Кингс-Линн", "S181 (новый) + Ents24/Skiddle kings-lynn",
     r"Corn Exchange.*(?:King'?s Lynn|Lynn)|King'?s Lynn Corn Exchange", None),
    ("True's Yard Fisherfolk Museum", "Кингс-Линн", "—", r"True'?s Yard", "P:truesyard.co.uk"),
    ("Календарь событий города (Visit West Norfolk)", "Кингс-Линн", "S183 (новый) + Ents24 и Skiddle kings-lynn",
     r"King'?s Lynn", "P:visitwestnorfolk.com"),
]
# закрытые места: ключ «Не разобрано» → (название, URL, что теряем, что делать)
BLOCKED = {
    "S135": ("Shepreth Wildlife Park", "https://www.sheprethwildlifepark.co.uk/whats-on/",
             "сезонные события парка (Halloween, Christmas), семейные занятия",
             "перепроверять раз в неделю; события — через Visit Cambridge и газеты, если появятся"),
    "S053": ("IWM Duxford", "https://www.iwm.org.uk/visits/iwm-duxford/whats-on",
             "авиашоу, дни техники, выставки музея (в базе — только то, что публикует Visit Cambridge, S001)",
             "обходного пути нет: сайт IWM отвечает 403 с проверкой бот-защиты; альтернативный путь — Visit Cambridge "
             "(S001) и статьи газет; крупные авиашоу — в recurring_events вручную"),
    "P:gogmagoghills.com": ("Gog Magog Hills Farm Shop", "https://www.gogmagoghills.com/",
                            "сезонные события фермы (тыквы, рождественские ёлки), мастер-классы",
                            "сайт не отвечает через шлюз (обрыв соединения) — перепроверить; события — через газеты"),
    "P:olivercromwellshouse.co.uk": ("Oliver Cromwell's House (Ely)", "https://www.olivercromwellshouse.co.uk/",
                                     "экскурсии и сезонные программы дома Кромвеля (Halloween)",
                                     "сайт за Sucuri (проверка бот-защиты) — не обходим; события — через Visit Cambridge и газеты"),
    "P:museums.norfolk.gov.uk": ("Lynn Museum (Norfolk Museums)", "https://www.museums.norfolk.gov.uk/lynn-museum/whats-on",
                                 "выставки и семейные занятия Lynn Museum",
                                 "сайт Norfolk Museums отвечает 403 с проверкой бот-защиты — не обходим; перепроверять"),
    "P:truesyard.co.uk": ("True's Yard Fisherfolk Museum", "https://www.truesyard.co.uk/events",
                          "события музея рыбаков Кингс-Линна", "сайт за Sucuri — не обходим; перепроверять"),
    "P:visitwestnorfolk.com": ("Visit West Norfolk (календарь Кингс-Линна)", "https://www.visitwestnorfolk.com/experiences/events/",
                               "городские события Кингс-Линна (ярмарки, фестивали)",
                               "сайт за Sucuri — не обходим; город покрывают Ents24 и Skiddle (страницы kings-lynn) и "
                               "Corn Exchange (S181)"),
}
# кинотеатры зоны, которые не подключены (одна проверка главной страницы)
CINEMAS_BLOCKED = [
    ("Babylon Cinema (Ely Maltings)", "Ely", "https://www.elymaltings.co.uk/whats-on/cinema"),
    ("Abbeygate Cinema", "Bury St Edmunds", "https://www.abbeygatecinema.co.uk/"),
    ("Saffron Screen", "Saffron Walden", "https://www.saffronscreen.com/"),
    ("Cineworld Huntingdon", "Huntingdon", "https://www.cineworld.co.uk/cinemas/huntingdon/"),
    ("Cineworld St Neots", "St Neots", "https://www.cineworld.co.uk/cinemas/st-neots/"),
    ("Cineworld Haverhill", "Haverhill", "https://www.cineworld.co.uk/cinemas/haverhill/"),
    ("Cineworld Bury St Edmunds", "Bury St Edmunds", "https://www.cineworld.co.uk/cinemas/bury-st-edmunds/"),
    ("Showcase Peterborough", "Peterborough", "https://www.showcasecinemas.co.uk/cinema-peterborough"),
    ("Odeon Peterborough", "Peterborough", "https://www.odeon.co.uk/cinemas/peterborough/"),
    ("Key Theatre (Peterborough)", "Peterborough", "https://www.keytheatre.co.uk/"),
    ("Kings Cinema Newmarket", "Newmarket", "https://www.kingscinemanewmarket.co.uk/"),
]


def probe_all() -> None:
    from collectors.http import PoliteClient
    con = connect()
    http = PoliteClient()
    out = {}
    try:
        for key, (name, url, losing, action) in BLOCKED.items():
            res, detail, _ = unparsed.probe(http, url)
            res2, detail2, _ = unparsed.probe(http, url)   # защита пропускает через раз (Sucuri, Shepreth) — две попытки
            if res != res2:
                bad = (res2, detail2) if res == "ok" else (res, detail)
                res, detail = bad[0], f"{bad[1]} (нестабильно: одна из двух попыток — «{'ok' if 'ok' in (res, res2) else res2}»)"
            out[key] = (res, detail)
            if res == "ok":
                unparsed.resolve(con, key, detail)
            else:
                unparsed.record(con, key, name, url, res, detail, losing, action)
            print(f"{key:30} {res:15} {detail[:90]}")
        for name, city, url in CINEMAS_BLOCKED:
            res, detail, _ = unparsed.probe(http, url)
            out[f"C:{name}"] = (res, detail)
            if res != "ok":
                unparsed.record(con, f"C:{name}", f"{name} ({city})", url, res, detail,
                                "расписание кинотеатра (только для базы с пометкой city; в кембриджский выпуск — спецпоказы)",
                                "перепроверять раз в неделю; не обходить")
            print(f"C:{name:28} {res:15} {detail[:90]}")
    finally:
        http.close()
    con.commit()
    (ROOT / "data" / "places_7d_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


def table(model_path: Path) -> None:
    con = connect()
    today = date.today()
    horizon = (today + timedelta(days=60)).isoformat()
    final = model_path.with_name(model_path.name.replace("_model.json", "_final.json"))
    model = json.loads((final if final.exists() else model_path).read_text())   # итоговый состав, если есть
    res = (model.get("result_post") or {}).get("result") or model.get("result") or model
    placed = {}
    for sec in res["sections"]:
        for it in sec["items"]:
            for i in it["ids"]:
                placed.setdefault(i, sec["rubric"])
    # кандидат → события: E<id>, A<id>, T-p<id> — по номеру события
    placed_ev = {}
    for cid, rub in placed.items():
        m = re.match(r"[EAT](?:-p)?(\d+)$", cid)
        if m:
            placed_ev[int(m.group(1))] = rub
    blocked = {r[0]: r for r in con.execute("SELECT key, problem, detail FROM unparsed_sources WHERE status='open'")}
    rows = []
    for name, group, src, rx, bkey in PLACES:
        rxc = re.compile(rx, re.I)
        evs = [e for e in con.execute("""SELECT event_id, title, venue_name, address, date_start, status, zone FROM events
                WHERE coalesce(date_end, date_start) >= ? AND date_start <= ?
                AND status NOT IN ('cancelled','past','disappeared')""", (today.isoformat(), horizon))
               if rxc.search(f"{e[2] or ''} | {e[3] or ''}") or (group == "Кингс-Линн" and rxc.search(e[1] or ""))]
        if group == "Кингс-Линн" and name.startswith("Календарь"):
            evs = [e for e in con.execute("""SELECT event_id, title, venue_name, address, date_start, status, zone FROM events
                    WHERE coalesce(date_end, date_start) >= ? AND date_start <= ?
                    AND status NOT IN ('cancelled','past','disappeared')
                    AND (address LIKE '%Lynn%' OR venue_name LIKE '%Lynn%' OR postcode LIKE 'PE30%' OR postcode LIKE 'PE31%'
                         OR postcode LIKE 'PE34%')""", (today.isoformat(), horizon))]
        in_issue = sorted({placed_ev[e[0]] for e in evs if e[0] in placed_ev})
        n_issue = sum(1 for e in evs if e[0] in placed_ev)
        b = blocked.get(bkey) if bkey else None
        if b and not evs:
            decision = f"«Не разобрано»: {unparsed.PROBLEM_RU.get(b[1], b[1])}"
        elif b:
            decision = f"сайт закрыт ({unparsed.PROBLEM_RU.get(b[1], b[1])}); события — из других источников"
        elif not evs:
            decision = "подключено; событий на 60 дней нет"
        else:
            decision = "подключено"
        zones = sorted({e[6] or "—" for e in evs})
        rows.append({"place": name, "group": group, "source": src, "events_60d": len(evs), "in_issue": n_issue,
                     "rubrics": in_issue, "zones": zones, "decision": decision})
    # кинотеатры зоны: regional_showings (все фильмы, с городом) и события-спецпоказы S182
    cin = []
    from collectors.sources.stage7d import REGIONAL_CINEMAS
    for name, city, url, venue, *_ in REGIONAL_CINEMAS:
        films = con.execute("SELECT count(*), sum(kind!='film') FROM regional_showings WHERE cinema=? AND last_date >= ?",
                            (name, today.isoformat())).fetchone()
        evs = [r[0] for r in con.execute("""SELECT e.event_id FROM events e JOIN event_sources s USING(event_id)
                WHERE s.source_id='S182' AND e.venue_name=? AND coalesce(e.date_end, e.date_start) >= ?
                AND e.date_start <= ?""", (venue, today.isoformat(), horizon))]
        n_issue = sum(1 for e in evs if e in placed_ev)
        cin.append({"place": name, "group": "кино округи", "city": city, "source": "S182 (новый)",
                    "films": films[0] or 0, "special": films[1] or 0, "events_60d": len(evs), "in_issue": n_issue,
                    "decision": "в базе с городом; в выпуск — только спецпоказы и трансляции, которых нет в Кембридже"})
    for name, city, url in CINEMAS_BLOCKED:
        b = blocked.get(f"C:{name}")
        cin.append({"place": name, "group": "кино округи", "city": city, "source": "—", "films": 0, "special": 0,
                    "events_60d": 0, "in_issue": 0,
                    "decision": (f"«Не разобрано»: {unparsed.PROBLEM_RU.get(b[1], b[1])}" if b else
                                 "страница открыта — подключить на этапе 8 (сети: расписание на скриптах)")})
    out = {"built": today.isoformat(), "issue_model": model_path.name, "places": rows, "cinemas": cin}
    (ROOT / "data" / "places_7d.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for r in rows + cin:
        print(f"{r['place'][:48]:48} {r['source'][:28]:28} {r['events_60d']:4} {r['in_issue']:3}  {r['decision'][:70]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--table", type=Path)
    a = ap.parse_args()
    if a.probe:
        probe_all()
    if a.table:
        table(a.table)
