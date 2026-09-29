"""Этап 6c: коллекторы из «Решений после этапа 6b» и зрительский спорт.

S149 King's College Choir (kingscollegechoir.com) — блок «Upcoming Performances» на странице концерта: название |
площадка | дата; время, программа и цена — со страницы концерта (кэш страниц). Концерты хора вне Кембриджа (Wigmore
Hall, Barbican) не берём.
"""

from __future__ import annotations

import re
from datetime import date

from selectolax.parser import HTMLParser

from ..base import Collector
from ..generic import DetailCache
from ..htmlevents import find_when, meta, page_text

FREE_RE = re.compile(r"\b(free of charge|free admission|admission (is )?free|free entry|free event)\b", re.I)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class KingsCollegeChoir(DetailCache, Collector):
    source_id, name = "S149", "King's College Choir — concerts"
    SEED = "https://kingscollegechoir.com/concert/"
    BLOCK_RE = re.compile(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \| \d{1,2} \| ([^|]+?) \| ([^|]+?) \| "
                          r"((?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day \d{1,2} [A-Z][a-z]+ \d{4}) \| View")

    def parse_page(self, page: str, link: str) -> dict | None:
        tree = HTMLParser(page)
        text = page_text(tree.css_first("main") or tree.body)
        h1 = tree.css_first("h1")
        title = h1.text(strip=True) if h1 else meta(tree, "og:title")
        scope = text[text.find(title):] if title and title in text else text
        when = find_when(scope[:600])
        if not when:
            return None
        start, _, t = when
        body = scope[:3000]
        return dict(title=title, start=f"{start.isoformat()}T{t}" if t else start.isoformat(), all_day=not t,
                    price="Free" if FREE_RE.search(body) else None,
                    summary=(meta(tree, "og:description") or "")[:300] + " | " + body[len(title or ""):700])

    def collect(self, http):
        links: dict[str, list[str]] = {}
        for n in range(1, 5):   # список отсортирован по дате публикации — концерты сезона на 1–3 страницах
            try:
                listing = http.get(self.SEED if n == 1 else f"{self.SEED}page/{n}/").text
            except Exception:  # noqa: BLE001 — страницы кончились
                break
            for m in re.finditer(r'href="(https://kingscollegechoir\.com/concert/[a-z0-9-]+/)"[^>]*title="([^"]+)"', listing):
                urls = links.setdefault(m.group(2).strip().replace("&#8217;", "’"), [])
                if m.group(1) not in urls:
                    urls.append(m.group(1))
        first = next(iter(links.values()))[0]
        text = page_text(HTMLParser(http.get(first).text).body)
        self.start_details()
        out = []
        for title, venue, when_s in self.BLOCK_RE.findall(text):
            title, venue = title.strip(), venue.strip()
            if "king's college" not in venue.lower() and "king’s college" not in venue.lower():
                continue   # концерты хора в других городах
            when = find_when(when_s)
            if not when or when[0] < date.today():
                continue
            cands = links.get(title) or next((u for t, u in links.items() if _slug(t)[:30] == _slug(title)[:30]), [])
            # у одинаковых названий (органист играет дважды) — страница с той же датой
            link, kw = next(((u, k) for u in cands if (k := self.detail(http, u)) and k["start"][:10] == when[0].isoformat()),
                            (cands[0] if cands else None, None))
            start = kw["start"] if kw else when[0].isoformat()
            out.append(self.event(title=title, url=link or self.SEED, external_id=f"{_slug(title)}#{when[0]}",
                                  start=start, all_day="T" not in start, venue="King's College Chapel",
                                  address="King's Parade, Cambridge", postcode="CB2 1ST",
                                  price=(kw or {}).get("price"), summary=(kw or {}).get("summary"),
                                  categories=["church_music" if "organ" in title.lower() else "concert"]))
        return out


# --- S150 Cambridge University Music / CMP (cmp.cam.ac.uk): WordPress REST → страницы событий «When: … Where: …» ---

WHEN_RE = re.compile(r"When: \| ([^|]+?) \| Where: \| ([^|]+?) \|")


