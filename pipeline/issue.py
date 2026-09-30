"""Этап 4 / 4b: черновик выпуска. Кандидаты из events.db → отбор и тексты через Claude (scripts/build_issue.py) → Markdown.

Факты пункта (даты, время, ссылка) берутся из базы, а не из ответа модели; модель выбирает пункты по id кандидатов
и пишет название, место, цену и описание своими словами на двух языках. Порядок внутри рубрик — по оценке
важности (importance_score); «Главное на выходные» — события с оценкой ≥ 7; «С детьми» и «Бесплатно» — по тегам.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import enrich, evergreen, kids, lineup, school_holidays
from .db import ROOT
from .normalize import norm_title, norm_venue, title_similarity

LISTED_ZONES = {"центр", "до 30 мин", "до часа", "Кембриджшир, дальше часа"}
geo_COUNTY_FAR = "Кембриджшир, дальше часа"
OUT_OF_TOWN = {"до 30 мин", "до часа"}
NO_VENUE_RE = re.compile(r"^\s*(various|multiple locations|location to be announced|tba|tbc|online)\b", re.I)
TBC_RE = re.compile(r"title to be confirmed", re.I)
# Матчи из загруженного целиком календаря сезона — не «новые анонсы» (бриф, этап 4).
SEASON_CALENDAR = {"S018", "S123"}
# Статусы ADC и Cambridge United без данных о продаже: в выпуске — обычные события, не «анонсы».
NO_SALE_DATA = {"S018", "S042", "S123"}
ANNOUNCE_DAYS = 21          # «объявлено недавно»: статья или старт продаж не старше стольких дней
VENUE_NEWS_DAYS = 60        # «Новое в городе» в первом выпуске — открытия за 2 месяца (правки по v3)

# Рубрики после «Темы недели» и «Главного на выходные» (их по одной на каждые выходные периода).
FIXED_RUBRICS = ["weekdays", "cinema", "talks", "colleges", "exhibitions", "free", "kids", "holidays", "sport", "out_of_town",
                 "county", "new_announcements", "tickets", "cancelled", "new_in_town"]
RUBRIC_TITLES = {
    "en": {"theme": "Theme of the week: {theme}", "weekend": "The weekend: {weekend}",
           "weekdays": "Weekdays: concerts, theatre, comedy", "cinema": "At the cinema", "talks": "Talks and meetings",
           "colleges": "At the colleges",
           "exhibitions": "Exhibitions", "free": "Free",
           "kids": "With kids", "holidays": "School holidays: where to book your child", "sport": "Sport",
           "out_of_town": "Out of town (within an hour)", "county": "Around the county",
           "new_announcements": "Just announced", "tickets": "Get your tickets",
           "cancelled": "Cancelled and postponed", "new_in_town": "New in town"},
    "ru": {"theme": "Тема недели: {theme}", "weekend": "Главное на выходные {weekend}",
           "weekdays": "На неделе: концерты, театр, комедия", "cinema": "В кино", "talks": "Лекции и встречи",
           "colleges": "В колледжах",
           "exhibitions": "Выставки", "free": "Бесплатно",
           "kids": "С детьми", "holidays": "Каникулы: куда записать ребёнка", "sport": "Спорт",
           "out_of_town": "За городом (до часа)", "county": "По графству",
           "new_announcements": "Новые анонсы", "tickets": "Успейте купить билеты",
           "cancelled": "Отменено и перенесено", "new_in_town": "Новое в городе"},
}
HEADLINE_MIN = 7.0          # «Тема недели» (опорное событие); на выходных — всегда в «Главном»
_WE = json.loads((ROOT / "data" / "importance_weights.json").read_text())["weekend"]
WEEKEND_MIN = _WE["min_score"]          # «Главное на выходные»: 3–5 лучших событий выходных, но не ниже 4
WEEKEND_MAX = _WE["max_items"]
LONG_BLURB_MIN = 8.0        # развёрнутое описание (2–3 предложения)
ONE_LINE_MAX = 3.0          # одна короткая фраза (правки по v2: описание есть у каждого пункта)
OUT_OF_TOWN_MIN = 4.0       # «За городом» — не ниже 4 (правки по v3; было 3 после v2)
COUNTY_MIN = 5.0            # «По графству» — не ниже 5 (правки по v4; было 4)
MAX_MAIN_ITEMS = 45         # основная часть выпуска (всё, кроме «Каникул») — не больше 40–45 пунктов (правки по v4)
COUNTY_WEEKEND_MIN = 8.0    # «Кембриджшир, дальше часа» и «до часа» в «Главном на выходные» — только от 8 (правки по v3, v5)
BIG_RACE_MIN = 7.0          # крупный забег с участниками — в «Главное» как событие для зрителей (решения после 6b)
TICKETS_SOON_DAYS = (14, 42)  # «Успейте купить»: событие через 2–6 недель с высокой оценкой и небольшим залом
FILM_RE = re.compile(r"\b(film|screening|cinema|documentary|movie|nt live|met opera|royal opera live|ballet live|"
                     r"encore screening)\b", re.I)
TALK_RE = re.compile(r"\b(lecture|talk|talks|in conversation|q ?& ?a|book launch|panel|discussion|symposium|reading|"
                     r"seminar|meet the (author|director))\b", re.I)
PUBLIC_RE = re.compile(r"\b(open to (all|the public|everyone)|all welcome|everyone welcome|free and open|public lecture|"
                       r"members of the public|no booking required)\b", re.I)
# этап 6d (аудит talks.cam): публичные — только эти два списка; Cabinet of Natural History — исследовательский семинар,
# Featured talks — подборка редакции talks.cam (сейчас в ней семинары Cabinet), CamTalks — закрытый от индекса список
PUBLIC_LISTS = {"talks.cam: Major Public Lectures in Cambridge", "talks.cam: Darwin College Lecture Series"}
# узкие научные мероприятия (симпозиумы, конференции, постдок-дни) — не публичные лекции, если нет пометки «open to all»
SPECIALIST_RE = re.compile(r"\b(symposium|conference|colloquium|postdoc|phd|workshop|seminar series|research day|"
                           r"annual meeting|users? meeting|retreat)\b", re.I)
THEATRE_RE = re.compile(r"\b(theatre|play|dance|ballet|musical|opera|panto(mime)?|shakespeare|drama|comedy of|"
                        r"footlights|king lear|hamlet|macbeth)\b", re.I)
# правки по v5: гражданские мероприятия (консультации, выставки проектов застройки) — пока не в выпуск
CIVIC_RE = re.compile(r"\b(public exhibition|public consultation|consultation event|planning (application|proposals?)|"
                      r"council meeting|drop-in (session|event) (on|about) (the )?(plans|proposals|development)|"
                      r"community engagement event)\b", re.I)
URGENCY_RE = re.compile(r"\b(few (tickets|seats|places) (left|remaining)|selling fast|last (few|remaining)|almost sold out|"
                        r"limited (availability|tickets)|early[- ]bird (ends|closes|until)|final tickets)\b", re.I)
PAID_ENTRY_RE = re.compile(r"\b(admission|entry fee|with (a |your )?(garden|museum|park|house) (ticket|admission)|"
                           r"included in|normal entry|standard entry)\b", re.I)
LONG_EXHIBITION_DAYS = 14   # идёт дольше 2 недель — не в «Главное на выходные», а в «Выставки» / «Бесплатно»
# благотворительные распродажи и барахолки — не в «За городом» / «По графству» (правки по v3)
SALE_RE = re.compile(r"\b(sale|jumble|car boot|nearly new|bric-?a-?brac|table top|flea market)\b", re.I)
HOLIDAY_NOTES = {"october_half_term": {"en": "booking now", "ru": "запись идёт сейчас"},
                 "christmas": {"en": "who is already taking bookings", "ru": "кто уже открыл запись"}}
HOLIDAY_TITLES = {"october_half_term": {"en": "October half term", "ru": "Октябрьские каникулы"},
                  "christmas": {"en": "Christmas holidays", "ru": "Рождественские каникулы"}}
WINDOW_DAYS = 10            # период выпуска = дата отправки … +10 дней (правки по v2)
# правки по v4: забеги, триатлоны, челленджи с регистрацией участников — не «Успейте купить билеты», а «Спорт →
# Поучаствовать». Явные виды — по названию; «run/race/challenge/walk» — только если в описании есть регистрация.
PARTICIPATE_RE = re.compile(r"\b(tri|du|aqua)athlon|\bmarathon|\b\d+\s?k\b|\bfun run|\btrail races?\b|\bsportive|"
                            r"\bswimathon|\bpark-?o\b|\borienteering|\bparkrun|\bobstacle (race|course)|\bcharity (run|walk)|"
                            r"\bhalloween run|\brelay\b|\bfestival of running|\brunning festival", re.I)
PARTICIPATE_WEAK_RE = re.compile(r"\b(run|race|challenge|walk|ride|swim)\b", re.I)
NOT_PARTICIPATE_RE = re.compile(r"\b(music|concert|choir|organ|reading|film|comedy|quiz|poetry|book)\b", re.I)   # «Music Marathon»
REGISTER_RE = re.compile(r"\b(regist\w*|entr(y|ies)|participants?|runners|riders|sign up|take part|places? (are )?limited)\b", re.I)
# «С детьми» — только если дети явно названы в данных (решение после этапа 4).
KIDS_RE = re.compile(r"\b(family[- ]friendly|for (all the |the whole )?famil(y|ies)|famil(y|ies) (fun|day|event|show|"
                     r"activit\w*|workshop|ticket)s?|all the family|whole family|kids|children'?s?|toddlers?|babies|"
                     r"baby|half[- ]term|ages? \d|aged \d|years? \d+\s*[-–]\s*\d+|under[- ]?\d+s|"
                     # правки по v5: детские персонажи и книги — явный признак семейного события (The Gruffalo на NVR)
                     r"gruffalo|peppa pig|paw patrol|room on the broom|stick man|hey duggee|bluey|julia donaldson|"
                     r"santa specials?|meet (father christmas|santa))\b", re.I)
WASTE_RE = re.compile(r"\b(e-?waste|recycling|repair caf[eé]|swap shop|bring .n. byte)\b", re.I)
FOR_KIDS_RE = re.compile(r"\b(?:for (?:young )?(?:children|kids|families|toddlers|little ones)|(?:children|kids) (?:aged|will|can)|"
                         r"family (?:fun )?(?:day|event|workshop|show|trail)|and families|suitable for children)\b|"
                         r"\bages? \d+\s*(?:[-–+]|to\b|and\b)", re.I)
# («family friendly» у Visit Cambridge стоит и у джаза в отеле, и у дня переработки техники — для for_kids слабый признак)
# Семейные категории, которыми источник сам размечает события (фильтры UCM «для кого», раздел Visit Cambridge,
# раздел University What's On, Science Centre) — явная пометка, не догадка (этап 6).
FAMILY_CATEGORIES = {"family", "families", "family events", "family friendly", "under 5s", "ages 5+"}
CHAIN_RE = re.compile(r"\b(burger king|mcdonald'?s|kfc|subway|greggs|starbucks|costa|domino'?s|pizza hut|five guys|"
                      r"taco bell|wendy'?s|popeyes|tim hortons|nando'?s|wingstop|jamaica blue|leon)\b", re.I)
MERGES = ROOT / "data" / "manual_merges.json"
# Связанные события, которые в выпуске — один пункт (встреча с режиссёром + показ его фильма); проверено редактором.
LINKS = ROOT / "data" / "issue_links.json"

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
             "ноября", "декабря"]
DAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


@dataclass
class Window:
    issue: date
    start: date
    end: date
    weekends: list[tuple[date, date]] = field(default_factory=list)

    def __post_init__(self):
        # правки по v2: события раньше даты отправки к моменту чтения уже прошли — окно начинается с даты отправки
        self.start = max(self.start, self.issue)
        if not self.weekends:  # все выходные периода (суббота и воскресенье внутри окна)
            x = self.start + timedelta(days=(5 - self.start.weekday()) % 7)
            while x + timedelta(days=1) <= self.end:
                self.weekends.append((x, x + timedelta(days=1)))
                x += timedelta(days=7)

    def rubrics(self) -> list[str]:
        return ["theme"] + [f"weekend_{i + 1}" for i in range(len(self.weekends))] + FIXED_RUBRICS

    def weekend_of(self, rubric: str) -> tuple[date, date] | None:
        return self.weekends[int(rubric.split("_")[1]) - 1] if rubric.startswith("weekend_") else None


@dataclass
class Pools:
    candidates: dict[str, dict] = field(default_factory=dict)   # id → данные для модели и рендера
    excluded: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))  # причина → названия
    duplicates: list[tuple[str, str, str]] = field(default_factory=list)  # (id1, id2, пояснение)
    sold_out: list[str] = field(default_factory=list)
    unverified_news: int = 0
    links: list[tuple[list[str], str]] = field(default_factory=list)  # связанные события → один пункт
    blocked_kids: dict[str, list[str]] = field(default_factory=dict)   # каникулы → закрытые провайдеры («Ещё проверьте»)
    releases: list[dict] = field(default_factory=list)   # решения после 6c: новые фильмы в прокате UK (календарь релизов)
    notes: list[tuple[str, str]] = field(default_factory=list)   # этап 7b: заметки редактору от сборки (en, ru)
    films: list[dict] = field(default_factory=list)      # этап 7b: фильмы окна с кинотеатрами и оценкой (pipeline/cinema)


def d(s: str | None) -> date | None:
    return date.fromisoformat(s[:10]) if s else None


# --- кандидаты ---

def _sources(con, event_id: int) -> list[str]:
    return sorted({r[0] for r in con.execute("SELECT source_id FROM event_sources WHERE event_id=?", (event_id,))})


def _summary(con, event_id: int) -> str:
    """Описания всех источников события (у склеенных дублей — разные: состав концерта может быть только в статье)."""
    rows = con.execute("SELECT summary FROM raw_items WHERE event_id=? AND summary IS NOT NULL", (event_id,)).fetchall()
    uniq = []
    for s in sorted((r["summary"] for r in rows), key=len, reverse=True):
        if not any(s[:80] in u for u in uniq):
            uniq.append(s)
    # правки по v3: лимит 1200 — состав концерта Барретта (Kula Shaker, Soft Machine) был только в третьем описании
    return " | ".join(u[:300] for u in uniq)[:1200]


def _categories(con, event_id: int, limit: int | None = 6) -> list[str]:
    cats = set()
    for (c,) in con.execute("SELECT categories FROM raw_items WHERE event_id=?", (event_id,)):
        cats.update(json.loads(c or "[]"))
    return sorted(cats)[:limit]


def _merge_notes() -> dict[tuple[str, str], str]:
    rules = json.loads(MERGES.read_text()) if MERGES.exists() else []
    return {(r["keep"]["date"], r["keep"]["title"]): r["note"] for r in rules}


def is_family(title: str, summary: str, cats: list[str]) -> bool:
    """Дети или семьи явно названы в данных: слова в названии/описании/категориях или семейная категория источника."""
    return bool(KIDS_RE.search(" ".join([title, summary or ""] + cats))) or any(
        c.strip().lower() in FAMILY_CATEGORIES for c in cats)


def _event_facts(con, e: sqlite3.Row) -> dict:
    srcs = _sources(con, e["event_id"]) or (["recurring"] if e["source_type"] == "recurring" else [])
    status = e["status"]
    if status == "announced" and set(srcs) <= NO_SALE_DATA:
        status = "scheduled (no ticket data)"
    cats = _categories(con, e["event_id"])
    summary = _summary(con, e["event_id"])
    facts = {
        "title": e["title"], "venue": e["venue_name"], "address": e["address"], "postcode": e["postcode"],
        "zone": e["zone"], "address_unknown": bool(e["address_unknown"]), "multi_venue": bool(e["multi_venue"]),
        "price_text": e["price_text"], "price_from": e["price_from"], "status": status, "sources": srcs,
        "categories": cats, "summary": summary, "source_type": e["source_type"],
        "importance": e["importance_score"], "importance_reason": e["importance_reason"],
        "kids_tag": is_family(e["title"], summary, _categories(con, e["event_id"], None)),
        "access": e["access"] or "open", "access_note": e["access_note"],
        # правки по v8: событие действительно для детей — дети в названии, семейная категория источника или описание
        # прямо адресовано детям; распродажи и дни переработки (Bring 'n' Byte, e-waste day) — нет
        "for_kids": (bool(KIDS_RE.search(e["title"])) or bool({x.strip().lower() for x in _categories(con, e["event_id"], None)}
                     & (FAMILY_CATEGORIES - {"family friendly"})) or bool(FOR_KIDS_RE.search(summary or "")))
                    and not SALE_RE.search(e["title"])
                    and not WASTE_RE.search(e["title"]),
        "free_tag": strictly_free(e["price_from"], e["price_text"]),
    }
    allcats = _categories(con, e["event_id"], None)
    text = " ".join([e["title"]] + allcats)
    if FILM_RE.search(text) or "film" in [c.lower() for c in allcats] or set(srcs) & {"S045"}:
        facts["film"] = True
    if TALK_RE.search(e["title"]) or any(c.lower() in ("talk", "lecture", "lectures", "talks") for c in allcats) \
            or (set(srcs) & {"S047"}):
        facts["talk"] = True
        # правки после v5: публичные — из публичных списков talks.cam, других источников или с пометкой «open to all»
        only_talks = set(srcs) <= {"S047"}
        facts["public_talk"] = (not only_talks) or bool(set(allcats) & PUBLIC_LISTS) or bool(PUBLIC_RE.search(summary or ""))
        if SPECIALIST_RE.search(e["title"]) and not PUBLIC_RE.search(summary or ""):
            facts["public_talk"] = False
    if THEATRE_RE.search(text) or set(srcs) & {"S042", "S041"}:
        facts["theatre"] = True
    if con.execute("SELECT name FROM sqlite_master WHERE name='page_status'").fetchone():   # этап 7: сигнал со страницы
        ps = con.execute("SELECT urgency FROM page_status WHERE event_id=? AND result='ok' "
                         "AND urgency IN ('few_left','selling_fast','early_bird_ends')", (e["event_id"],)).fetchone()
        if ps:
            facts["page_urgency"] = ps[0]
    fame = con.execute("SELECT result FROM fame_cache WHERE event_id=?", (e["event_id"],)).fetchone()
    if fame:
        performer = json.loads(fame["result"]).get("performer")
        if performer:
            facts["performer"] = performer   # кто на сцене — имя должно дойти до текста пункта
    names = lineup.names(con, e["event_id"])
    if names:
        facts["lineup"] = names              # правки по v4: все названные участники из всех склеенных записей
    if "participant" in [c.lower() for c in cats] or (PARTICIPATE_RE.search(e["title"]) or (PARTICIPATE_WEAK_RE.search(e["title"]) and (
            REGISTER_RE.search(summary or "") or "sport" in [c.lower() for c in cats]))) \
            and not NOT_PARTICIPATE_RE.search(e["title"]):
        facts["participant"] = True          # регистрация участников, не билеты для зрителей
    page = enrich.facts(con, e["event_id"])
    if page and page.get("text"):
        facts["page_facts"] = page["text"][:700]   # правки по v5: одна загрузка страницы у первоисточника
        if not facts.get("price_text") and page.get("price"):
            facts["page_price"] = page["price"]
    if e["source_type"] != "recurring" and thin(e["title"], (summary or "") + " " + facts.get("page_facts", ""),
                                                facts.get("performer"), names):   # дата ежегодного события — сама факт
        facts["thin_data"] = True            # в данных нет ни одного содержательного факта для описания
    if evergreen.regular_series(con, e["event_id"]):
        facts["regular_series"] = True
    note = _merge_notes().get((e["date_start"], e["title"]))
    if note:
        facts["editor_note"] = note
    return facts


MONTHS_FULL = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
               "november", "december"]
RANGE_RE = re.compile(r"\b(?:\w+day\s+)?(\d{1,2})(?:st|nd|rd|th)?\s*(?:-|–|&|and|to)\s*(?:\w+day\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+"
                      r"(" + "|".join(MONTHS_FULL) + r")\b", re.I)


def page_date_end(start: date, text: str | None) -> date | None:
    """Правки по v8: многодневное событие, у которого источник дал только первый день (Dubai Future Champions Festival —
    «Friday 9 - Saturday 10 October 2026» на странице события) → дата окончания со страницы. Только диапазон, который
    начинается с даты события, в том же месяце, не длиннее 14 дней."""
    for m in RANGE_RE.finditer(text or ""):
        a, b, mon = int(m.group(1)), int(m.group(2)), MONTHS_FULL.index(m.group(3).lower()) + 1
        if a == start.day and mon == start.month and a < b <= a + 14:
            return date(start.year, mon, b)
    return None


NIGHT_RE = re.compile(r"^(2[2-3]|0[0-5]):\d\d$")


def kid_time(p: Pools, facts: dict, t: str | None) -> str | None:
    """Правки по v8: время детского события между 22:00 и 6:00 — подозрительно (Kids Halloween Party в 00:30 — ошибка
    разбора 12:30). Сверка со страницей первоисточника: там есть то же время днём («12:30», «12.30pm») — берём его;
    иначе время не показываем. Заметка — редактору."""
    if not t or not NIGHT_RE.match(t) or not facts.get("kids_tag"):
        return t
    h, m = int(t[:2]), t[3:]
    day_h = h + 12 if h < 6 else h - 12
    page = facts.get("page_facts") or ""
    alt = next((f"{day_h:02d}:{m}" for pat in (rf"\b{day_h}[:.]{m}\b", rf"\b{day_h % 12 or 12}[:.]{m}\s*pm\b")
                if re.search(pat, page, re.I)), None)
    p.notes.append((f"“{facts['title']}”: time {t} looks wrong for a children's event — "
                    + (f"page says {alt}, used it" if alt else "hidden"),
                    f"«{facts['title']}»: время {t} подозрительно для детского события — "
                    + (f"на странице {alt}, взято оно" if alt else "не показываем")))
    return alt


def strictly_free(price_from, price_text: str | None) -> bool:
    """Правки по v5: «бесплатно» — только если максимальная цена тоже £0 и это не «бесплатно при входном билете»."""
    if price_from != 0:
        return False
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", (price_text or "").replace(",", ""))]
    return not any(nums) and not PAID_ENTRY_RE.search(price_text or "")


def thin(title: str, summary: str | None, performer: str | None, names: list[str]) -> bool:
    """Правки по v4: пустые описания запрещены по-настоящему. Мало данных = в описании источников меньше 8 слов
    сверх слов названия и нет ни исполнителя, ни состава."""
    if performer or names:
        return False
    tw = set(re.findall(r"\w+", title.lower()))
    extra = [w for w in re.findall(r"\w+", (summary or "").lower()) if w not in tw and len(w) > 2]
    return len(extra) < 8


def _exclusion(e: sqlite3.Row) -> str | None:
    if TBC_RE.search(e["title"]):
        return "лекции talks.cam с «Title to be confirmed»"
    if e["evergreen"]:
        return "постоянный продукт для туристов (evergreen), не событие"
    if e["roundup"]:
        return "подборка («Things to do…»), не событие — разобрана на отдельные события"
    if CIVIC_RE.search(e["title"]):
        return "гражданское мероприятие (консультация, выставка проекта) — пока не в выпуск"
    # площадки нет, но есть адрес (Visit Cambridge, Visit Ely) — место известно
    if (not e["venue_name"] or NO_VENUE_RE.match(e["venue_name"])) and not e["multi_venue"] and not e["address"]:
        return "нет площадки или адреса"
    if e["zone"] not in LISTED_ZONES:
        return "зона не определена (нет postcode)" if not e["zone"] else "вне зоны"
    if e["status"] in ("cancelled", "postponed", "disappeared", "past"):
        return f"статус {e['status']}"
    if e["access"] == "restricted":   # этап 7b: «Доступ к событию» — купить такой доступ нельзя
        return "только для студентов или сотрудников (доступ restricted)"
    return None


def build_pools(con: sqlite3.Connection, w: Window) -> Pools:
    p = Pools()
    s, e_ = w.start.isoformat(), w.end.isoformat()
    rows = con.execute("""SELECT * FROM events WHERE date_start <= ? AND coalesce(date_end, date_start) >= ?
        ORDER BY date_start, time_start""", (e_, s)).fetchall()
    # серии (спектакль в разные дни, повторяющееся занятие) — один кандидат
    series: dict[tuple, list] = defaultdict(list)
    excluded_rows = []
    for r in rows:
        why = _exclusion(r)
        if why:
            excluded_rows.append(r)
            p.excluded[why].append(f"{r['title']} ({r['date_start']})")
            continue
        if r["status"] == "sold_out":
            p.sold_out.append(f"{r['title']} ({r['date_start']})")
            continue
        series[(norm_title(r["title"]), r["venue_id"] or norm_venue(r["venue_name"]))].append(r)
    for group in series.values():
        first = group[0]
        facts = _event_facts(con, first)
        facts["dates"] = sorted({(g["date_start"], g["date_end"] or g["date_start"], kid_time(p, facts, g["time_start"]))
                                 for g in group}, key=lambda x: tuple(y or "" for y in x))
        facts["event_ids"] = [g["event_id"] for g in group]
        if len(facts["dates"]) == 1 and facts["dates"][0][0] == facts["dates"][0][1]:
            end = page_date_end(d(facts["dates"][0][0]), facts.get("page_facts"))
            if end:   # «пт, 9 октября» + «двухдневное» в описании → «9–10 октября»; время дня тогда не показываем
                facts["dates"] = [(facts["dates"][0][0], end.isoformat(), None)]
        facts["url"] = first["url"]
        facts["kind"] = "event"
        facts["importance"] = max((g["importance_score"] or 0) for g in group) or None
        days = {d(x[0]) + timedelta(days=i) for x in facts["dates"] for i in range((d(x[1]) - d(x[0])).days + 1)}
        days = {x for x in days if w.start <= x <= w.end}
        facts["on_weekends"] = [f"weekend_{i + 1}" for i, (sa, su) in enumerate(w.weekends) if {sa, su} & days]
        facts["on_weekdays"] = any(x.weekday() < 5 for x in days)
        span = (max(d(x[1]) for x in facts["dates"]) - min(d(x[0]) for x in facts["dates"])).days
        if span > LONG_EXHIBITION_DAYS and not facts.get("regular_series"):
            facts["long_running"] = True     # выставка / длительное событие: не в «Главное на выходные»
        if SALE_RE.search(first["title"]):
            facts["sale"] = True             # распродажа / барахолка: не в «За городом» / «По графству»
        p.candidates[f"E{first['event_id']}"] = facts
    _find_duplicates(p, excluded_rows)
    _links(p)
    _announcements(con, w, p)
    _tickets(con, w, p)
    _cancellations(con, w, p)
    _venue_news(con, w, p)
    _drop_repeats(con, w, p)
    _kids_programmes(con, w, p)
    _holiday_family(con, w, p)
    _blocked_kids(con, p)
    from . import film_releases
    p.releases = film_releases.in_window(con, w.start, w.end)
    _films(con, w, p)
    _siblings(con, p)
    return p


SIB_STOP = {"the", "and", "with", "tour", "live", "show", "night", "music", "concert", "comedy", "festival", "party", "club",
            "special", "presents", "featuring", "band", "orchestra", "choir", "quartet", "trio", "cambridge", "event",
            "evening", "tickets", "uk", "2026", "2027", "official", "celebration", "celebrations", "anniversary", "talk",
            "talks", "class", "session", "sessions", "workshop", "lecture", "sunday", "saturday", "friday"}


def _tokens(t: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", (t or "").lower()) if len(x) >= 4 and x not in SIB_STOP}


def _slug(u: str | None) -> str:
    parts = [x for x in (u or "").rstrip("/").split("/") if x and not x.isdigit()]
    return parts[-1].lower() if parts else ""


def _siblings(con, p: Pools) -> None:
    """Этап 7c (правки по v9: The bEAT + The Selecter): все ссылки источников события (all_urls) и несклеенные дубли той
    же даты и площадки (siblings: общее отличительное слово названия или одинаковый адрес страницы) — чтобы ссылка вела
    на первоисточник, а цена бралась из лучшего источника, а не из того, чья ссылка выбрана."""
    rows = {}
    for cid, c in p.candidates.items():
        if not c.get("event_ids"):
            continue
        urls = []
        for e in c["event_ids"]:
            urls += [r[0] for r in con.execute("SELECT url FROM raw_items WHERE event_id=? AND url IS NOT NULL", (e,))]
        c["all_urls"] = list(dict.fromkeys(([c["url"]] if c.get("url") else []) + urls))
        if c["kind"] in ("event", "announcement", "tickets") and c.get("dates"):
            rows[cid] = c
    by: dict[tuple, list] = defaultdict(list)
    for cid, c in rows.items():
        by[(c["dates"][0][0], norm_venue((c.get("venue") or "").replace("’", "'")))].append(cid)
    for (day, venue), ids in by.items():
        if not venue or len(ids) < 2:
            continue
        for a in ids:
            ca = rows[a]
            sib = []
            vt = _tokens(venue) | _tokens(ca.get("venue") or "")
            ta = _tokens(ca["title"]) - vt
            for b in ids:
                cb = rows[b]
                if b == a or set(cb["event_ids"]) & set(ca["event_ids"]):
                    continue
                if set(ca.get("sources") or []) & set(cb.get("sources") or []):
                    continue   # один источник дважды одно событие не публикует: это разные сеансы или события
                t1, t2 = ca["dates"][0][2], cb["dates"][0][2]
                if t1 and t2 and t1 != t2:   # разные сеансы (Studio Sunday в 10:00 и в 13:00) — не дубли
                    continue
                tb = _tokens(cb["title"]) - vt
                common = ta & tb
                same_slug = any(len(_slug(x)) >= 12 and "-" in _slug(x) and _slug(x) == _slug(y) for x in ca["all_urls"] for y in cb["all_urls"])
                if same_slug or (common and len(common) >= 0.5 * min(len(ta), len(tb))) \
                        or title_similarity(norm_title(ca["title"]), norm_title(cb["title"])) >= 0.6:
                    sib.append({"id": b, "event_ids": cb["event_ids"], "title": cb["title"], "urls": cb["all_urls"],
                                "price_text": cb.get("price_text"), "price_from": cb.get("price_from"),
                                "sources": cb.get("sources")})
            if sib:
                ca["siblings"] = sib


def _drop_repeats(con, w: Window, p: Pools) -> None:
    """Правки по v8: уже показанное в прошлых выпусках (история issue_items, pipeline/history.py) не повторяем."""
    from . import history
    seen = history.shown_before(con, w.issue)
    if not seen:
        return
    for cid, c in list(p.candidates.items()):
        k = cid[:1]
        keys = [c.get("news_id")] if k == "V" else c.get("event_ids") or []
        prev = [seen.get(k, {}).get(x) for x in keys]
        if k in "AT":   # анонс уже был как анонс или старт продаж
            prev += [seen.get(o, {}).get(x) for o in "AT" for x in keys]
        prev = [x for x in prev if x]
        if prev:   # C — только если эта же отмена уже была
            p.excluded[f"уже было в выпуске от {max(prev)} (история выпусков)"].append(c["title"])
            del p.candidates[cid]


FILM_CANDIDATES = 8        # этап 7b: лучшие фильмы окна по оценке — кандидаты F… (модель берёт 2–4 полными пунктами)
CINEMA_RU = {"Arts Picturehouse": "Arts Picturehouse", "Light": "The Light"}


def _films(con, w: Window, p: Pools) -> None:
    """Раздел «В кино» (этап 7b): фильмы окна (релизы календаря + премьеры и спецпоказы Light / Picturehouse) с
    кинотеатрами, оценкой и описанием Wikipedia (pipeline/cinema). Нет сети или Wikipedia — рубрика как раньше."""
    from . import cinema
    try:
        p.films = cinema.window_films(con, w.start, w.end)
    except Exception as e:  # noqa: BLE001
        p.notes.append((f"cinema: films were not scored ({type(e).__name__})", f"кино: оценка фильмов не выполнена ({type(e).__name__})"))
        return
    for i, f in enumerate(p.films[:FILM_CANDIDATES]):
        if f["score"] <= 0 and not f["cinemas"]:
            continue
        url = next((r[0] for r in con.execute("SELECT url FROM cinema_showings WHERE norm=? ORDER BY cinema='Light'",
                                               (f["norm"],)) if r[0]), None) or (
            f"https://en.wikipedia.org/wiki/{f['wiki']}" if f.get("wiki") else None)
        p.candidates[f"F{i + 1}"] = {
            "kind": "film_release", "title": f["title"], "film": True, "uk_release": f["uk_date"],
            "rerelease": f["kind"] != "new", "cinemas": f["cinemas"], "wide_release": f["wide"],
            "importance": f["score"], "importance_reason": "; ".join(f["score_reason"]),
            "wiki_description": f.get("wiki_description"), "wiki_extract": f.get("wiki_extract"),
            "dates": [(f["uk_date"], f["uk_date"], None)], "event_ids": [], "url": url, "norm": f["norm"],
            "cinema_url": next((r[0] for r in con.execute("SELECT url FROM cinema_showings WHERE norm=? AND url IS NOT NULL "
                                                           "ORDER BY cinema='Light'", (f["norm"],))), None)}
        # правки по v9: семейный фильм (анимация, family — по описанию Wikipedia) — кандидат и в «С детьми»
        from tests.issue_rules.r32_family_films import is_family_film
        c = p.candidates[f"F{i + 1}"]
        if is_family_film(c):
            c["kids_tag"] = c["for_kids"] = True


def film_where(c: dict, lang: str) -> str:
    """Где идёт — только подтверждённое: кинотеатры из расписаний; широкий релиз без подтверждения — «в широком
    прокате»; иначе пусто."""
    if c.get("cinemas"):
        names = [CINEMA_RU.get(x, x) if lang == "ru" else ("The Light" if x == "Light" else x) for x in c["cinemas"]]
        return (("at " if lang == "en" else "идёт в ") + (" and " if lang == "en" else " и ").join(names)
                + (", Cambridge" if lang == "en" else ", Кембридж"))
    if c.get("wide_release"):
        return "on general release" if lang == "en" else "в широком прокате"
    return ""


RERELEASE_PAREN_RE = re.compile(r"\s*\(([^)]*\b(?:restoration|anniversary|re-?release|4k|director.s cut|remaster\w*)\b[^)]*)\)", re.I)


def rerelease_title(t: str, lang: str) -> str:
    """Правки по v8: «24 Hour Party People (24 Year Anniversary 4K Re-Release)» → «24 Hour Party People
    (4K-реставрация)», «The Others (25th Anniversary)» → «The Others (к 25-летию)», а не «24 года 4K»."""
    def rep(m):
        x = m.group(1).lower()
        years = re.search(r"(\d+)(?:st|nd|rd|th)?[ -]*(?:year )?anniversary", x)
        if re.search(r"4k|restor|remaster", x):
            return " (4K restoration)" if lang == "en" else " (4K-реставрация)"
        if re.search(r"director.s cut", x):
            return " (director's cut)" if lang == "en" else " (режиссёрская версия)"
        if years:
            n = int(years.group(1))
            return f" ({n}th anniversary)" if lang == "en" else f" (к {n}-летию)"
        return " (re-release)" if lang == "en" else " (повторный прокат)"
    return RERELEASE_PAREN_RE.sub(rep, t)


def release_lines(p: Pools, w: Window, lang: str, featured: set[str] | None = None) -> list[dict]:
    """«В прокате с пятницы, 2 октября: …» — одна строка на дату релиза (без привязки к кинотеатру), повторные прокаты —
    в той же строке после «снова на экранах»."""
    # одна строка на группу соседних дат (календари расходятся на день: четверг 8-го или пятница 9-го);
    # отдельная дата через несколько дней (премьера во вторник) — своя строка
    def rdays(r):
        return {d(r["uk_date"])} | ({d(r["note"].split(": ")[1])} if (r.get("note") or "").startswith("mediamole") else set())
    from .cinema import norm as film_norm
    where = {f["norm"]: f["cinemas"] for f in p.films}
    featured = featured or set()
    groups: list[list] = []
    for r in sorted((r for r in p.releases if film_norm(r["title"]) not in featured), key=lambda r: r["uk_date"]):
        if groups and min(rdays(r)) - max(x for g in groups[-1] for x in rdays(g)) <= timedelta(days=1):
            groups[-1].append(r)
        else:
            groups.append([r])
    out = []
    for rs in groups:
        days = sorted({d(r["uk_date"]) for r in rs} | {d(n.split(": ")[1]) for r in rs for n in [r.get("note") or ""]
                                                         if n.startswith("mediamole")})
        # решения после 6d: релизы в Великобритании — по пятницам; календари расходятся — берём пятницу; пятницы нет
        # и дат несколько — «на этой / на следующей неделе»; одна дата не в пятницу (премьера в среду) — как есть
        fridays = [x for x in days if x.weekday() == 4]
        dt = fridays[0] if fridays else days[0]
        if fridays:
            head = f"Out in cinemas from Friday {dt.day} {MONTHS_EN[dt.month - 1]}" if lang == "en" else \
                f"В прокате с пятницы, {_day(dt, lang, weekday=False)}"
        elif len(days) == 1:
            head = f"Out in cinemas from {_day(dt, 'en')}" if lang == "en" else f"В прокате с {_day(dt, lang, weekday=False)}"
        else:
            same_week = dt.isocalendar()[:2] == w.issue.isocalendar()[:2]
            head = ("Out in cinemas this week" if same_week else "Out in cinemas next week") if lang == "en" else \
                ("В прокате на этой неделе" if same_week else "В прокате на следующей неделе")
        def tag(t, shown):   # этап 7b: где идёт — только подтверждённое расписанием кинотеатра
            cs = where.get(film_norm(t)) or []
            return shown + (f" ({', '.join('The Light' if c == 'Light' else c for c in cs)})" if cs else "")
        new = [tag(r["title"], r["title"]) for r in rs if r["kind"] == "new"]
        old = [tag(r["title"], rerelease_title(r["title"], lang)) for r in rs if r["kind"] != "new"]
        meta = ", ".join(new) + (("; back on screen: " if lang == "en" else "; снова на экранах: ") + ", ".join(old)
                                 if old else "")
        out.append({"title": head, "meta": meta, "blurb": "", "url": None, "compact": True, "ids": [], "release": True})
    return out


def _blocked_kids(con, p: Pools) -> None:
    """Решения после 6c: провайдеры за защитой (лист «Не разобрано»), у которых поиск 6b показал программы на эти
    каникулы, — одной строкой «Ещё проверьте» без подробностей."""
    if not con.execute("SELECT name FROM sqlite_master WHERE name='unparsed_sources'").fetchone():
        return
    from .kids_collect import ROOT as KROOT
    blocked = {r[0][2:] for r in con.execute("SELECT key FROM unparsed_sources WHERE key LIKE 'P:%' "
                                             "AND coalesce(status, '') != 'resolved'")}
    have = {r[0] for r in con.execute("SELECT DISTINCT provider_host FROM kids_programmes WHERE source='collector'")}
    for pr in json.loads((KROOT / "data" / "kids_providers.json").read_text())["providers"]:
        if pr["host"] in blocked and pr["host"] not in have:
            for hol in pr.get("holidays") or []:
                p.blocked_kids.setdefault(hol, []).append(pr["provider"].split(" — ")[0])
    # ручной срез 6-v4 искал программы именно на октябрьские каникулы (Cambridge Kids Club, soccer schools и др.)
    from .domains import host as _host
    for name, url, _ in json.loads(kids.DATA.read_text())["not_verified"]:
        if _host(url) in blocked and _host(url) not in have:
            p.blocked_kids.setdefault("october_half_term", []).append(name.split(" — ")[0])


def _kids_programmes(con, w: Window, p: Pools) -> None:
    """«Каникулы: куда записать ребёнка» — программы из kids_programmes (этап 6-v4): ближайшие каникулы в пределах
    8 недель от даты выпуска (октябрьские — запись идёт; рождественские — кто уже открыл запись)."""
    if not con.execute("SELECT name FROM sqlite_master WHERE name='kids_programmes'").fetchone():
        return
    from .kids_collect import text_of
    horizon = (w.issue + timedelta(weeks=13)).isoformat()
    texts = {x["id"]: x.get("text", {}) for x in json.loads(kids.DATA.read_text())["programmes"]}
    for k in con.execute("SELECT * FROM kids_programmes WHERE coalesce(kind, 'holiday') = 'holiday' ORDER BY prog_id").fetchall():
        if k["source"] == "collector":
            texts[k["prog_id"]] = text_of(con, k["prog_id"])
        if k["date_start"] and not (w.issue.isoformat() <= (k["date_end"] or k["date_start"]) and k["date_start"] <= horizon):
            continue
        p.candidates[k["prog_id"]] = {
            "kind": "programme", "title": k["title"], "provider": k["provider"], "holiday": k["holiday"],
            "ages": k["ages"], "hours": k["hours"], "price_text": k["price"], "venue": k["venue"],
            "address": k["address"], "postcode": k["postcode"], "zone": k["zone"], "places": k["places"],
            "booking_opens": k["booking_opens"], "audience": k["audience"], "verified": bool(k["verified"]),
            "note": k["note"], "url": k["url"], "event_ids": [],
            "sources": ["kids_collector"] if k["source"] == "collector" else ["web_search"],
            "booking_deadline": k["booking_deadline"], "collector": k["source"] == "collector",
            "text": texts.get(k["prog_id"], {}),
            "dates": [(k["date_start"], k["date_end"] or k["date_start"], None)] if k["date_start"] else []}


def _links(p: Pools) -> None:
    """data/issue_links.json: группы разных событий, которые подаются одним пунктом. Кандидаты группы получают
    linked (id остальных) и editor_note; scripts/build_issue.py сводит их в один пункт, если модель не свела."""
    rules = json.loads(LINKS.read_text()) if LINKS.exists() else []
    by_key = {}
    for cid, c in p.candidates.items():
        if c["kind"] == "event":
            for x in c["dates"]:
                by_key[(x[0], c["title"])] = cid
    for r in rules:
        ids = [by_key[(e["date"], e["title"])] for e in r["events"] if (e["date"], e["title"]) in by_key]
        if len(ids) < 2:
            continue
        for cid in ids:
            c = p.candidates[cid]
            c["linked"] = [i for i in ids if i != cid]
            c["editor_note"] = " ".join(x for x in (c.get("editor_note"), r["note"]) if x)
        p.links.append((ids, r.get("as", "")))


def _find_duplicates(p: Pools, excluded_rows: list) -> None:
    """Пары событий окна в один день, похожие по названию, на одной площадке (или у одной площадка неизвестна) —
    дубли, которые не склеила дедупликация. Смотрим и исключённые записи: дубль может быть без адреса.
    Модель может объединить кандидатов в один пункт; в «Для редактора» — список."""
    evs = [(cid, c["title"], c["venue"], {x[0] for x in c["dates"]})
           for cid, c in p.candidates.items() if c["kind"] == "event"]
    evs += [(f"#{r['event_id']}", r["title"], r["venue_name"], {r["date_start"]}) for r in excluded_rows]
    for i, (id1, t1, v1, days1) in enumerate(evs):
        for id2, t2, v2, days2 in evs[i + 1:]:
            if not days1 & days2:
                continue
            n1, n2 = norm_title(t1), norm_title(t2)
            sim = title_similarity(n1, n2)
            common = {w for w in set(n1.split()) & set(n2.split()) if len(w) >= 3}
            nv1, nv2 = norm_venue(v1), norm_venue(v2)
            venue_ok = nv1 == nv2 or not nv1 or not nv2 or nv1 in nv2 or nv2 in nv1
            # у исключённой записи вместо площадки бывает команда или организатор из названия другого события
            if id2.startswith("#") and set(nv2.split()) <= set(n1.split()):
                venue_ok = True
            if sim >= 0.85 or (venue_ok and (sim >= 0.6 or len(common) >= 2)):
                p.duplicates.append((id1, id2, f"{t1} / {t2}"))


def _announcements(con, w: Window, p: Pools) -> None:
    """Первый выпуск: заметные события дальше окна, объявленные недавно по данным источников — статья о событии
    или старт продаж за последние ANNOUNCE_DAYS дней, найденная дата ежегодного события."""
    since = (w.issue - timedelta(days=ANNOUNCE_DAYS)).isoformat()
    after = w.end.isoformat()
    seen: set[int] = set()

    def add(e: sqlite3.Row, evidence: str) -> None:
        if e["event_id"] in seen or _exclusion(e):
            return
        facts = _event_facts(con, e)
        if facts["sources"] and set(facts["sources"]) <= SEASON_CALENDAR:
            return
        seen.add(e["event_id"])
        facts |= {"kind": "announcement", "evidence": evidence, "url": e["url"], "event_ids": [e["event_id"]],
                  "dates": [(e["date_start"], e["date_end"] or e["date_start"], e["time_start"])]}
        p.candidates[f"A{e['event_id']}"] = facts

    for e in con.execute("""SELECT DISTINCT e.*, a.published, a.url AS art_url FROM events e
            JOIN event_sources s USING(event_id) JOIN articles a ON a.article_id = s.article_id
            WHERE e.date_start > ? AND a.published >= ? ORDER BY a.published DESC""", (after, since)).fetchall():
        add(e, f"статья {e['published'][:10]}")
    for e in con.execute("""SELECT e.*, u.on_sale_date FROM event_updates u JOIN events e USING(event_id)
            WHERE u.kind='on_sale' AND e.date_start > ? AND u.first_seen_at >= ?""", (after, since)).fetchall():
        add(e, f"старт продаж {e['on_sale_date'] or '?'}")
    for e in con.execute("""SELECT e.*, r.name AS rec_name FROM recurring_events r JOIN events e USING(event_id)
            WHERE e.date_start > ? AND r.found_date IS NOT NULL""", (after,)).fetchall():
        add(e, f"дата ежегодного события ({e['rec_name']})")


def _tickets(con, w: Window, p: Pools) -> None:
    """Старт продаж из статей (недавний или будущий) — если событие не ушло в «новые анонсы», ему место здесь."""
    since = (w.issue - timedelta(days=ANNOUNCE_DAYS)).isoformat()
    for u in con.execute("""SELECT * FROM event_updates WHERE kind='on_sale'
            AND (on_sale_date >= ? OR on_sale_date IS NULL) AND coalesce(date, '9999') >= ?""",
                         (since, w.start.isoformat())).fetchall():
        e = con.execute("SELECT * FROM events WHERE event_id=?", (u["event_id"],)).fetchone() if u["event_id"] else None
        if not e:  # событие из статьи могло не связаться: ищем по дате и названию
            e = next((x for x in con.execute("SELECT * FROM events WHERE date_start=?", (u["date"],))
                      if title_similarity(norm_title(x["title"]), norm_title(u["event_name"])) >= 0.6), None)
        facts = _event_facts(con, e) if e else {"title": u["event_name"], "sources": [u["source_id"]]}
        # ссылка — на событие (первоисточник), а не на статью о старте продаж, если событие есть в базе
        facts |= {"kind": "tickets", "on_sale_date": u["on_sale_date"], "url": (e["url"] if e and e["url"] else u["url"]),
                  "event_ids": [e["event_id"]] if e else [],
                  "dates": [(e["date_start"], e["date_end"] or e["date_start"], e["time_start"])] if e else
                  [(u["date"], u["date"], None)] if u["date"] else []}
        facts["urgency"] = urgency(con, e, facts, w)
        p.candidates[f"T{u['update_id']}"] = facts
    # этап 7: сигналы срочности со страниц событий (перепроверка статусов) — события ближайших 6 недель в продаже
    if not con.execute("SELECT name FROM sqlite_master WHERE name='page_status'").fetchone():
        return
    have = {e for c in p.candidates.values() if c["kind"] == "tickets" for e in c["event_ids"]}
    horizon = (w.issue + timedelta(weeks=6)).isoformat()
    for ps in con.execute("""SELECT ps.*, e.date_start FROM page_status ps JOIN events e USING(event_id)
            WHERE ps.result='ok' AND ps.urgency IN ('few_left','selling_fast','early_bird_ends')
            AND e.status NOT IN ('sold_out','cancelled','postponed','past')
            AND e.date_start >= ? AND e.date_start <= ?""", (w.start.isoformat(), horizon)).fetchall():
        if ps["event_id"] in have:
            continue
        e = con.execute("SELECT * FROM events WHERE event_id=?", (ps["event_id"],)).fetchone()
        if _exclusion(e) or e["zone"] not in LISTED_ZONES:
            continue
        facts = _event_facts(con, e) | {"kind": "tickets", "url": ps["url"] or e["url"], "event_ids": [e["event_id"]],
                                         "dates": [(e["date_start"], e["date_end"] or e["date_start"], e["time_start"])],
                                         "page_signal": ps["evidence"]}
        facts["urgency"] = urgency(con, e, facts, w)
        p.candidates[f"T-p{e['event_id']}"] = facts


def urgency(con, e, facts: dict, w: Window) -> str | None:
    """Правки по v5: «Успейте купить» — только при сигнале срочности: «мало билетов» на странице, заканчивается ранняя
    цена, или событие через 2–6 недель с оценкой ≥ 7 в зале до 1000 мест. Иначе — это анонс («в продаже с …»)."""
    if not e:
        return None
    if e["status"] == "sold_out":
        return None
    ps = con.execute("SELECT urgency, evidence FROM page_status WHERE event_id=? AND result='ok' "
                     "AND urgency IN ('few_left','selling_fast','early_bird_ends')",
                     (e["event_id"],)).fetchone() if con.execute(
        "SELECT name FROM sqlite_master WHERE name='page_status'").fetchone() else None
    if ps:   # этап 7: перепроверка страницы нашла сигнал
        return {"few_left": "на странице: мало билетов", "selling_fast": "на странице: билеты быстро расходятся",
                "early_bird_ends": "на странице: заканчивается ранняя цена",
                "some_dates_sold_out": "на странице: часть дат распродана"}.get(ps["urgency"], ps["urgency"]) + \
            f" («{ps['evidence'][:120]}»)"
    text = " ".join(x for x in (facts.get("summary"), facts.get("page_facts"), e["status"]) if x)
    if URGENCY_RE.search(text):
        return "на странице: мало билетов / ранняя цена заканчивается"
    days = (d(e["date_start"]) - w.issue).days
    cap = con.execute("SELECT capacity FROM venues WHERE venue_id=?", (e["venue_id"],)).fetchone() if e["venue_id"] else None
    if TICKETS_SOON_DAYS[0] <= days <= TICKETS_SOON_DAYS[1] and (e["importance_score"] or 0) >= 7 and cap and cap[0] and cap[0] <= 1000:
        return f"через {days} дн., оценка {e['importance_score']:g}, зал ~{cap[0]}"
    return None


def _holiday_family(con, w: Window, p: Pools) -> None:
    """Правки по v5: семейные события в дни ближайших каникул (в т.ч. за окном выпуска) — подраздел «Каникулы → Куда
    сходить с детьми в каникулы», рядом с лагерями. Любая зона из выпуска (пометка зоны — в строке)."""
    for h in school_holidays.upcoming(w.issue):
        start, end = d(h["start"]) - timedelta(days=2), d(h["end"]) + timedelta(days=2)   # с выходными вокруг
        if (start - w.issue).days > 56:
            continue
        for e in con.execute("""SELECT * FROM events WHERE date_start <= ? AND coalesce(date_end, date_start) >= ?""",
                             (end.isoformat(), start.isoformat())).fetchall():
            if _exclusion(e) or e["status"] == "sold_out":
                continue
            facts = _event_facts(con, e)
            if not facts["kids_tag"] or facts.get("regular_series"):
                continue
            # правки по v8: только события для детей и семей — дети названы в названии или источник сам отнёс событие
            # к семейным, либо описание прямо адресует его детям; распродажи (Bring 'n' Byte Sale) — нет
            if not facts["for_kids"]:
                continue
            span = (d(e["date_end"] or e["date_start"]) - d(e["date_start"])).days
            if span > 21:
                continue   # длительные выставки и сезонные аттракционы — не «сходить в каникулы»
            facts |= {"kind": "holiday_event", "holiday": h["key"], "url": e["url"], "event_ids": [e["event_id"]],
                      "dates": [(e["date_start"], e["date_end"] or e["date_start"], kid_time(p, facts, e["time_start"]))]}
            p.candidates[f"H{e['event_id']}"] = facts


def _cancellations(con, w: Window, p: Pools) -> None:
    # этап 7: «пропало из источника» (disappeared) — не отмена: в «Что не попало» редактору («статус disappeared»),
    # пока перепроверка страницы не подтвердит отмену
    for e in con.execute("""SELECT * FROM events WHERE status IN ('cancelled','postponed')
            AND date_start >= ?""", (w.start.isoformat(),)).fetchall():
        facts = _event_facts(con, e) | {"kind": "cancellation", "url": e["url"], "event_ids": [e["event_id"]],
                                         "dates": [(e["date_start"], e["date_end"] or e["date_start"], e["time_start"])]}
        p.candidates[f"C{e['event_id']}"] = facts
    for u in con.execute("""SELECT * FROM event_updates WHERE kind IN ('cancelled','postponed')
            AND coalesce(date, '9999') >= ?""", (w.start.isoformat(),)).fetchall():
        p.candidates[f"C-u{u['update_id']}"] = {
            "kind": "cancellation", "title": u["event_name"], "status": u["kind"], "new_date": u["new_date"],
            "url": u["url"], "event_ids": [u["event_id"]] if u["event_id"] else [], "sources": [u["source_id"]],
            "dates": [(u["date"], u["date"], None)] if u["date"] else []}


def _venue_news(con, w: Window, p: Pools) -> None:
    since = (w.issue - timedelta(days=VENUE_NEWS_DAYS)).isoformat()
    for v in con.execute("""SELECT v.*, a.published FROM venue_news v LEFT JOIN articles a USING(article_id)
            WHERE coalesce(v.date, substr(a.published,1,10), substr(v.first_seen_at,1,10)) >= ?
               OR v.stage = 'coming_soon'""", (since,)).fetchall():
        if v["source_type"] == "rss_title":
            p.unverified_news += 1
            continue
        if v["source_type"] == "search" and not v["date"]:
            p.excluded["открытие найдено поиском, дата неизвестна"].append(v["name"])
            continue
        # решения после 6b: сетевые фастфуды за пределами Кембриджа в «Новое в городе» не брать
        if CHAIN_RE.search(v["name"]) and not re.search(r"\bCambridge\b", v["address"] or ""):
            p.excluded["сетевой фастфуд за пределами Кембриджа"].append(v["name"])
            continue
        p.candidates[f"V{v['news_id']}"] = {
            "kind": "venue_news", "title": v["name"], "type": v["type"], "stage": v["stage"],
            "address": v["address"], "postcode": v["postcode"], "date": v["date"], "date_basis": v["date_basis"],
            "published": (v["published"] or "")[:10] or None, "note": v["note"], "sources": [v["source_id"]],
            "source_type": v["source_type"], "url": v["url"], "event_ids": [], "dates": [], "news_id": v["news_id"]}
        page = enrich.facts(con, -v["news_id"])   # этап 7c: страница открытия, найденного поиском (enrich_pages)
        if page and page.get("text"):
            p.candidates[f"V{v['news_id']}"]["page_facts"] = page["text"][:700]


ALSO_PLAYING = {"S019", "S154"}   # Cambridge City FC, Cambridge United Women
ZONE_ORDER = ["центр", "до 30 мин", "до часа", geo_COUNTY_FAR]
AGES_RU = [(r"^school age$", "школьники"), (r"^families$", "семьи"), (r"^children, by level$", "дети, по уровню"),
           (r"^primary and secondary$", "начальная и средняя школа"), (r"^Reception – (\d+)$", r"от Reception до \1 лет"),
           (r"^(\d+)\s*(?:[–-]|to)\s*(\d+)(?: years?(?: old)?)?(?: \((.*)\))?$", r"\1–\2 лет"),
           (r"^(?:school )?years? (\d+)\s*(?:[–-]|to)\s*(?:year )?(\d+)$", r"Year \1 – Year \2"),
           (r"^reception(?: class)?\s*(?:[–-]|to)\s*(\d+)(?: years?(?: old)?)?$", r"от Reception до \1 лет"),
           (r"^primary and secondary school children$", "начальная и средняя школа"),
           (r"^(\d+)\+?(?: years?)?\+$", r"от \1 лет"),
           (r"^(\d+)\s*[-–]\s*(\d+)\s*(?:yrs|year-olds|y/?o|years? old)$", r"\1–\2 лет"),
           (r"^older children and teens$", "старшие дети и подростки")]
AUDIENCE = {"eligible": {"en": "for families eligible for free school meals",
                         "ru": "для семей с правом на бесплатное школьное питание"},
            "university": {"en": "only for children of University of Cambridge staff and students",
                           "ru": "только для детей сотрудников и студентов университета"}}


def _date_conflict(c: dict) -> str | None:
    """Даты программы не совпадают с каникулами, к которым она отнесена (больше чем на неделю) — противоречие на
    странице провайдера (например, «October Half Term» с датой 26/11): в выпуск не берём, редактору — с причиной."""
    hols = {}
    for h in school_holidays.load():
        hols.setdefault(h["key"], []).append(h)
    if c.get("holiday") not in hols or not c.get("dates"):
        return None
    a, b = d(c["dates"][0][0]), d(c["dates"][0][1])
    for h in hols[c["holiday"]]:
        if a <= d(h["end"]) + timedelta(days=7) and b >= d(h["start"]) - timedelta(days=7):
            return None
    return f"дата на странице ({c['dates'][0][0]}) не совпадает с каникулами из названия — противоречие у провайдера"


def holiday_selection(p: Pools) -> tuple[list[str], dict[str, str]]:
    """«Каникулы» собираются без модели (правки по v4: одна строка на программу). В выпуск — проверенные на сайте
    провайдера программы в зоне (и университетская — с пометкой); остальные — с причиной (для редакторской версии)."""
    chosen, why = [], {}
    for cid, c in p.candidates.items():
        if c["kind"] != "programme":
            continue
        if not c["verified"] and c["audience"] != "university":
            why[cid] = "не проверено на сайте провайдера"
        elif c["places"] == "full":
            why[cid] = "мест нет"
        elif _date_conflict(c):
            why[cid] = _date_conflict(c)
        elif c["zone"] not in LISTED_ZONES and not (c["zone"] is None and c["audience"] == "eligible"):
            why[cid] = "вне зоны" if c["zone"] else "зона не определена (нет postcode)"
        else:
            chosen.append(cid)
    return chosen, why


def _ages(a: str | None, lang: str) -> str:
    if not a or lang == "en":
        return a or ""
    for pat, rep in AGES_RU:
        if re.match(pat, a.strip(), flags=re.I):
            return re.sub(pat, rep, a.strip(), flags=re.I)
    return a


BOOKING_RU = [(r"^early[- ]", "в начале "), (r"^(?:mid|middle of)[- ]", "в середине "), (r"^late[- ]", "в конце "),
              (r"^end of ", "в конце "), (r"^start of ", "в начале ")]
MONTH_RU_PREP = {m: r for m, r in zip(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                       "October", "November", "December"],
                                      ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
                                       "октября", "ноября", "декабря"])}


def booking_text(bo: str, lang: str) -> str:
    """Дата открытия записи: ISO — как дата; «mid-November» → «в середине ноября» (правки по v5: без английских слов)."""
    if re.match(r"\d{4}-\d\d-\d\d", bo):
        return _day(d(bo), lang, weekday=False)
    if lang == "en":
        return bo
    out = bo
    for pat, rep in BOOKING_RU:
        out = re.sub(pat, rep, out, flags=re.I)
    for en, ru in MONTH_RU_PREP.items():
        out = re.sub(rf"\b{en}\b", ru, out)
    return out


HOLIDAY_TITLES |= {"february_half_term": {"en": "February half term", "ru": "Февральские каникулы"},
                   "easter": {"en": "Easter holidays", "ru": "Пасхальные каникулы"},
                   "may_half_term": {"en": "May half term", "ru": "Майские каникулы"},
                   "summer": {"en": "Summer holidays", "ru": "Летние каникулы"}}
HOLIDAY_NOTES |= {k: {"en": "who is already taking bookings", "ru": "кто уже открыл запись"}
                  for k in ("february_half_term", "easter", "may_half_term", "summer")}
FAMILY_IN_HOLIDAYS_MAX = 6


def booking_closed(c: dict, w: Window) -> bool:
    """Правки по v8: дедлайн записи прошёл к дате выпуска (Strike Academy — «запись до 1 октября» в выпуске 8 октября)."""
    bd = c.get("booking_deadline")
    return bool(bd and re.match(r"\d{4}-\d\d-\d\d$", bd) and d(bd) < w.issue)


def holiday_clip(c: dict, dates: list[tuple], hol: dict | None) -> tuple[list[tuple], str | None]:
    """Правки по v8: даты вне каникул не выдаём за каникулярные — показываем дни каникул (с прилегающими выходными),
    остальное — пометкой («идёт и раньше, с 19 октября»)."""
    if not hol or not dates:
        return dates, None
    hs, he = d(hol["start"]) - timedelta(days=2), d(hol["end"]) + timedelta(days=2)
    a, b = d(min(x[0] for x in dates)), d(max(x[1] for x in dates))
    if b < hs or a > he or (a >= hs and b <= he):
        return dates, None
    na, nb = max(a, d(hol["start"]) if a < hs else a), min(b, d(hol["end"]) if b > he else b)
    note = a if a < hs else None
    return [(na.isoformat(), nb.isoformat())], note.isoformat() if note else None


def _programme_line(x: dict, w: Window, lang: str) -> dict:
    c = x["c"]
    unknown = re.compile(r"^(цены на сайте|prices on the website)$", re.I)
    norm = lambda v: norm_price(re.sub(r"\s+", " ", v or "").strip(), lang)
    pairs = [(re.sub(r"\s+", " ", wh or "").strip(), norm(pr)) for wh, pr in x["where"]]
    pairs = [(("" if wh.lower() == pr.lower() or unknown.match(wh) else wh), pr) for wh, pr in pairs]
    if lang == "ru":
        pairs = [(wh, pr[:1].lower() + pr[1:] if re.match(r"[А-ЯЁ][а-яё]", pr) else pr) for wh, pr in pairs]
    if any(pr and not unknown.match(pr) for _, pr in pairs):   # известная цена есть — «при записи» не повторяем
        pairs = [(wh, "" if unknown.match(pr) else pr) for wh, pr in pairs]
    x = x | {"where": list(dict.fromkeys(pairs))}
    places = list(dict.fromkeys(wh for wh, _ in x["where"] if wh))
    prices = list(dict.fromkeys(pr for _, pr in x["where"] if pr))
    if len(prices) > 1 and len(places) > 1:   # разные цены на разных площадках — цена при каждой площадке
        place, price = "; ".join(f"{wh} ({pr})" if pr else wh for wh, pr in x["where"] if wh), ""
    elif len(prices) > 1:
        place, price = "; ".join(places), "; ".join(prices)
    else:
        place, price = "; ".join(places), (prices[0] if prices else "")
    ages = _ages(c["ages"], lang)
    notes = []
    if c["audience"] in AUDIENCE:
        notes.append(AUDIENCE[c["audience"]][lang])
    if c["places"] == "few_left":
        notes.append("few places left" if lang == "en" else "мест мало")
    if c["places"] == "not_open" and c.get("booking_opens"):
        notes.append(("booking opens " if lang == "en" else "запись открывается: ") + booking_text(c["booking_opens"], lang))
    if booking_closed(c, w):
        notes.append("booking closed" if lang == "en" else "запись закрыта")
    elif c.get("booking_deadline"):
        notes.append(("book by " if lang == "en" else "запись до ") + booking_text(c["booking_deadline"], lang))
    head = f"{x['provider']} — {x['title']}" + (f" ({ages})" if ages else "")
    dates = sorted(x.get("dates") or [])
    hol = nearest_holidays(w).get(c.get("holiday")) if c.get("holiday") else None
    dates, early = holiday_clip(c, dates, hol)
    if early:
        notes.append((f"also runs before the holidays, from {_day(d(early), lang, weekday=False)}" if lang == "en"
                      else f"идёт и раньше, с {_day(d(early), lang, weekday=False)}"))
    if len(dates) > 1:   # одна программа в разные дни (на разных площадках) — одна строка: весь период, «в разные дни»
        c = c | {"dates": [(dates[0][0], max(b for _, b in dates), None)]}
    elif dates:
        c = c | {"dates": [(dates[0][0], dates[0][1], None)]}
    dw = when(c, w, lang) + ((" (different days)" if lang == "en" else " (в разные дни)") if len(dates) > 1 else "")
    if lang == "ru":
        place = re.sub(r"^Multiple locations across ", "несколько площадок: ", place)
        place = re.sub(r",? and ", " и ", place)
    meta = " · ".join(v for v in [dw, place, price] + notes if v)
    return {"title": head, "meta": meta, "blurb": "", "url": c["url"], "compact": True, "ids": x["ids"]}


def _hurry(c: dict, w: Window) -> bool:
    """«Успейте записаться»: мест мало или запись заканчивается в ближайшие 14 дней. Правки по v8: только программы,
    открытые для всех (University Playscheme — только для детей сотрудников и студентов — сюда никогда)."""
    if c.get("audience") not in (None, "", "public"):
        return False
    bd = c.get("booking_deadline")
    soon = bool(bd and re.match(r"\d{4}-\d\d-\d\d", bd) and 0 <= (d(bd) - w.issue).days <= 14)
    return c["places"] == "few_left" or soon


TOWNS_RU_EN = {"Кембридж": "Cambridge", "Эли": "Ely", "Хантингдон": "Huntingdon", "Питерборо": "Peterborough",
               "Бери-Сент-Эдмундс": "Bury St Edmunds", "Саффрон-Уолден": "Saffron Walden", "Сент-Айвс": "St Ives",
               "Сент-Нитс": "St Neots", "Сент-Неотс": "St Neots", "Ньюмаркет": "Newmarket", "Ройстон": "Royston",
               "Уиттлси": "Whittlesey"}


def holiday_groups(p: Pools, w: Window, lang: str) -> list[dict]:
    """Подразделы «Каникул»: «Успейте записаться» (мест мало, скоро дедлайн) → по каникулам, внутри — по зоне
    (Кембридж → до 30 мин → дальше); одинаковые программы одного провайдера на разных площадках — одной строкой;
    в конце — «Куда сходить с детьми в каникулы» (семейные события в дни каникул)."""
    groups = programme_lines(p, w, lang)
    return limited_holiday_groups(p, w, lang, groups)


PROG_TYPES = [("swimming", re.compile(r"\bswim|плаван", re.I)),
              ("science", re.compile(r"\b(science|stem|coding|code|robot|lego|engineer|potions?)|научн", re.I)),
              ("creative", re.compile(r"\b(art|craft|drama|theatre|musical|music|dance|paint|print|illustrat|comic|creative)\b|"
                                      r"театр|танц|мастер-класс|рисов|мюзикл", re.I)),
              ("nature", re.compile(r"\b(forest|bushcraft|outdoors?|nature|farm|riding|horse|pony|park)\b|лесн|природ|"
                                    r"открытом воздухе", re.I)),
              ("sport", re.compile(r"\b(sports?|football|tennis|netball|gym|gymnast\w*|athletics?|multi-?sport|"
                                   r"multi-?activit\w*|climb\w*|kung fu|martial|cricket|rugby|hockey)\b|спорт|теннис|"
                                   r"гимнаст|атлет|нетбол|футбол|мультиактив", re.I))]
HOLIDAY_NEAR_DAYS = 42        # решения после 6c: «ближайшие каникулы» — до них 6 недель и меньше
HOLIDAY_NEAR_MAX, HOLIDAY_NEXT_MAX, HOLIDAY_TYPE_MAX = 12, 5, 2


def prog_type(x: dict) -> str:
    c = x["c"]
    text = " ".join(v for v in (x["title"], c.get("title"), c.get("provider")) if v)
    return next((t for t, rx in PROG_TYPES if rx.search(text)), "other")


def kids_page_name(hol: str, h: dict | None, lang: str) -> str:
    year = (h or {}).get("start", "")[:4]
    return f"kids_{hol}_{year}_{lang}.html"


def programme_lines(p: Pools, w: Window, lang: str) -> dict[str, list[tuple[dict, dict]]]:
    """Все проверенные программы в зоне — строки по каникулам (и «hurry»), без лимитов: [(данные, строка)]."""
    chosen, _ = holiday_selection(p)
    lines: dict[tuple, dict] = {}
    for cid in chosen:
        c = p.candidates[cid]
        t = c.get("text") or {}
        title = t.get(f"title_{lang}") or c["title"]
        title = title[:1].upper() + title[1:]
        key = ("hurry" if _hurry(c, w) else c["holiday"], c["provider"], title)
        x = lines.setdefault(key, {"c": c, "ids": [], "where": [], "zone": 9, "provider": c["provider"], "title": title,
                                   "dates": []})
        x["ids"].append(cid)
        if c["dates"] and tuple(c["dates"][0][:2]) not in x["dates"]:
            x["dates"].append(tuple(c["dates"][0][:2]))
        where, price = t.get(f"where_{lang}") or c["venue"] or "", t.get(f"price_{lang}") or c.get("price_text") or ""
        if lang == "en":   # модель иногда пишет город по-русски и в английской строке
            for ru, en in TOWNS_RU_EN.items():
                where = where.replace(ru, en)
        if (where, price) not in x["where"]:
            x["where"].append((where, price))
        z = ZONE_ORDER.index(c["zone"]) if c["zone"] in ZONE_ORDER else 8
        x["zone"] = min(x["zone"], z)
    groups: dict[str, list] = {}
    for (hol, provider, title), x in sorted(lines.items(), key=lambda kv: (kv[1]["zone"], kv[0][1].lower())):
        groups.setdefault(hol, []).append((x, _programme_line(x, w, lang)))
    return groups


def nearest_holidays(w: Window) -> dict[str, dict]:
    hols = {}
    for h in school_holidays.upcoming(w.issue):   # ближайшие каникулы каждого вида (не следующего учебного года)
        hols.setdefault(h["key"], h)
    return hols


def limited_holiday_groups(p: Pools, w: Window, lang: str, groups: dict) -> list[dict]:
    """Решения после 6c — лимиты «Каникул»: «Успейте записаться» — без лимита; ближайшие каникулы (до них ≤ 6 недель) —
    до 12 строк: сначала Кембридж и «до 30 мин», не больше 2 строк одного типа (спорт, творчество, наука, природа,
    плавание), остальные — строкой «Ещё N программ →» на полный список kids_<каникулы>.html и «Ещё проверьте» для
    закрытых провайдеров; следующие каникулы — до 5 строк, только где запись открыта; «Куда сходить с детьми» — до 6."""
    out = []
    if "hurry" in groups:
        out.append({"title": "Hurry — few places or booking closes soon" if lang == "en" else
                    "Успейте записаться — мест мало или запись скоро закроется", "items": [ln for _, ln in groups["hurry"]]})
    order = ["october_half_term", "christmas", "february_half_term", "easter", "may_half_term", "summer", "both"]
    hols = nearest_holidays(w)
    for hol in [k for k in order if k in groups]:
        h = hols.get(hol) or kids.holidays().get(hol)
        near = bool(h) and (d(h["start"]) - w.issue).days <= HOLIDAY_NEAR_DAYS
        pairs = [(x, ln) for x, ln in groups[hol] if not booking_closed(x["c"], w)]   # правки по v8: запись закрыта —
        # в письмо не берём (на полной странице — с пометкой «запись закрыта»)
        if near:
            first = sorted(pairs, key=lambda xl: (xl[0]["zone"] > 1, xl[0]["zone"]))   # центр и «до 30 мин» — первыми
            sel, per_type = [], {}
            for x, ln in first:
                t = prog_type(x)
                if len(sel) < HOLIDAY_NEAR_MAX and per_type.get(t, 0) < HOLIDAY_TYPE_MAX:
                    sel.append((x, ln))
                    per_type[t] = per_type.get(t, 0) + 1
        else:
            sel = [(x, ln) for x, ln in pairs if x["c"]["places"] in ("open", "few_left")
                   or re.search(r"early", x["c"].get("price_text") or "", re.I)][:HOLIDAY_NEXT_MAX]
        items = [ln for _, ln in sel]
        rest = len(pairs) - len(sel)
        if near and rest > 0:
            items.append({"title": (f"{rest} more programmes for these holidays →" if lang == "en" else
                                    f"Ещё {rest} программ на эти каникулы →"),
                          "meta": "", "blurb": "", "url": kids_page_name(hol, h, lang), "compact": True, "ids": [],
                          "more": True})
        if near and p.blocked_kids.get(hol):
            names = ", ".join(sorted(set(p.blocked_kids[hol])))
            items.append({"title": (f"Also check: {names}" if lang == "en" else f"Ещё проверьте: {names}"),
                          "meta": ("they usually run holiday programmes — details on their websites" if lang == "en" else
                                   "у них обычно есть программы на каникулы, подробности на сайтах"),
                          "blurb": "", "url": None, "compact": True, "ids": [], "more": True})
        if hol in HOLIDAY_TITLES:
            rng = f"{_day(d(h['start']), lang, weekday=False)} – {_day(d(h['end']), lang, weekday=False, year=d(h['end']).year != w.issue.year)}"
            title = f"{HOLIDAY_TITLES[hol][lang]}, {rng} — {HOLIDAY_NOTES[hol][lang]}"
        else:
            title = "Both holidays" if lang == "en" else "На все каникулы"
        if items:
            out.append({"title": title, "items": items})
    fam = sorted((c for c in p.candidates.values() if c["kind"] == "holiday_event"),
                 key=lambda c: -(c.get("importance") or 0))[:FAMILY_IN_HOLIDAYS_MAX]
    if fam:
        items = []
        for c in sorted(fam, key=lambda c: c["dates"][0][0]):
            zone = "" if c.get("zone") == "центр" else (f" ({c['zone']})" if lang == "ru" else
                                                        f" ({ZONE_EN.get(c.get('zone'), c.get('zone'))})")
            price = price_from_data(c)[0 if lang == "en" else 1]
            if price in ("price not listed", "цена не указана"):
                price = "prices on the website" if lang == "en" else "цены на сайте"
            place = c.get("venue") or ", ".join((c.get("address") or "").split(",")[:2]).strip()
            meta = " · ".join(x for x in (when(c, w, lang), re.sub(r"\s+", " ", place + zone).strip(), price) if x)
            from tests.issue_rules.common import tier
            from tests.issue_rules.r11_primary_link import best_url
            b = best_url(c)   # этап 7c: ссылка на первоисточник (Botanic Garden, а не сводная афиша музеев)
            items.append({"title": c["title"], "meta": meta, "blurb": "",
                          "url": b if b and tier(b) < tier(c["url"]) else c["url"], "compact": True,
                          "ids": [cid for cid, x in p.candidates.items() if x is c]})
        out.append({"title": "Where to go with children during the holidays" if lang == "en" else
                    "Куда сходить с детьми в каникулы", "items": items})
    return out


ZONE_EN = {"до 30 мин": "within 30 min", "до часа": "within an hour", "Кембриджшир, дальше часа": "Cambridgeshire, over an hour"}


def model_view(p: Pools) -> list[dict]:
    """Кандидаты для модели: только нужные поля, без пустых. «Каникулы» собираются без модели."""
    out = []
    for cid, c in p.candidates.items():
        if c["kind"] in ("programme", "holiday_event"):
            continue
        item = {"id": cid} | {k: v for k, v in c.items()
                              if k not in ("url", "event_ids", "importance_reason") and v not in (None, "", [], False)}
        if item.get("summary") and (c.get("importance") or 0) < 6:   # экономия: полный состав нужен крупным событиям
            item["summary"] = item["summary"][:400]
        out.append(item)
    return out


UNKNOWN_PRICE_RE = re.compile(r"^(цен[аы]\s*(?:—|-|–)?\s*(?:при|на) (?:записи|бронировании|входе)|цен[аы]? (?:указаны? )?на сайте"
                              r"(?: организатора| площадки)?|цена не указана|price on booking|price not listed|prices? on "
                              r"(?:the )?(?:website|booking|request)|see (?:the )?website)\.?$", re.I)


def norm_price(v: str | None, lang: str) -> str:
    """Правки по v8: одна формулировка для неизвестной цены — «цены на сайте» / «prices on the website»; ровные суммы —
    без копеек (£20, а не £20.00)."""
    v = re.sub(r"\s+", " ", v or "").strip()
    if UNKNOWN_PRICE_RE.match(v):
        return "prices on the website" if lang == "en" else "цены на сайте"
    return re.sub(r"(£\d+(?:,\d{3})*)\.00\b", r"\1", v)


def price_from_data(c: dict) -> tuple[str, str]:
    """Цена по данным базы (если модель ошиблась): «£50», «£5–£20», «free», «price not listed»."""
    vals = sorted({float(x) for x in re.findall(r"\d+(?:\.\d+)?", (c.get("price_text") or "").replace(",", ""))})
    if c.get("price_from") == 0 and not any(vals):
        return "free", "бесплатно"
    if not vals:
        return "price not listed", "цена не указана"
    fmt = lambda x: f"£{x:g}" if x == int(x) else f"£{x:.2f}"
    s = fmt(vals[0]) if len(vals) == 1 else f"{fmt(vals[0])}–{fmt(vals[-1])}"
    return s, s


# --- даты ---

def _day(x: date, lang: str, weekday: bool = True, year: bool = False) -> str:
    if lang == "en":
        s = f"{x.day} {MONTHS_EN[x.month - 1]}" + (f" {x.year}" if year else "")
        return f"{DAYS_EN[x.weekday()]} {s}" if weekday else s
    s = f"{x.day} {MONTHS_RU[x.month - 1]}" + (f" {x.year}" if year else "")
    return f"{DAYS_RU[x.weekday()]}, {s}" if weekday else s


def when(c: dict, w: Window, lang: str) -> str:
    """«Sat 3 Oct, 20:00» / «6–10 Oct» / «until 17 Jan 2027»; для открытий — стадия и дата."""
    if c.get("regular_series"):
        return "regular sessions — see the schedule" if lang == "en" else "регулярные занятия — расписание по ссылке"
    if c["kind"] == "programme":
        if not c["dates"]:
            return "school holidays" if lang == "en" else "в школьные каникулы"
        a, b = d(c["dates"][0][0]), d(c["dates"][0][1])
        s = _day(a, lang, weekday=False) if a == b else (_range(a, b, lang) if a.month == b.month else
                                                         f"{_day(a, lang, weekday=False)} – {_day(b, lang, weekday=False, year=b.year != a.year)}")
        return s
    if c["kind"] == "venue_news":
        stage = {"en": {"opened": "Opened", "coming_soon": "Opening soon", "closed": "Closed"},
                 "ru": {"opened": "Открылось", "coming_soon": "Скоро откроется", "closed": "Закрылось"}}[lang][c["stage"]]
        dt = d(c["date"])
        if dt and c.get("date_basis") == "publication_date":
            # правки по v5: дата открытия = дата статьи — не «Открылось 17 августа», а месяц или «недавно»
            if (w.issue - dt).days <= 21:
                return {"en": {"opened": "Recently opened", "coming_soon": "Opening soon", "closed": "Recently closed"},
                        "ru": {"opened": "Недавно открылось", "coming_soon": "Скоро откроется",
                               "closed": "Недавно закрылось"}}[lang][c["stage"]]
            mon = MONTHS_EN[dt.month - 1] if lang == "en" else ["январе", "феврале", "марте", "апреле", "мае", "июне", "июле",
                                                                "августе", "сентябре", "октябре", "ноябре", "декабре"][dt.month - 1]
            return f"{stage} in {mon}" if lang == "en" else f"{stage.lower().capitalize()} в {mon}"
        return f"{stage} {_day(dt, lang, weekday=False, year=dt.year != w.issue.year)}" if dt else stage
    if c["kind"] == "film_release":   # этап 7b: полный пункт о фильме — «в прокате с пт, 9 октября»
        x = d(c["dates"][0][0])
        if x < w.issue:
            return "now showing" if lang == "en" else "уже в прокате"
        return (f"in cinemas from {_day(x, lang)}" if lang == "en" else f"в прокате с {_day(x, lang)}")
    if not c["dates"]:
        return ""
    starts = [d(x[0]) for x in c["dates"]]
    ends = [d(x[1]) for x in c["dates"]]
    first, last = min(starts), max(ends)
    times = {x[2] for x in c["dates"]}
    time = next(iter(times)) if len(times) == 1 and next(iter(times)) and next(iter(times)) != "11:59" else None
    other_year = last.year != w.issue.year
    days = sorted({d(x[0]) for x in c["dates"]})
    if 1 < len(days) <= 3 and all(d(x[0]) == d(x[1]) for x in c["dates"]):  # отдельные дни: «пн 5 и сб 10 окт.»
        s = (" and " if lang == "en" else " и ").join(_day(x, lang, year=other_year) for x in days)
    elif first == last:
        s = _day(first, lang, year=other_year)
    elif first < w.start:  # идёт давно: выставки
        s = ("until " if lang == "en" else "до ") + _day(last, lang, weekday=False, year=other_year)
    elif first.month == last.month and first.year == last.year:
        s = (f"{first.day}–{last.day} {MONTHS_EN[last.month - 1]}" if lang == "en"
             else f"{first.day}–{last.day} {MONTHS_RU[last.month - 1]}") + (f" {last.year}" if other_year else "")
    else:
        s = f"{_day(first, lang, weekday=False)} – {_day(last, lang, weekday=False, year=other_year)}"
    if time and len(c["dates"]) == 1 and first == last:
        s += f", {time}"
    elif first == last and len(c["dates"]) > 1 and all(x[2] for x in c["dates"]):  # один день, два сеанса
        s += ", " + (" and " if lang == "en" else " и ").join(sorted(times))
    if c["kind"] == "tickets" and c.get("on_sale_date"):
        osd = d(c["on_sale_date"])
        label = ("on sale from " if osd > w.issue else "on sale since ") if lang == "en" else \
                ("продажа с " if osd > w.issue else "в продаже с ")
        s += f" · {label}{_day(osd, lang, weekday=False)}"
    return s


# --- Markdown ---

def _range(a: date, b: date, lang: str) -> str:
    return (f"{a.day}–{b.day} {MONTHS_EN[b.month - 1]}" if lang == "en" else f"{a.day}–{b.day} {MONTHS_RU[b.month - 1]}")


def rubric_title(rub: str, w: Window, lang: str, theme: str = "") -> str:
    we = w.weekend_of(rub)
    if we:
        return RUBRIC_TITLES[lang]["weekend"].format(weekend=_range(*we, lang))
    return RUBRIC_TITLES[lang][rub].format(theme=theme)


def importance_of(p: Pools, it: dict) -> float:
    return max(((p.candidates[i].get("importance") or 0) for i in it["ids"] if i in p.candidates), default=0)


def access_mark(c: dict, lang: str) -> tuple[str, str | None]:
    """Этап 7b: пометка в строке с датой для событий «только для членов» и ссылка на страницу членства."""
    if c.get("access") != "members":
        return "", None
    f = dict(x.split("=", 1) for x in (c.get("access_note") or "").split("|") if "=" in x)
    org, fee = f.get("org"), f.get("fee")
    if lang == "en":
        s = f"members only — {org}" if org else "members only"
        s += f" (membership {fee} a year)" if fee else ""
    else:
        s = f"только для членов {org}" if org else "только для членов клуба"
        s += f" (членство — {fee} в год)" if fee else ""
    return s, f.get("url")


LIBRARIES_URL = "https://www.eventbrite.co.uk/o/cambridgeshire-libraries-33302830317"   # все события библиотек (S055)


PAGE_URGENCY_MARK = {"few_left": {"en": "few tickets left", "ru": "мало билетов"},
                     "selling_fast": {"en": "selling fast", "ru": "билеты быстро раскупают"},
                     "early_bird_ends": {"en": "early-bird price ending", "ru": "заканчивается ранняя цена"}}
# «some_dates_sold_out» (метка «Sold out» и кнопка покупки на одной странице) неоднозначно — только редактору


def layout(result: dict, p: Pools, w: Window, lang: str) -> dict:
    """Выпуск как структура (для Markdown и читательского HTML): шапка, вступление, разделы → подразделы → пункты."""
    weekends = (" and " if lang == "en" else " и ").join(_range(a, b, lang) for a, b in w.weekends)
    period = f"{_day(w.start, lang, weekday=False)} – {_day(w.end, lang, weekday=False)}"
    if lang == "en":
        title = f"What's on in Cambridge — {w.issue.day} {MONTHS_EN[w.issue.month - 1]} {w.issue.year}"
        sub = f"Events {period} · weekends: {weekends}"
    else:
        title = f"Что происходит в Кембридже — {w.issue.day} {MONTHS_RU[w.issue.month - 1]} {w.issue.year}"
        sub = f"События {period} · выходные: {weekends}"
    sections = {s["rubric"]: s["items"] for s in result["sections"]}
    out = {"title": title, "subtitle": sub, "intro": result[f"intro_{lang}"], "sections": []}
    for rub in w.rubrics():
        if rub == "holidays":   # без модели, одна строка на программу (правки по v4)
            groups = holiday_groups(p, w, lang)
            if groups:
                out["sections"].append({"rubric": rub, "title": rubric_title(rub, w, lang), "intro": "", "groups": groups})
            continue
        items = sections.get(rub) or []
        if rub == "colleges":   # этап 7c: по дате
            items = sorted(items, key=lambda it: tuple(x or "" for x in (p.candidates[it["ids"][0]].get("dates") or [("",)])[0]))
        elif rub == "weekdays":   # правки по v5: «На неделе» — по дате
            items = sorted(items, key=lambda it: min((x[0], x[2] or "") for i in it["ids"]
                                                     for x in (p.candidates[i]["dates"] or [("9999", "", None)])))
        elif rub == "new_in_town":   # сначала Кембридж
            items = sorted(items, key=lambda it: not re.search(r"\bCambridge\b", p.candidates[it["ids"][0]].get("address") or ""))
        elif rub != "theme":   # «Тема недели» — порядок по смыслу, как у модели (правки по v3); остальное — по важности
            items = sorted(items, key=lambda it: (bool(it.get("union")), -importance_of(p, it) if it["ids"] else 0))
        featured = {p.candidates[i].get("norm") for it in items for i in it["ids"] if i.startswith("F")}
        rel = release_lines(p, w, lang, featured) if rub == "cinema" else []
        if not items and not rel:
            continue  # пустые рубрики не выводим (правки по v2)
        sec = {"rubric": rub, "title": rubric_title(rub, w, lang, result.get(f"theme_title_{lang}", "")),
               "intro": result.get(f"theme_intro_{lang}", "") if rub == "theme" else "", "groups": []}
        groups: dict[str, list] = {}
        for it in items:
            if it.get("union"):   # этап 7c: строка «В Cambridge Union на этой неделе (для членов клуба): …»
                groups.setdefault("", []).append({"title": it[f"title_{lang}"], "meta": it.get(f"meta_{lang}", ""),
                                                  "blurb": "", "url": it.get("url"), "ids": [], "compact": True})
                continue
            c = p.candidates[it["ids"][0]]
            evs = [p.candidates[i] for i in it["ids"] if p.candidates[i]["kind"] == c["kind"] == "event"]
            if len(evs) > 1:  # два дня одной выставки на разных площадках и т.п.
                c = c | {"dates": sorted({x for e in evs for x in e["dates"]}, key=lambda x: tuple(y or "" for y in x))}
            price = "" if c["kind"] in ("venue_news", "film_release") else norm_price(it[f"price_{lang}"], lang)
            where_ = film_where(c, lang) if c["kind"] == "film_release" else it[f"where_{lang}"]
            urg = next((p.candidates[i].get("page_urgency") for i in it["ids"] if p.candidates[i].get("page_urgency")), None)
            mark = PAGE_URGENCY_MARK.get(urg, {}).get(lang, "") if c["kind"] != "cancellation" else ""
            acc, acc_url = access_mark(c, lang)
            if c["kind"] == "cancellation":   # правки по v8: отмена — одной строкой: что, когда, где, «отменено»
                price = {"postponed": ("postponed", "перенесено")}.get(c.get("status"), ("cancelled", "отменено"))[
                    0 if lang == "en" else 1]
            meta = " · ".join(x for x in (when(c, w, lang), where_, price, acc, mark) if x)
            if it.get("line") and it.get("kind_ru") and lang == "ru":   # «В колледжах»: вид события — в строке
                meta = f"{it['kind_ru']} · {meta}"
            title = it[f"title_{lang}"]
            if c["kind"] == "venue_news" and not re.search(r"\bCambridge\b", c.get("address") or ""):
                town = (c.get("address") or "").split(",")[-1].strip()   # правки по v5: городок — в заголовке строки
                if town and town.lower() not in title.lower():
                    title = f"{title} — {town}"
            # правки по v4: забеги и триатлоны с регистрацией участников — подраздел «Поучаствовать» в «Спорте»
            key = "take_part" if rub == "sport" and any(p.candidates[i].get("participant") for i in it["ids"]) else ""
            if rub == "sport" and not key and (it.get("also") or set(c.get("sources") or []) & ALSO_PLAYING):
                key = "also"   # правки после v5: нелиговый и женский футбол — одной строкой в «Также играют»
            blurb = "" if c["kind"] == "cancellation" else it[f"blurb_{lang}"].strip()
            url = it.get("url") or c["url"]   # этап 7c: ссылка на первоисточник (issue_fixes.fix_links)
            if len(it["ids"]) > 1 and all(set(p.candidates[i].get("sources") or []) <= {"S055"} for i in it["ids"]):
                url = LIBRARIES_URL   # правки по v8: «Регулярно в библиотеках» — страница всех событий библиотек
            groups.setdefault(key, []).append({"title": title, "meta": meta, "access_url": acc_url,
                                               "blurb": blurb, "url": url, "ids": it["ids"],
                                               **({"compact": True} if it.get("line") else {})})
        for key in sorted(groups, key=lambda k: ["", "also", "take_part"].index(k)):
            sub_title = {"take_part": ("Take part", "Поучаствовать"), "also": ("Also playing", "Также играют")}.get(key)
            items_ = groups[key]
            if key == "also":   # по дате
                items_ = sorted((x | {"compact": True} for x in items_),
                                key=lambda x: tuple(y or "" for y in (p.candidates[x["ids"][0]].get("dates") or [("",)])[0]))
            sec["groups"].append({"title": (sub_title[0] if lang == "en" else sub_title[1]) if sub_title else "",
                                  "items": items_})
        if rel:   # решения после 6c: новые фильмы недели — из календаря релизов, первой строкой рубрики
            sec["groups"].insert(0, {"title": "", "items": rel})
        out["sections"].append(sec)
    return out


def render(result: dict, p: Pools, w: Window, lang: str, editor: dict) -> str:
    L = layout(result, p, w, lang)
    more = "More" if lang == "en" else "Подробнее"
    lines = [f"# {L['title']}", "", f"*{L['subtitle']}*", "", L["intro"], ""]
    for sec in L["sections"]:
        lines += [f"## {sec['title']}", ""]
        if sec["intro"]:
            lines += [sec["intro"], ""]
        for g in sec["groups"]:
            if g["title"]:
                lines += [f"### {g['title']}", ""]
            for it in g["items"]:
                if it.get("compact"):   # «Каникулы»: одна строка на программу
                    head = f"[{it['title']}]({it['url']})" if it.get("url") else it["title"]
                    lines += [f"- **{head}**" + (f" — {it['meta']}" if it["meta"] else "")]
                    continue
                acc = (f" ([{'membership' if lang == 'en' else 'членство'}]({it['access_url']}))"
                       if it.get("access_url") else "")
                lines += [f"**{it['title']}** — {it['meta']}{acc}  ",
                          (f"{it['blurb']} " if it["blurb"] else "") + f"[{more} →]({it['url']})", ""]
            if any(it.get("compact") for it in g["items"]):
                lines += [""]
    lines += ["---", "", "## For the editor" if lang == "en" else "## Для редактора", ""]
    for title, entries in editor[lang]:
        lines += [f"**{title}**", ""]
        lines += [f"- {x}" for x in entries] if entries else ["- —"]
        lines += [""]
    return "\n".join(lines).rstrip() + "\n"


def render_reader_html(result: dict, p: Pools, w: Window, lang: str) -> str:
    """Читательская версия без блока «Для редактора»: одна колонка «как письмо», читается на телефоне."""
    from html import escape as e
    L = layout(result, p, w, lang)
    more = "More" if lang == "en" else "Подробнее"
    body = [f'<h1>{e(L["title"])}</h1>', f'<p class="sub">{e(L["subtitle"])}</p>', f'<p class="intro">{e(L["intro"])}</p>']
    for sec in L["sections"]:
        body.append(f'<section><h2>{e(sec["title"])}</h2>')
        if sec["intro"]:
            body.append(f'<p class="secintro">{e(sec["intro"])}</p>')
        for g in sec["groups"]:
            if g["title"]:
                body.append(f'<h3>{e(g["title"])}</h3>')
            for it in g["items"]:
                body.append(item_html(it, more, lang))
        body.append("</section>")
    return READER_HTML.format(lang=lang, title=e(L["title"]), body="\n".join(body), extra_css="")


def item_html(it: dict, more: str, lang: str = "ru") -> str:
    from html import escape as e
    if it.get("compact"):   # «Каникулы»: одна строка на программу
        head = f'<a href="{e(it["url"])}">{e(it["title"])}</a>' if it.get("url") else f'<b>{e(it["title"])}</b>'
        return f'<p class="line">{head}' + (f' — <span class="m2">{e(it["meta"])}</span>' if it["meta"] else "") + '</p>'
    return ('<article class="item">'
            f'<p class="t"><a href="{e(it["url"])}">{e(it["title"])}</a></p>'
            f'<p class="m">{e(it["meta"])}'
            + (f' (<a href="{e(it["access_url"])}">{"membership" if lang == "en" else "членство"}</a>)'
               if it.get("access_url") else "") + '</p>'
            + (f'<p class="b">{e(it["blurb"])}</p>' if it["blurb"] else "")
            + f'<p class="more"><a href="{e(it["url"])}">{more} →</a></p></article>')


READER_HTML = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#f4f1ea; --card:#fffdf8; --ink:#1f1d1a; --muted:#6b645a; --accent:#8a3b12; --line:#e3dccf; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1a18; --card:#24221f; --ink:#ece7de; --muted:#a59d90; --accent:#e39a6a; --line:#3a3631; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:17px/1.55 Georgia, "Times New Roman", serif; }}
.wrap {{ max-width:640px; margin:0 auto; padding:24px 16px 48px; }}
.letter {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:28px 22px; }}
h1 {{ font-size:1.6em; line-height:1.2; margin:0 0 6px; }}
.sub {{ color:var(--muted); font-style:italic; margin:0 0 18px; }}
.intro {{ font-size:1.05em; margin:0 0 8px; }}
section {{ border-top:1px solid var(--line); margin-top:26px; padding-top:18px; }}
h2 {{ font:700 1.15em/1.3 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color:var(--accent); margin:0 0 10px; }}
h3 {{ font:600 1em/1.3 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; margin:18px 0 6px; }}
.secintro {{ margin:0 0 10px; }}
.item {{ margin:0 0 16px; }}
.item p {{ margin:0; }}
.t {{ font-weight:700; }}
.t a {{ color:var(--ink); text-decoration:none; }}
.t a:hover {{ text-decoration:underline; }}
.m {{ color:var(--muted); font:14px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; margin:2px 0 4px !important; }}
.more a {{ color:var(--accent); font:14px -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
a {{ color:var(--accent); overflow-wrap:anywhere; }}
.line {{ margin:0 0 8px; font-size:.95em; }}
.line a {{ color:var(--ink); font-weight:700; }}
.m2 {{ color:var(--muted); font:14px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
{extra_css}
</style></head>
<body><div class="wrap"><div class="letter">
{body}
</div></div></body></html>
"""


