"""S048 University of Cambridge — What's On (admin.cam.ac.uk/whatson): недельные страницы (эта и две следующие),
на каждой — день, время, название и ссылка; площадка, диапазон дат и цена — со страницы события (кэш DetailCache).
Раздел «Families» (category=13) — отдельный запрос, у его событий категория family. iCal/RSS на
webservices.admin.cam.ac.uk закрыты robots.txt — не используем (решение после этапа 1)."""

from __future__ import annotations

import re
from datetime import date, timedelta

from selectolax.parser import HTMLParser

from ..base import Collector
from ..generic import DetailCache
from ..htmlevents import TIME_RE, find_when

BASE = "https://www.admin.cam.ac.uk/whatson/"


def _time(s: str) -> str | None:
    m = TIME_RE.search(s or "")
    if not m:
        return None
    if m.group(3):
        return f"{int(m.group(1)) % 12 + (12 if m.group(3).lower() == 'p' else 0):02d}:{int(m.group(2) or 0):02d}"
    return f"{int(m.group(4)):02d}:{m.group(5)}"


class UniWhatsOn(DetailCache, Collector):
    source_id, name = "S048", "University of Cambridge — What's On"
    refresh_days = 14

    def week(self, http, monday: date, category: str | None = None) -> list[dict]:
        url = f"{BASE}index.shtml?range=week%3B{monday.isoformat()}" + (f"&category={category}" if category else "")
        out, day = [], None
        for tr in HTMLParser(http.get(url).text).css("table.sessions tr"):
            d = tr.css_first("td.date")
            if d:
                txt = d.text(strip=True)
                day = date.today() if txt == "Today" else (find_when(txt) or (None,))[0]
            a = tr.css_first("td.title a")
            if not a or not day:
                continue
            out.append({"uid": a.attributes["href"].split("uid=")[-1], "title": a.text(strip=True), "day": day,
                        "time": _time((tr.css_first("td.time") or tr).text(strip=True)),
                        "summary": (tr.css_first("p.description").text(strip=True) if tr.css_first("p.description") else None)})
        return out

    def parse_page(self, page: str, link: str) -> dict | None:
        tree = HTMLParser(page)
        get = lambda sel: tree.css_first(sel).text(separator=" ", strip=True) if tree.css_first(sel) else None
        cost = get("p.cost")
        return {"venue": get("p.venueName"), "date_range": get("p.dateRange"),
                "price": re.sub(r"^Cost:\s*", "", cost) if cost else None}

    def collect(self, http):
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        # этап 7e: все недели, которые отдаёт календарь (было 3), до трёх пустых подряд, не больше 26
        rows, family, empty = [], set(), 0
        for i in range(26):
            w = monday + timedelta(days=7 * i)
            week = self.week(http, w)
            rows += week
            if week:
                family |= {x["uid"] for x in self.week(http, w, "13")}
            empty = 0 if week else empty + 1
            if empty >= 3:
                break
        self.start_details()
        out, done = [], set()
        for x in rows:
            link = f"{BASE}detail.shtml?uid={x['uid']}"
            det = self.detail(http, link) or {}
            rng = find_when(det.get("date_range") or "") if det.get("date_range") else None
            cats = ["family"] if x["uid"] in family else []
            if rng and rng[1] and (rng[1] - rng[0]).days > 1:     # выставка / длительное событие — одна запись
                if x["uid"] in done:
                    continue
                done.add(x["uid"])
                out.append(self.event(title=x["title"], url=link, external_id=x["uid"], start=rng[0].isoformat(),
                                      end=rng[1].isoformat(), all_day=True, venue=det.get("venue"),
                                      price=det.get("price"), summary=x["summary"], categories=cats))
                continue
            key = (x["uid"], x["day"], x["time"])
            if key in done:
                continue
            done.add(key)
            start = f"{x['day'].isoformat()}T{x['time']}" if x["time"] else x["day"].isoformat()
            out.append(self.event(title=x["title"], url=link, external_id=f"{x['uid']}#{start}", start=start,
                                  all_day=not x["time"], venue=det.get("venue"), price=det.get("price"),
                                  summary=x["summary"], categories=cats))
        return out