class CmpConcerts(DetailCache, Collector):
    source_id, name = "S150", "Cambridge Music (cmp.cam.ac.uk) — West Road, CUMS, college concerts"
    API = "https://www.cmp.cam.ac.uk/wp-json/wp/v2/events?per_page=100&orderby=date&order=desc"
    MEMBERS_RE = re.compile(r"fresher|squash|taster|audition|open rehearsal|come and sing|workshop for members|"
                            r"recruit|welcome drinks|socials?\b", re.I)

    def parse_page(self, page: str, link: str) -> dict | None:
        tree = HTMLParser(page)
        text = page_text(tree.css_first("main") or tree.body)
        m = WHEN_RE.search(text)
        if not m:
            return None
        when = find_when(m.group(1))
        if not when:
            return None
        start, end, t = when
        h1 = tree.css_first("h1")
        title = (h1.text(strip=True) if h1 else meta(tree, "og:title")) or ""
        body = text[m.end():m.end() + 900]
        price = re.search(r"£\s?\d+(?:\.\d{2})?(?:\s*[-–]\s*£?\s?\d+(?:\.\d{2})?)?", body)
        return dict(title=title, start=f"{start.isoformat()}T{t}" if t else start.isoformat(),
                    end=end.isoformat() if end else None, all_day=not t, venue=m.group(2).strip(),
                    address="Cambridge" if "," not in m.group(2) else None,
                    price="Free" if FREE_RE.search(body) else (price.group(0) if price else None), summary=body[:600])

    def collect(self, http):
        items = http.get(self.API).json()
        self.start_details()
        out = []
        for it in items:
            if self.MEMBERS_RE.search(it["title"]["rendered"]):
                continue   # набор в студенческие коллективы — не концерт для публики
            kw = self.detail(http, it["link"])
            if not kw or (kw.get("end") or kw["start"])[:10] < date.today().isoformat():
                continue
            cats = [c.replace("event_categories-", "") for c in it.get("class_list", []) if c.startswith("event_categories-")]
            out.append(self.event(**dict(kw, url=it["link"], external_id=it["link"], categories=cats or ["concert"])))
        return out


# --- S151 Music Live Cambridge (musiclivecambridge.com): список концертов → iCal каждого концерта ---

class MusicLiveCambridge(DetailCache, Collector):
    source_id, name = "S151", "Music Live Cambridge — концерты и открытые микрофоны в пабах"
    HOME = "https://musiclivecambridge.com/"

    def parse_page(self, page: str, link: str) -> dict | None:
        from icalendar import Calendar
        try:
            ev = next(c for c in Calendar.from_ical(page).walk("VEVENT"))
        except Exception:  # noqa: BLE001
            return None
        s, e = ev.decoded("DTSTART"), ev.get("DTEND") and ev.decoded("DTEND")
        title = re.sub(r"\s+-\s+\d{2}/\d{2}/\d{4}$", "", str(ev.get("SUMMARY", "")))
        return dict(title=title, start=s.isoformat()[:16], end=e.isoformat()[:16] if e else None, all_day=False,
                    venue=str(ev.get("LOCATION", "")) or None, address="Cambridge",
                    summary=str(ev.get("DESCRIPTION", ""))[:400] or None)

    def collect(self, http):
        home = http.get(self.HOME).text
        gigs = list(dict.fromkeys(re.findall(r'href="(/gigs/[^"/?#]+)"', home)))
        self.start_details()
        out = []
        for g in gigs:
            kw = self.detail(http, f"{self.HOME.rstrip('/')}{g}/calendar")
            if not kw or kw["start"][:10] < date.today().isoformat():
                continue
            out.append(self.event(**dict(kw, url=f"{self.HOME.rstrip('/')}{g}", external_id=g, categories=["concert"])))
        return out


# --- S152 Find a Race (findarace.com): JSON-LD ItemList SportsEvent в радиусе 40 км от Кембриджа ---

class FindARace(Collector):
    """Забеги, трейлы, триатлоны с регистрацией участников (рубрика «Спорт → Поучаствовать»). Виртуальные забеги и
    «в любой день» (период дольше 3 дней) не берём."""
    source_id, name = "S152", "Find a Race — забеги и трейлы (40 км от Кембриджа)"
    URL = "https://findarace.com/events{page}?lat=52.2053&lng=0.1218&radius=40&sports=running"

    def collect(self, http):
        import json as _json
        out, seen = [], set()
        for n in range(1, 6):
            try:
                page = http.get(self.URL.format(page="" if n == 1 else f"/p{n}")).text
            except Exception:  # noqa: BLE001 — страницы кончились (404)
                break
            items = []
            for block in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', page, re.S):
                try:
                    d = _json.loads(block)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("@type") == "ItemList":
                    items += [x["item"] for x in d.get("itemListElement", []) if isinstance(x.get("item"), dict)]
            fresh = [x for x in items if x.get("url") not in seen]
            if not fresh:
                break
            for x in fresh:
                seen.add(x.get("url"))
                s, e = (x.get("startDate") or "")[:10], (x.get("endDate") or x.get("startDate") or "")[:10]
                if not s or e < date.today().isoformat() or (date.fromisoformat(e) - date.fromisoformat(s)).days > 3:
                    continue
                if re.search(r"\bvirtual\b|anytime|any day", x.get("name", ""), re.I):
                    continue
                loc = x.get("location") or {}
                geo = loc.get("geo") or {}
                offers = x.get("offers") or []
                prices = sorted(o.get("price") for o in offers if isinstance(o, dict) and o.get("price") is not None)
                out.append(self.event(title=x["name"], url=x["url"], external_id=x["url"], start=s,
                                      end=e if e != s else None, all_day=True, venue=loc.get("name"),
                                      address=loc.get("address"), lat=geo.get("latitude"), lon=geo.get("longitude"),
                                      price=(f"£{prices[0]:g}" + (f" – £{prices[-1]:g}" if len(prices) > 1 else "")) if prices else None,
                                      summary=(x.get("description") or "")[:400], categories=["sport", "participant"]))
        return out