# --- редакторская версия (с v5): читательская вёрстка + все кандидаты рубрик под катом + «Для редактора» ---

EDITOR_CSS = """details { margin:10px 0 4px; border:1px dashed var(--line); border-radius:8px; padding:6px 10px; }
summary { cursor:pointer; color:var(--muted); font:600 14px -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.cands { list-style:none; margin:8px 0 0; padding:0; font:13px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.cands li { padding:5px 0; border-top:1px solid var(--line); }
.cands li.in { background:var(--hl); }
.cands .mark { display:inline-block; width:1.3em; color:var(--accent); font-weight:700; }
.cands .why { color:var(--accent); }
.cands .src, .cands .sc { color:var(--muted); }
.stub h2 { color:var(--muted); }
.tbl { overflow-x:auto; }
select { max-width:100%; font:inherit; }
table { border-collapse:collapse; font:12px/1.4 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; min-width:560px; }
th, td { border-top:1px solid var(--line); padding:4px 6px; text-align:left; vertical-align:top; }
.editor { font:14px/1.5 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.editor h3 { margin:16px 0 4px; }
.editor ul { padding-left:18px; margin:4px 0; }
.badge { display:inline-block; font:600 12px -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color:var(--card);
  background:var(--accent); border-radius:4px; padding:1px 6px; margin-left:6px; vertical-align:middle; }
:root { --hl:#f6ecd9; }
@media (prefers-color-scheme: dark) { :root { --hl:#2f2a22; } }"""


