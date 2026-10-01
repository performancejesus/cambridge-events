"""Этап 7b: покрытие колледжей.

S168 Camdram — все площадки (не только ADC): общий дневник camdram.net/diary.json?start=…&end=… — Corpus Playroom,
     театры и залы колледжей (Fitzpatrick Hall и Black Box в Queens', Robinson Brickhouse, Pembroke New Cellars,
     Howard Theatre в Downing и др.). Площадки ADC Theatre пропускаем — их с ценами собирает S042. Показы без площадки
     («Not applicable», «Cambridge», даты вместо места) — не события на сцене (фильмы, наборы), пропускаем.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from selectolax.parser import HTMLParser

from ..base import Collector, RawEvent
from ..generic import DetailCache
from ..http import PoliteClient

# адреса колледжей (площадки внутри колледжа — по названию колледжа в названии площадки)
COLLEGE_ADDR = [
    (r"christ'?s", "Christ's College, St Andrew's Street, Cambridge", "CB2 3BU"),
    (r"churchill", "Churchill College, Storey's Way, Cambridge", "CB3 0DS"),
    (r"clare hall", "Clare Hall, Herschel Road, Cambridge", "CB3 9AL"),
    (r"\bclare\b", "Clare College, Trinity Lane, Cambridge", "CB2 1TL"),
    (r"corpus playroom", "Corpus Playroom, St Edward's Passage, Cambridge", "CB2 3PJ"),
    (r"corpus", "Corpus Christi College, Trumpington Street, Cambridge", "CB2 1RH"),
    (r"darwin", "Darwin College, Silver Street, Cambridge", "CB3 9EU"),
    (r"downing|howard (theatre|assembly)", "Downing College, Regent Street, Cambridge", "CB2 1DQ"),
    (r"emmanuel|\bemma\b", "Emmanuel College, St Andrew's Street, Cambridge", "CB2 3AP"),
    (r"fitzwilliam college|\bfitz\b", "Fitzwilliam College, Storey's Way, Cambridge", "CB3 0DG"),
    (r"girton", "Girton College, Huntingdon Road, Cambridge", "CB3 0JG"),
    (r"caius|gonville", "Gonville & Caius College, Trinity Street, Cambridge", "CB2 1TA"),
    (r"homerton", "Homerton College, Hills Road, Cambridge", "CB2 8PH"),
    (r"hughes hall", "Hughes Hall, Wollaston Road, Cambridge", "CB1 2EW"),
    (r"jesus", "Jesus College, Jesus Lane, Cambridge", "CB5 8BL"),
    (r"king'?s college", "King's College, King's Parade, Cambridge", "CB2 1ST"),
    (r"lucy cavendish", "Lucy Cavendish College, Lady Margaret Road, Cambridge", "CB3 0BU"),
    (r"magdalene", "Magdalene College, Magdalene Street, Cambridge", "CB3 0AG"),
    (r"murray edwards|new hall", "Murray Edwards College, Huntingdon Road, Cambridge", "CB3 0DF"),
    (r"newnham", "Newnham College, Sidgwick Avenue, Cambridge", "CB3 9DF"),
    (r"pembroke", "Pembroke College, Trumpington Street, Cambridge", "CB2 1RF"),
    (r"peterhouse", "Peterhouse, Trumpington Street, Cambridge", "CB2 1RD"),
    (r"queens'?|fitzpatrick hall", "Queens' College, Silver Street, Cambridge", "CB3 9ET"),
    (r"robinson", "Robinson College, Grange Road, Cambridge", "CB3 9AN"),
    (r"st\.? catharine'?s|\bcatz\b", "St Catharine's College, Trumpington Street, Cambridge", "CB2 1RL"),
    (r"st\.? edmund'?s", "St Edmund's College, Mount Pleasant, Cambridge", "CB3 0BN"),
    (r"st\.? john'?s", "St John's College, St John's Street, Cambridge", "CB2 1TP"),
    (r"selwyn", "Selwyn College, Grange Road, Cambridge", "CB3 9DQ"),
    (r"sidney sussex", "Sidney Sussex College, Sidney Street, Cambridge", "CB2 3HU"),
    (r"trinity hall", "Trinity Hall, Trinity Lane, Cambridge", "CB2 1TJ"),
    (r"trinity", "Trinity College, Trinity Street, Cambridge", "CB2 1TQ"),
    (r"wolfson", "Wolfson College, Barton Road, Cambridge", "CB3 9BB"),
    (r"arts theatre", "Cambridge Arts Theatre, 6 St Edward's Passage, Cambridge", "CB2 3PJ"),
    (r"mumford", "Mumford Theatre, East Road, Cambridge", "CB1 1PT"),
    (r"west road", "West Road Concert Hall, 11 West Road, Cambridge", "CB3 9DP"),
]
NO_VENUE_RE = re.compile(r"^(not applicable|n/?a|tbc|tba|cambridge|online|various|\w+ (till|to|-) \w+ \d{4})$", re.I)


def college_address(venue: str) -> tuple[str | None, str | None]:
    for rx, addr, pc in COLLEGE_ADDR:
        if re.search(rx, venue, re.I):
            return addr, pc
    return None, None


class CamdramAll(DetailCache, Collector):
    source_id, name = "S168", "Camdram — все площадки (театры колледжей, Corpus Playroom)"
    DIARY = "https://www.camdram.net/diary.json?start={start}&end={end}"
    WEEKS = 52   # этап 7e: база знаний — весь доступный срок (было 12 недель)

    def parse_page(self, page: str, link: str) -> dict | None:
        tree = HTMLParser(page)
        desc = re.sub(r"\s+", " ", (tree.css_first("main") or tree.body).text(separator=" "))[:1200]
        tickets = next((a.attributes.get("href") for a in tree.css("a[href]")
                        if re.search(r"book|ticket", (a.text() or ""), re.I)
                        and (a.attributes.get("href") or "").startswith("http")), None)
        return {"summary": desc, "ticket_url": tickets}

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        self.start_details()
        today = date.today()
        url = self.DIARY.format(start=today.isoformat(), end=(today + timedelta(weeks=self.WEEKS)).isoformat())
        out = []
        self.skipped = {"adc": 0, "no_venue": 0}
        for p in http.get(url).json().get("events", []):
            venue = ((p.get("venue") or {}).get("name") or p.get("other_venue") or "").strip()
            if "adc theatre" in venue.lower():
                self.skipped["adc"] += 1
                continue
            if not venue or NO_VENUE_RE.match(venue):
                self.skipped["no_venue"] += 1
                continue
            show = p.get("show") or {}
            link = f"https://www.camdram.net/shows/{show['slug']}" if show.get("slug") else None
            kw = self.detail(http, link) if link else None
            addr, pc = college_address(venue)
            out.append(self.event(
                external_id=f"camdram-performance-{p['id']}", title=show.get("name") or "(без названия)",
                url=link, start=p.get("start_at"), end=p.get("repeat_until"), venue=venue,
                address=addr, postcode=pc, categories=["theatre", "student"],
                summary=" · ".join(x for x in (p.get("date_string"), (kw or {}).get("summary", "")[:600]) if x)))
        return out


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


class NationalGardenScheme(Collector):
    """S067 National Garden Scheme: открытый API приложения findagarden (api.findagarden.ngs.org.uk, robots.txt
    разрешает всё). /api/gardens — сады с открытиями сезона (координаты, даты); /api/gardens/<id> — цена входа и
    предзапись по каждому открытию. Берём сады в Кембриджшире и в пределах 75 км от центра Кембриджа (зону уточнит
    postcode), открытия с датой (тип 1 — открытие, 2 — вечернее, 5 — по предварительной записи); «по договорённости»
    (типы 3, 4 — группы в любой день сезона) и отменённые — нет."""
    source_id, name = "S067", "National Garden Scheme (сады, в т.ч. колледжей)"
    API = "https://api.findagarden.ngs.org.uk/api/gardens"
    CENTRE = (52.2053, 0.1218)
    RADIUS_KM = 75
    TYPES = {1, 2, 5}

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        today = date.today().isoformat()
        out = []
        self.stats = {"gardens_total": 0, "gardens_near": 0, "openings": 0}
        gardens = http.get(self.API).json().get("results", [])
        self.stats["gardens_total"] = len(gardens)
        for g in gardens:
            pos = g.get("position") or {}
            near = g.get("county") == "Cambridgeshire" or (
                pos.get("lat") and _km(*self.CENTRE, pos["lat"], pos["lng"]) <= self.RADIUS_KM)
            opens = [o for o in g.get("openings") or [] if o.get("garden_opening_type_id") in self.TYPES
                     and not o.get("canceled") and (o.get("start_date") or "")[:10] >= today]
            if not near or not opens:
                continue
            self.stats["gardens_near"] += 1
            d = http.get(f"{self.API}/{g['id']}").json()
            d = d.get("data", d)
            url = d.get("canonical") or f"https://findagarden.ngs.org.uk/garden/{g['id']}"
            opens = sorted((o for o in d.get("openings") or [] if o.get("garden_opening_type_id") in self.TYPES
                            and not o.get("canceled") and (o.get("start_date") or "")[:10] >= today),
                           key=lambda o: o["start_date"])
            # подряд идущие дни (Robinson College открыт ежедневно с сентября по декабрь) — одно событие с диапазоном
            runs: list[list[dict]] = []
            for o in opens:
                if runs and (date.fromisoformat(o["start_date"][:10]) - date.fromisoformat(runs[-1][-1]["start_date"][:10])).days <= 1 \
                        and o.get("price_adult") == runs[-1][-1].get("price_adult"):
                    runs[-1].append(o)
                else:
                    runs.append([o])
            for run in runs:
                o = run[0]
                pa, pc = o.get("price_adult"), o.get("price_child")
                price = None
                if pa is not None:
                    child = "" if pc in (None, "") else (", children free" if float(pc) == 0 else f", children £{float(pc):g}")
                    price = f"£{float(pa):g}" + child
                booking = "pre-booking essential" if o.get("prebookingthroughngs") or o.get("prebookingthroughgarden") else ""
                s_ = o["start_date"].replace(" ", "T")
                if len(run) > 1:   # диапазон дат: время у дней разное — без времени
                    s_, e_ = o["start_date"][:10], run[-1]["start_date"][:10]
                else:
                    e_ = (o.get("end_date") or "").replace(" ", "T") or None
                self.stats["openings"] += len(run)
                out.append(self.event(
                    external_id=f"ngs-{g['id']}-{s_}", title=f"{g['name']} — NGS garden opening",
                    url=url, start=s_, end=e_, all_day=len(run) > 1, venue=g["name"],
                    address=", ".join(x for x in (g.get("address_2"), g.get("address_3"), g.get("town")) if x),
                    postcode=g.get("postcode"), lat=pos.get("lat"), lon=pos.get("lng"), price=price,
                    organizer="National Garden Scheme", categories=["garden", "open garden"],
                    summary=" · ".join(x for x in (booking, (d.get("description") or "")[:500]) if x)))
        return out


class LightCinema(Collector):
    """S157 Light Cinema Cambridge: открытый JSON мини-гида (pipeline/cinema.py). Событиями становятся только
    трансляции (event cinema: NT Live, опера, концерты, мюзиклы) и спецпоказы (Q&A, премьеры); обычные фильмы
    идут в cinema_showings для строки «где идёт» в рубрике «В кино»."""
    source_id, name = "S157", "Light Cinema Cambridge — event cinema и спецпоказы (мини-гид JSON)"

    def collect(self, http: PoliteClient) -> list[RawEvent]:
        from pipeline.cinema import LIGHT_VENUE, light_schedule
        out = []
        for f in light_schedule(http):
            if f["kind"] == "film":
                continue
            for d, t in f["dates"]:
                out.append(self.event(
                    external_id=f"light-{f['url'].rsplit('/', 1)[-1]}-{d}", title=f["title"], url=f["url"],
                    start=f"{d}T{t}:00" if t else d, all_day=not t, venue=LIGHT_VENUE[0], address=LIGHT_VENUE[1],
                    postcode=LIGHT_VENUE[2], categories=["film", "event cinema" if f["kind"] == "event_cinema" else "special screening"],
                    summary=" · ".join(x for x in (f.get("cert") and f"cert {f['cert']}", f.get("runtime")) if x)))
        return out


# --- колледжи: страницы публичных событий (аудит 7b, data/college_decisions_7b.json) ---

from ..llmlist import LlmListCollector  # noqa: E402

COLLEGE_HINT = (
    "Public events of {college}, Cambridge: lectures and talks, concerts and recitals, exhibitions, garden or library "
    "openings, festivals. Skip chapel services and evensong, admissions open days and applicant/school outreach, "
    "conferences and room hire, sports fixtures, and events that already took place (skip anything in the past; if a year "
    "is not given and the date has passed this year, it is a past event, not next year's). Student wellbeing, revision "
    "and study-skills sessions, fitness classes, freshers' and formal-hall events are audience=students_staff. "
    "Set competition = '<type>; audience=<a>' where type is one of lecture, "
    "concert, exhibition, garden, library, festival, other and a is: public (open to all, members of the public welcome, "
    "anyone can book), alumni (for alumni / college members / friends of the college only), students_staff (only "
    "students, staff or fellows), unknown (the page does not say). home=false if the event is not held in Cambridge "
    "(London, abroad, online only).")
AUD_RE = re.compile(r"audience=(\w+)")


class CollegeEvents(LlmListCollector):
    """Страница событий колледжа → события через Haiku (кэш по тексту). Выпускникам и только студентам/сотрудникам —
    не берём (правило «Доступ к событию»: купить такой доступ нельзя); «unknown» — как обычно (open)."""
    college = ""
    urls: list[str] = []
    categories = ["college"]

    @property
    def pages(self):
        return [(u, COLLEGE_HINT.format(college=self.college)) for u in self.urls]

    def keep(self, it: dict) -> bool:
        m = AUD_RE.search(it.get("competition") or "")
        # без классификации (модель не заполнила competition) — не берём: у публичного события она есть
        return it.get("home") is not False and bool(m) and m.group(1) not in ("alumni", "students_staff")

    def collect(self, http):
        out = super().collect(http)
        for e in out:
            e.categories = [re.sub(r";\s*audience=\w+", "", c) for c in e.categories]
            e.summary = re.sub(r";\s*audience=\w+", "", e.summary or "") or None
        return out


def _college(sid: str, college: str, urls: list[str]) -> CollegeEvents:
    from .stage7b import college_address
    c = CollegeEvents()
    c.source_id, c.name, c.college, c.urls = sid, f"{college} — публичные события (этап 7b)", college, urls
    c.address, c.postcode = college_address(college)
    c.venue = college
    return c


# Magdalene, Trinity Hall, Emmanuel: на страницах событий только выпускники, первокурсники и ужины (аудит 7b) — не
# подключаем; концерты Emmanuel и Selwyn приходят из cmp.cam.ac.uk (S150). Решения — data/college_decisions_7b.json.
COLLEGE_COLLECTORS = [
    _college("S169", "Churchill College", ["https://www.chu.cam.ac.uk/events/list/",
                                           "https://archives.chu.cam.ac.uk/events/"]),   # Churchill Archives Centre
    _college("S170", "Clare Hall", ["https://www.clarehall.cam.ac.uk/events/"]),
    _college("S171", "Lucy Cavendish College", ["https://www.lucy.cam.ac.uk/events"]),
    _college("S172", "Robinson College", ["https://www.robinson.cam.ac.uk/events"]),
    _college("S173", "St Edmund's College", ["https://www.st-edmunds.cam.ac.uk/the-vhi/vhi-events/"]),
    _college("S174", "Girton College", ["https://www.girton.cam.ac.uk/upcoming-events"]),
    _college("S175", "Hughes Hall", ["https://www.hughes.cam.ac.uk/about/events/"]),
    _college("S166", "Trinity College", ["https://www.trin.cam.ac.uk/events/", "https://www.trin.cam.ac.uk/about/public-lectures/"]),
]