# --- S105 St Neots Town Council: помесячные страницы council_events → страница события (Date / Location / Time) ---

class StNeotsTownCouncil(DetailCache, Collector):
    source_id, name = "S105", "St Neots Town Council — события (рынки, Bands in the Park, лекции)"
    BASE = "https://www.stneots-tc.gov.uk/council_events/"
    SKIP_RE = re.compile(r"coffee-morning|support-group|poppy-appeal|meeting|surgery", re.I)

    def parse_page(self, page: str, link: str) -> dict | None:
        tree = HTMLParser(page)
        text = page_text(tree.body)
        m = re.search(r"Event Information \| Date \| (\d{2})/(\d{2})/(\d{4})(?: \| Location \| ([^|]+))?(?: \| Time \| (\d{2})(\d{2}))?", text)
        if not m:
            return None
        d, mo, y, loc, hh, mm = m.groups()
        h1 = tree.css_first("h1")
        pc = re.search(r"PE19 ?\d[A-Z]{2}", loc or "")
        return dict(title=h1.text(strip=True) if h1 else "", start=f"{y}-{mo}-{d}" + (f"T{hh}:{mm}" if hh else ""),
                    all_day=not hh, venue=(loc or "St Neots").split(",")[0].strip(), address=(loc or "St Neots").strip(),
                    postcode=pc.group(0) if pc else None, summary=text[m.end():m.end() + 500])

    def collect(self, http):
        links: list[str] = []
        today = date.today()
        for k in range(3):   # текущий и два следующих месяца
            y, mo = today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1
            page = http.get(f"{self.BASE}?event_month={y}-{mo:02d}-01").text
            for u in re.findall(r'href="(https://www\.stneots-tc\.gov\.uk/council_events/[a-z0-9-]+/(?:\?event_date=[\d-]+)?)"', page):
                if u not in links and not self.SKIP_RE.search(u):
                    links.append(u)
        self.start_details()
        out = []
        for u in links:
            kw = self.detail(http, u)
            if not kw or kw["start"][:10] < today.isoformat():
                continue
            out.append(self.event(**dict(kw, url=u, external_id=u)))
        return out


# --- S153 Royston Museum (roystonmuseum.org.uk/what-s-on, Wix): «Название | Wed 30 Sept | £15 | Book Here» ---

class RoystonMuseum(Collector):
    source_id, name = "S153", "Royston Museum — события (концерты, мастер-классы, лекции, детские занятия)"
    URL = "https://www.roystonmuseum.org.uk/what-s-on"
    ITEM_RE = re.compile(r"(?:Multiple Dates \| )?([^|]{4,120}?) \| ((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2,4})"
                         r" \| ([^|]{1,60}?) \| (?:Book Here|Learn more)")

    def collect(self, http):
        tree = HTMLParser(http.get(self.URL).text)
        tree.strip_tags(["script", "style"])
        text = re.sub(r"\s+", " ", (tree.body or tree.root).text(separator=" | "))
        text = text.split("Exciting Events", 1)[-1]
        out = []
        for title, when_s, price in self.ITEM_RE.findall(text):
            when = find_when(when_s)
            if not when or when[0] < date.today():
                continue
            title = title.strip()
            kids = bool(re.search(r"tots|half term|art club|children|family", title, re.I))
            out.append(self.event(title=title, url=self.URL, external_id=f"{_slug(title)}#{when[0]}",
                                  start=when[0].isoformat(), all_day=True, venue="Royston Museum",
                                  address="Lower King Street, Royston", postcode="SG8 5AL", price=price.strip(),
                                  categories=["family"] if kids else []))
        return out