def _n_ru(n: int, one: str, few: str, many: str) -> str:
    w = one if n % 10 == 1 and n % 100 != 11 else few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many
    return f"{n} {w}"


def _cands_html(rows: list[dict], lang: str, placed_n: int, items_n: int | None = None) -> str:
    from html import escape as e
    if not rows:
        return ""
    merged = placed_n - items_n if items_n is not None and placed_n > items_n else 0
    if merged:   # правки по v5: при склейке — «6 событий → 5 пунктов (2 объединены)»
        n_m = sum(1 for r in rows if r.get("in") and r.get("merged")) or merged + 1
        label = (f"All candidates of this rubric — {len(rows)}; in the issue: {placed_n} events → {items_n} items "
                 f"({n_m} merged)" if lang == "en" else
                 f"Все события рубрики — {len(rows)}; в выпуске: {_n_ru(placed_n, 'событие', 'события', 'событий')} → "
                 f"{_n_ru(items_n, 'пункт', 'пункта', 'пунктов')} ({n_m} объединены)")
    else:
        label = (f"All candidates of this rubric — {len(rows)} (in the issue: {placed_n})" if lang == "en"
                 else f"Все события рубрики — {len(rows)} (в выпуске {placed_n})")
    out = [f"<details><summary>{e(label)}</summary><ul class=\"cands\">"]
    for r in rows:
        title = f'<a href="{e(r["url"])}">{e(r["title"])}</a>' if r.get("url") else e(r["title"])
        meta = " · ".join(x for x in (r["when"][lang], f'{r["venue"]}' + (f' ({r["zone"]})' if r["zone"] else ""),
                                      r["price"][lang]) if x and x.strip())
        score = f'<span class="sc">★ {r["score"]:g}</span>' if r.get("score") else ""
        src = f'<span class="src">{e(", ".join(r["sources"]))}</span>' if r["sources"] else ""
        why = "" if r["in"] else f' — <span class="why">{e(r["why"][lang])}</span>'
        if r["in"] and r.get("merged"):
            why = ' — <span class="why">' + ("merged into one item" if lang == "en" else "объединено в один пункт") + "</span>"
        out.append(f'<li class="{"in" if r["in"] else ""}"><span class="mark">{"✓" if r["in"] else ""}</span>{title}'
                   f'{(" — " + e(meta)) if meta else ""} {score} {src}{why}</li>')
    out.append("</ul></details>")
    return "\n".join(out)


