"""Этап 7g: зрительский спорт для рубрики «Спорт → Смотреть» (итоги 7f: «рубрика бедная — добрать источники»).

S186 Cambridge South Hockey Club — iCal всех матчей клуба (/matches/cshc_matches.ics); в выпуск — домашние ([H]) матчи
     первых команд (M1, L1): остальные команды — клубный уровень.
S187 Peterborough Phantoms (NIHL National, хоккей на льду) — таблица матчей сезона на gophantoms.co.uk: домашние матчи
     (Peterborough Phantoms первыми), время face-off, соперник; площадка — Planet Ice Peterborough (адрес и зону уточняет locate_venues).
S188 Cambridge RUFC (National League 1) — домашние матчи на Grantchester Road по странице команды на ultimaterugby.com
     (ссылки «cambridge-rufc-vs-<соперник>-at-grantchester-road-<дата>»); сайт клуба закрыт проверкой браузера — не обходим.

Не подключены: Cambridge City HC (на сайте нет календаря матчей), Wildlife Trust BCN (403 — защита, не обходим).
"""

from __future__ import annotations

import re
from datetime import date, datetime

from ..base import Collector, RawEvent
from ..http import PoliteClient
from ..parsers import ical_events

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


class CambridgeSouthHockey(Collector):
    source_id, name = "S186", "Cambridge South Hockey Club — домашние матчи первых команд"
    feed = "https://cambridgesouthhockeyclub.co.uk/matches/cshc_matches.ics"
    TEAMS = {"M1": "Men's 1st XI", "L1": "Ladies' 1st XI"}

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        out = []
        today = date.today().isoformat()
        for kw in ical_events(http.get(self.feed).content):
            m = re.match(r"\[H\]\s+(M1|L1)\s+(?:\d+\s*-\s*\d+\s+)?(.+)$", kw["title"])
            if not m or (kw["start"] or "")[:10] < today:
                continue
            opp = re.sub(r"^(?:vs?\.?|v)\s+", "", m.group(2).strip(), flags=re.I)   # «[H] L1 vs Dereham Ladies 1»
            team, opp = self.TEAMS[m.group(1)], re.sub(r"\s+(Mens|Ladies|Men|Women)\s+\d+$", "", opp).strip()
            out.append(self.event(**dict(kw, title=f"Cambridge South HC {team} v {opp}",
                                         categories=["sport", "hockey", "field hockey"],
                                         summary=f"Home league hockey match: Cambridge South {team} v {m.group(2)}")))
        return out


class PeterboroughPhantoms(Collector):
    source_id, name = "S187", "Peterborough Phantoms — домашние матчи (NIHL National)"
    page = "https://gophantoms.co.uk/gameday/2026-27-fixtures"
    ROW_RE = re.compile(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2})\s+([A-Z][a-z]{2})\s*\|?\s*\|?\s*Face-off:\s*(\d{1,2}:\d{2})"
                        r"\s*\|?\s*\|?\s*([A-Za-z /]+?)\s*\|\s*Peterborough Phantoms\s*\|\s*V\s*\|\s*([^|]+?)\s*\|")

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        from ..llmlist import visible_text
        text, _ = visible_text(http.get(self.page).text)
        text = re.sub(r"\s+", " ", text)
        out, today = [], date.today()
        for wd, d, mon, t, comp, opp in self.ROW_RE.findall(text):
            mm = MONTHS[mon.lower()]
            year = 2026 if mm >= 8 else 2027   # сезон 2026–27: сентябрь — апрель
            try:
                day = date(year, mm, int(d))
            except ValueError:
                continue
            if day < today:
                continue
            out.append(self.event(title=f"Peterborough Phantoms v {opp.strip()}", url=self.page,
                                  external_id=f"phantoms-{day.isoformat()}-{opp.strip().lower()}",
                                  start=f"{day.isoformat()}T{int(t.split(':')[0]):02d}:{t.split(':')[1]}",
                                  venue="Planet Ice Peterborough", address="Peterborough", categories=["sport", "ice hockey"],
                                  summary=f"NIHL National ice hockey, {comp.strip()}: Peterborough Phantoms v {opp.strip()}, "
                                          f"face-off {t}"))
        return out


class CambridgeRUFC(Collector):
    source_id, name = "S188", "Cambridge RUFC — домашние матчи (Grantchester Road)"
    page = "https://ultimaterugby.com/cambridge-rufc/fixtures"
    LINK_RE = re.compile(r'href="(/match/cambridge-rufc-vs-([a-z0-9-]+?)-at-grantchester-road-(\d{1,2})(?:st|nd|rd|th)-'
                         r'([a-z]{3})-(\d{4})/\d+[^"]*)"')

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        html = http.get(self.page).text
        out, seen, today = [], set(), date.today()
        for href, opp, d, mon, y in self.LINK_RE.findall(html):
            try:
                day = date(int(y), MONTHS[mon], int(d))
            except (KeyError, ValueError):
                continue
            if day < today or (opp, day) in seen:
                continue
            seen.add((opp, day))
            name = " ".join(w.upper() if w in ("rfc", "rufc", "fc") else w.capitalize() for w in opp.split("-"))
            url = "https://ultimaterugby.com" + href.split("/lineup")[0].split("/commentary")[0]
            out.append(self.event(title=f"Cambridge RUFC v {name}", url=url, external_id=url, start=day.isoformat(),
                                  all_day=True, venue="Cambridge RUFC, Grantchester Road", address="Grantchester Road, Cambridge",
                                  categories=["sport", "rugby"],
                                  summary=f"Home rugby union match (National League 1): Cambridge RUFC v {name}"))
        return out


ALL7G = [CambridgeSouthHockey(), PeterboroughPhantoms(), CambridgeRUFC()]