# --- зрительский спорт: календари клубов и лиг через LlmListCollector (текст страницы → Haiku, кэш по хэшу) ---

from ..llmlist import LlmListCollector  # noqa: E402


class CambridgeCityFC(LlmListCollector):
    """S019 Cambridge City FC (Isthmian North, стадион в Sawston): решение этапа 6 «не нужен» отменено (правки после v5) —
    одной строкой в «Спорт → Также играют». Календарь — страница клуба на сайте лиги (Pitchero)."""
    source_id, name = "S019", "Cambridge City FC — домашние матчи (Isthmian League)"
    pages = [("https://www.cambridgecityfc.com/",
              "Upcoming home matches of Cambridge City FC listed as club events ('Cambridge City Vs <opponent>'): title "
              "as 'Cambridge City v <opponent>', home=true, competition if the page names it (FA Cup, league). Ignore "
              "non-match events (bingo, quiz, car boot, parties).")]
    home_only = True
    venue, address, postcode = "FWD-IP Community Stadium", "West Way, Sawston", "CB22 3FG"
    categories = ["sport", "football"]


class CambridgeUnitedWomen(LlmListCollector):
    source_id, name = "S154", "Cambridge United Women — домашние матчи"
    pages = [("https://www.cambridgeunited.com/fixture/list/844",
              "Upcoming fixtures of Cambridge United Women. Title as 'Cambridge United Women v <opponent>' for home "
              "games; home=true for home games; competition as written (league, cup).")]
    home_only = True
    address, categories = "Cambridge", ["sport", "football", "women's football"]


class CambridgeRUFC(Collector):
    """S020 Cambridge RUFC: сайт клуба за бот-защитой. С сезона 2026/27 — National League 1 (выбыли из Champ Rugby);
    сайт лиги публикует весь сезон одним PDF-сеткой: блоки по 5 туров, в строке — по матчу каждого тура.
    Берём домашние матчи Cambridge (время по умолчанию у лиги — 15:00, на странице не указано)."""
    source_id, name = "S020", "Cambridge RUFC — домашние матчи (National League 1, PDF лиги)"
    PDF = "https://nationalleaguerugby.com/wp-content/uploads/2026/06/National-League-Rugby-Fixtures-2026_27-1.pdf"
    PAGE = "https://nationalleaguerugby.com/national-league-rugby-fixtures-2026-27/"
    MATCH_RE = re.compile(r"(\S(?:.*?\S)?)\s+v\s+(\S(?:.*?\S)?)(?=\s{3,}|$)")

    def collect(self, http):
        import io
        from datetime import datetime as _dt
        import pypdf
        pdf = pypdf.PdfReader(io.BytesIO(http.get(self.PDF).content))
        out = []
        for page in pdf.pages:
            text = page.extract_text(extraction_mode="layout")
            if "National One" not in text:
                continue   # в PDF все лиги; Cambridge — National One
            dates: list[str] = []
            for line in text.splitlines():
                ds = re.findall(r"Round \d+\s+(\d{1,2}-[A-Z][a-z]{2}-\d{2})", line)
                if ds:
                    dates = [_dt.strptime(x, "%d-%b-%y").date().isoformat() for x in ds]
                    continue
                for i, (home, away) in enumerate(self.MATCH_RE.findall(line.strip())):
                    if home.strip() == "Cambridge" and i < len(dates) and dates[i] >= date.today().isoformat():
                        out.append(self.event(title=f"Cambridge RUFC v {away.strip()}", url=self.PAGE,
                                              external_id=f"{dates[i]}|{away.strip()}", start=dates[i], all_day=True,
                                              venue="Volac Park, Cambridge RUFC", address="Grantchester Road, Cambridge",
                                              summary=f"National League 1 · v {away.strip()}",
                                              categories=["sport", "rugby", "National League 1"]))
        return out


class PeterboroughPhantoms(LlmListCollector):
    source_id, name = "S155", "Peterborough Phantoms — домашние матчи (хоккей, NIHL)"
    pages = [("https://www.gophantoms.co.uk/gameday/2026-27-fixtures",
              "Upcoming Peterborough Phantoms ice hockey games. Title as 'Peterborough Phantoms v <opponent>' for home "
              "games; home=true for home games (the 'Next Home Games' list and fixtures marked home).")]
    home_only = True
    venue, address, categories = "Planet Ice Peterborough", "Peterborough", ["sport", "ice hockey"]


