"""Этап 6c: перепроверка закрытых источников и провайдеров по новому правилу robots.txt (RFC 9309: 4xx — «правил нет»).

Кого проверяем: источники реестра, закрытые из-за 403 / бот-защиты / robots.txt, непроверенные детские программы
(data/kids_programmes.json → not_verified) и провайдеры из data/kids_providers.json, у которых robots.txt «закрыт».
Одна загрузка страницы честным User-Agent; 403, заглушка или проверка — не обходим, запись в «Не разобрано».

  python scripts/recheck_blocked.py            # → data/recheck_6c.json + таблица unparsed_sources
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402

from collectors.http import PoliteClient  # noqa: E402
from pipeline import domains, unparsed  # noqa: E402
from pipeline.db import connect  # noqa: E402

REGISTRY = ROOT / "data" / "cambridge_event_sources_v0.6.xlsx"
OUT = ROOT / "data" / "recheck_6c.json"
# страница, которую имеет смысл проверять (реестр часто хранит только главную)
PAGES = {
    "S013": "https://www.theportlandarms.co.uk/", "S020": "https://www.cambridgerugbyclub.co.uk/fixtures",
    "S029": "https://www.letsdothis.com/gb/running-events-in-cambridgeshire", "S036": "https://www.cambridgeliteraryfestival.com/",
    "S041": "https://www.cambridgeartstheatre.com/whats-on", "S053": "https://www.iwm.org.uk/events/iwm-duxford",
    "S088": "https://www.parkrun.org.uk/cambridge/", "S089": "https://www.townandgown10k.com/",
    "S101": "https://www.fenland.gov.uk/events", "S103": "https://www.cityofelycouncil.org.uk/", "S104": "https://www.stivestowncouncil.gov.uk/",
    "S106": "https://www.huntingdontown.gov.uk/council_events/", "S112": "https://www.soham-tc.gov.uk/council_events/",
    "S114": "https://www.visitpeterborough.com/whats-on", "S120": "https://peterborough-cathedral.org.uk/whats-on/",
    "S127": "https://www.saffronwalden.gov.uk/", "S100": "https://www.ticketsource.co.uk/hinchingbrooke-country-park",
    "S133": "https://www.nenepark.org.uk/events/", "S135": "https://www.sheprethwildlifepark.co.uk/",
    "S142": "https://churchsuite.com/", "S019": "https://www.cambridgecityfc.com/fixtures/", "S063": "https://ra.co/events/uk/cambridge",
    "S070": "https://www.nationaltrust.org.uk/visit/cambridgeshire/wimpole-estate/events",
}
LOSING = {  # что теряем (для листа «Не разобрано»)
    "S013": "концерты Portland Arms (часть есть на Ents24/Skiddle)", "S020": "домашние матчи Cambridge RUFC",
    "S029": "забеги и триатлоны с регистрацией", "S036": "Cambridge Literary Festival (весна, осень)",
    "S041": "афиша Arts Theatre (есть через Ents24)", "S053": "авиашоу и события IWM Duxford",
    "S088": "спецзабеги parkrun (Рождество, Новый год)", "S089": "дата Town & Gown 10K (найдена поиском)",
    "S114": "события Питерборо из Visit Peterborough", "S120": "концерты собора Питерборо (часть — Ents24/Skiddle)",
    "S133": "события Ferry Meadows / Nene Park", "S135": "события Shepreth Wildlife Park",
    "S142": "календари приходов на ChurchSuite", "S100": "события Hinchingbrooke Country Park (TicketSource)",
    "S070": "сезонные события National Trust (Wimpole, Anglesey Abbey)",
}


def targets() -> list[dict]:
    wb = openpyxl.load_workbook(REGISTRY, read_only=True)
    rows = list(wb["Источники"].iter_rows(values_only=True))
    head = rows[0]
    idx = {k: head.index(k) for k in ("ID", "Источник", "URL", "Заметки")}
    out = []
    for r in rows[1:]:
        sid, note = r[idx["ID"]], str(r[idx["Заметки"]] or "")
        if sid in PAGES:
            out.append({"key": sid, "name": r[idx["Источник"]], "url": PAGES[sid], "kind": "source",
                        "was": note[-160:]})
    kd = json.loads((ROOT / "data" / "kids_programmes.json").read_text())
    for name, url, why in kd["not_verified"]:
        out.append({"key": f"P:{domains.host(url)}", "name": name, "url": url, "kind": "kids", "was": why})
    for p in kd["programmes"]:
        if not p.get("verified"):
            out.append({"key": f"P:{domains.host(p['url'])}", "name": f"{p['provider']} — {p['title']}", "url": p["url"],
                        "kind": "kids", "was": p.get("note", "")[:160]})
    seen = {t["key"] for t in out}
    for p in json.loads((ROOT / "data" / "kids_providers.json").read_text())["providers"]:
        k = f"P:{p['host']}"
        if "закрыт" in p["robots"] and k not in seen:
            out.append({"key": k, "name": p["provider"], "url": p["urls"][0], "kind": "kids", "was": p["robots"]})
            seen.add(k)
    return out


def main() -> None:
    con = connect()
    unparsed.init(con)
    http = PoliteClient()
    res = []
    for t in targets():
        result, detail, text = unparsed.probe(http, t["url"])
        t |= {"result": result, "detail": detail, "text_words": len(text.split())}
        if result == "ok":
            unparsed.resolve(con, t["key"], detail)
        else:
            action = "проверить вручную" if result in ("bot_challenge", "http_403") else "перепроверить позже"
            if t["kind"] == "kids":
                action += "; найти поиском"
            unparsed.record(con, t["key"], t["name"], t["url"], result, detail,
                            LOSING.get(t["key"], "каникулярные программы провайдера" if t["kind"] == "kids" else ""),
                            action)
        con.commit()
        res.append(t)
        print(f"{t['key']:32} {result:15} {detail[:90]}")
    http.close()
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