def render_editor_html(result: dict, p: Pools, w: Window, lang: str, editor: dict, lists: dict, plate: str = "") -> str:
    """Та же вёрстка, что у читательской версии, плюс под каждой рубрикой — все кандидаты (в выпуске отмечены, у
    остальных — причина), рубрика «Не попало никуда» и блок «Для редактора» в конце."""
    from html import escape as e
    L = layout(result, p, w, lang)
    more = "More" if lang == "en" else "Подробнее"
    badge = "editor's version" if lang == "en" else "редакторская версия"
    # этап 7c: красная плашка «НЕ ОТПРАВЛЯТЬ: …» (блокирующие проверки tests/issue_rules) — самой первой строкой
    body = [plate, f'<h1>{e(L["title"])}<span class="badge">{badge}</span></h1>', f'<p class="sub">{e(L["subtitle"])}</p>',
            f'<p class="intro">{e(L["intro"])}</p>']
    shown = {sec["rubric"]: sec for sec in L["sections"]}
    for rub in w.rubrics():
        rows = lists.get(rub, [])
        sec = shown.get(rub)
        if not sec and not rows:
            continue
        placed = sum(r["in"] for r in rows)
        items_n = sum(len(g["items"]) for g in sec["groups"]) if sec else 0
        if sec:
            body.append(f'<section><h2>{e(sec["title"])}</h2>')
            if sec["intro"]:
                body.append(f'<p class="secintro">{e(sec["intro"])}</p>')
            for g in sec["groups"]:
                if g["title"]:
                    body.append(f'<h3>{e(g["title"])}</h3>')
                for it in g["items"]:
                    body.append(item_html(it, more, lang))
        else:
            title = "Theme of the week" if rub == "theme" and lang == "en" else \
                "Тема недели" if rub == "theme" else rubric_title(rub, w, lang)
            hidden = "not in the issue" if lang == "en" else "в выпуск не вошла"
            body.append(f'<section class="stub"><h2>{e(title)} — {hidden}</h2>')
        body.append(_cands_html(rows, lang, placed, items_n if rub not in ("holidays",) else None))
        body.append("</section>")
    nowhere = lists.get("nowhere", [])
    body.append(f'<section><h2>{"Didn’t fit anywhere" if lang == "en" else "Не попало никуда"}</h2>')
    body.append(_cands_html(nowhere, lang, 0).replace(
        "Все события рубрики", "События окна вне рубрик").replace("All candidates of this rubric", "Events of the window outside all rubrics"))
    body.append("</section>")
    body.append(_dropped_html(lists.get("dropped", []), lang))
    body.append(_unparsed_html(lists.get("unparsed", []), lang))
    body.append(f'<section class="editor"><h2>{"For the editor" if lang == "en" else "Для редактора"}</h2>')
    for title, entries in editor[lang]:
        body.append(f"<h3>{e(title)}</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in (entries or ["—"])) + "</ul>")
    body.append("</section>")
    return READER_HTML.format(lang=lang, title=e(L["title"] + (" — editor" if lang == "en" else " — редактор")),
                              body="\n".join(body), extra_css=EDITOR_CSS + "\n" + _plate_css())


def _plate_css() -> str:
    from tests.issue_rules import PLATE_CSS
    return PLATE_CSS


def _dropped_html(rows: list[dict], lang: str) -> str:
    """Сводная таблица отсеянных пунктов выпуска с фильтром по причине (правки после v5); то же — в CSV."""
    from html import escape as e
    if not rows:
        return ""
    reasons = sorted({r["why"][lang] for r in rows})
    opts = "".join(f'<option value="{e(x)}">{e(x)} — {sum(r["why"][lang] == x for r in rows)}</option>' for x in reasons)
    head = ("Dropped items — summary" if lang == "en" else "Отсеянные пункты — сводная таблица")
    th = ("Reason", "Event", "Date", "Venue (zone)", "Score", "Rubric") if lang == "en" else \
        ("Причина", "Событие", "Дата", "Площадка (зона)", "Оценка", "Рубрика")
    trs = "".join(f'<tr data-r="{e(r["why"][lang])}"><td>{e(r["why"][lang])}</td><td>'
                  + (f'<a href="{e(r["url"])}">{e(r["title"])}</a>' if r.get("url") else e(r["title"]))
                  + f'</td><td>{e(r["when"][lang])}</td><td>{e(r["venue"])}{" (" + e(r["zone"]) + ")" if r["zone"] else ""}</td>'
                  f'<td>{r["score"] if r["score"] is not None else ""}</td><td>{e(r.get("rubric", ""))}</td></tr>' for r in rows)
    label = "Filter by reason" if lang == "en" else "Фильтр по причине"
    allr = "all" if lang == "en" else "все"
    return (f'<section><h2>{head}</h2><details><summary>{len(rows)}</summary>'
            f'<p><label>{label}: <select onchange="var v=this.value;document.querySelectorAll(\'#dropped tr[data-r]\')'
            f'.forEach(function(t){{t.style.display=(!v||t.dataset.r===v)?\'\':\'none\'}})"><option value="">{allr}</option>{opts}'
            f'</select></label></p><div class="tbl"><table id="dropped"><tr>{"".join(f"<th>{x}</th>" for x in th)}</tr>{trs}'
            f'</table></div></details></section>')


def _unparsed_html(rows: list[dict], lang: str) -> str:
    """Лист «Не разобрано» — раздел редакторской версии."""
    from html import escape as e
    if not rows:
        return ""
    head = "Not parsed (sources we could not collect)" if lang == "en" else "Не разобрано (источники, которые не удалось собрать)"
    th = ("ID", "Source", "Problem", "Since", "What we lose", "Action", "Checked") if lang == "en" else \
        ("ID", "Источник", "Проблема", "С какой даты", "Что теряем", "Что делать", "Проверено")
    trs = "".join(f'<tr><td>{e(r["key"])}</td><td><a href="{e(r["url"])}">{e(r["name"] or r["url"])}</a></td>'
                  f'<td>{e(r["problem"])}</td><td>{e(r["since"] or "")}</td><td>{e(r["losing"] or "")}</td>'
                  f'<td>{e(r["action"] or "")}</td><td>{e((r["last_checked"] or "")[:10])}</td></tr>' for r in rows)
    return (f'<section><h2>{head}</h2><details><summary>{len(rows)}</summary><div class="tbl"><table>'
            f'<tr>{"".join(f"<th>{x}</th>" for x in th)}</tr>{trs}</table></div></details></section>')