# --- S045 Arts Picturehouse: страница кинотеатра (без AJAX с токеном сессии): спецпоказы с датой + «Now Playing» ---

class ArtsPicturehouse(LlmListCollector):
    """Правки после v5: рубрика «В кино». Сеансы грузятся внутренним AJAX с XSRF-токеном — не используем. На самой
    странице есть спецпоказы с датой и временем (Q&A, трансляции, финалы сезонов) и список «Now Playing». Фильму из
    «Now Playing» даётся неделя от даты сбора — по first_seen видно, какой фильм новый."""
    source_id, name = "S045", "Arts Picturehouse — спецпоказы и фильмы в прокате"
    pages = [("https://www.picturehouses.com/cinema/arts-picturehouse-cambridge",
              "Films at Arts Picturehouse Cambridge. (1) Special screenings/events with a date (Q&A, live broadcasts, "
              "seasons, festivals): title, date, time. (2) Films listed as 'Now Playing': title, date = null; set "
              "competition='now playing' for them and 'special screening' for dated events. Ignore membership, kids "
              "club promos, food and drink.")]
    venue, address, postcode, categories = "Arts Picturehouse", "38-39 St Andrew's Street, Cambridge", "CB2 3AR", ["film"]

    def collect(self, http):
        from datetime import timedelta
        out = super().collect(http)
        # «Now Playing» без даты: LlmListCollector их отбросил (нет даты) — берём из кэша ответа
        from pipeline.db import connect
        con = connect()
        row = con.execute("SELECT result FROM llm_list_cache WHERE url=?", (self.pages[0][0],)).fetchone()
        con.close()
        today = date.today()
        for it in json_loads(row[0]) if row else []:
            if (it.get("competition") or "").lower() == "now playing":
                out.append(self.event(title=it["title"], url=it.get("url") or self.pages[0][0],
                                      external_id=f"now|{it['title']}", start=today.isoformat(),
                                      end=(today + timedelta(days=6)).isoformat(), all_day=True, venue=self.venue,
                                      address=self.address, postcode=self.postcode, categories=["film", "now playing"],
                                      summary="в прокате"))
        return out


def json_loads(s):
    import json
    return json.loads(s)


# --- колледжи (правки после v5: рубрика «Лекции и встречи»; решения этапа 6 «покрыт» для S143/S144 — неверные) ---

class StJohnsCollege(LlmListCollector):
    source_id, name = "S144", "St John's College — лекции, концерты, выставки, хор"
    pages = [("https://www.joh.cam.ac.uk/festival",
              "Public events at St John's College, Cambridge: lectures, concerts, exhibitions, open days. Skip events "
              "held elsewhere (Oxford, London, livestream only) and routine chapel services (evensong). competition = "
              "event type as the page labels it (Lecture, Music in College, Exhibition)."),
             ("https://www.sjcchoir.co.uk/events/",
              "Public concerts and recitals of the Choir of St John's College, Cambridge. Skip chorister auditions and "
              "'chorister experience' mornings. competition='concert'.")]
    venue, address, postcode = "St John's College", "St John's Street, Cambridge", "CB2 1TP"
    categories = ["college"]

    def keep(self, it):
        v = (it.get("venue") or "").lower()
        return "oxford" not in v and "livestream" not in v and not re.search(
            r"\bKS[2-5]\b|visit day|residential|admissions|chorister experience", it["title"], re.I)


class HeongGallery(LlmListCollector):
    source_id, name = "S163", "Heong Gallery (Downing College) — выставки"
    pages = [("https://www.dow.cam.ac.uk/creative-arts/heong-gallery",
              "Current and upcoming exhibitions at the Heong Gallery: title, date = opening date (or today if already "
              "open), and put the closing date into 'competition' as 'until YYYY-MM-DD'; price as written (Free admission).")]
    venue, address, postcode = "Heong Gallery, Downing College", "Regent Street, Cambridge", "CB2 1DQ"
    categories = ["exhibition", "college"]


class WomensArtCollection(LlmListCollector):
    source_id, name = "S164", "The Women's Art Collection (Murray Edwards College) — выставки и кураторские лекции"
    pages = [("https://www.murrayedwards.cam.ac.uk/womens-art-collection",
              "Exhibitions and talks of The Women's Art Collection at Murray Edwards College. For an exhibition: "
              "date = opening date, competition = 'until YYYY-MM-DD'. For a talk: date, time, competition='talk'.")]
    venue, address, postcode = "The Women's Art Collection, Murray Edwards College", "Huntingdon Road, Cambridge", "CB3 0DF"
    categories = ["college"]
