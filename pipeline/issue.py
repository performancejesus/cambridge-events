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

from . import evergreen, kids, lineup
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
FIXED_RUBRICS = ["weekdays", "exhibitions", "free", "kids", "holidays", "sport", "out_of_town", "county",
                 "new_announcements", "tickets", "cancelled", "new_in_town"]
RUBRIC_TITLES = {
    "en": {"theme": "Theme of the week: {theme}", "weekend": "The weekend: {weekend}",
           "weekdays": "Weekdays: concerts, theatre, comedy", "exhibitions": "Exhibitions", "free": "Free",
           "kids": "With kids", "holidays": "School holidays: where to book your child", "sport": "Sport",
           "out_of_town": "Out of town (within an hour)", "county": "Around the county",
           "new_announcements": "Just announced", "tickets": "Get your tickets",
           "cancelled": "Cancelled and postponed", "new_in_town": "New in town"},
    "ru": {"theme": "Тема недели: {theme}", "weekend": "Главное на выходные {weekend}",
           "weekdays": "На неделе: концерты, театр, комедия", "exhibitions": "Выставки", "free": "Бесплатно",
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
COUNTY_WEEKEND_MIN = 8.0    # «Кембриджшир, дальше часа» в «Главном на выходные» — только от 8 (правки по v3)
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
                     r"baby|half[- ]term|ages? \d|aged \d|years? \d+\s*[-–]\s*\d+|under[- ]?\d+s)\b", re.I)
# Семейные категории, которыми источник сам размечает события (фильтры UCM «для кого», раздел Visit Cambridge,
# раздел University What's On, Science Centre) — явная пометка, не догадка (этап 6).
FAMILY_CATEGORIES = {"family", "families", "family events", "family friendly", "under 5s", "ages 5+"}
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
        "free_tag": e["price_from"] == 0,
    }
    fame = con.execute("SELECT result FROM fame_cache WHERE event_id=?", (e["event_id"],)).fetchone()
    if fame:
        performer = json.loads(fame["result"]).get("performer")
        if performer:
            facts["performer"] = performer   # кто на сцене — имя должно дойти до текста пункта
    names = lineup.names(con, e["event_id"])
    if names:
        facts["lineup"] = names              # правки по v4: все названные участники из всех склеенных записей
    if (PARTICIPATE_RE.search(e["title"]) or (PARTICIPATE_WEAK_RE.search(e["title"]) and (
            REGISTER_RE.search(summary or "") or "sport" in [c.lower() for c in cats]))) \
            and not NOT_PARTICIPATE_RE.search(e["title"]):
        facts["participant"] = True          # регистрация участников, не билеты для зрителей
    if e["source_type"] != "recurring" and thin(e["title"], summary, facts.get("performer"), names):   # дата ежегодного события — сама факт
        facts["thin_data"] = True            # в данных нет ни одного содержательного факта для описания
    if evergreen.regular_series(con, e["event_id"]):
        facts["regular_series"] = True
    note = _merge_notes().get((e["date_start"], e["title"]))
    if note:
        facts["editor_note"] = note
    return facts


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
    # площадки нет, но есть адрес (Visit Cambridge, Visit Ely) — место известно
    if (not e["venue_name"] or NO_VENUE_RE.match(e["venue_name"])) and not e["multi_venue"] and not e["address"]:
        return "нет площадки или адреса"
    if e["zone"] not in LISTED_ZONES:
        return "зона не определена (нет postcode)" if not e["zone"] else "вне зоны"
    if e["status"] in ("cancelled", "postponed", "disappeared", "past"):
        return f"статус {e['status']}"
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
        facts["dates"] = sorted({(g["date_start"], g["date_end"] or g["date_start"], g["time_start"]) for g in group})
        facts["event_ids"] = [g["event_id"] for g in group]
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
    _kids_programmes(con, w, p)
    return p


def _kids_programmes(con, w: Window, p: Pools) -> None:
    """«Каникулы: куда записать ребёнка» — программы из kids_programmes (этап 6-v4): ближайшие каникулы в пределах
    8 недель от даты выпуска (октябрьские — запись идёт; рождественские — кто уже открыл запись)."""
    if not con.execute("SELECT name FROM sqlite_master WHERE name='kids_programmes'").fetchone():
        return
    horizon = (w.issue + timedelta(weeks=13)).isoformat()
    texts = {x["id"]: x.get("text", {}) for x in json.loads(kids.DATA.read_text())["programmes"]}
    for k in con.execute("SELECT * FROM kids_programmes ORDER BY prog_id").fetchall():
        if k["date_start"] and not (w.issue.isoformat() <= (k["date_end"] or k["date_start"]) and k["date_start"] <= horizon):
            continue
        p.candidates[k["prog_id"]] = {
            "kind": "programme", "title": k["title"], "provider": k["provider"], "holiday": k["holiday"],
            "ages": k["ages"], "hours": k["hours"], "price_text": k["price"], "venue": k["venue"],
            "address": k["address"], "postcode": k["postcode"], "zone": k["zone"], "places": k["places"],
            "booking_opens": k["booking_opens"], "audience": k["audience"], "verified": bool(k["verified"]),
            "note": k["note"], "url": k["url"], "event_ids": [], "sources": ["web_search"],
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
        p.candidates[f"T{u['update_id']}"] = facts


def _cancellations(con, w: Window, p: Pools) -> None:
    for e in con.execute("""SELECT * FROM events WHERE status IN ('cancelled','postponed','disappeared')
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
        p.candidates[f"V{v['news_id']}"] = {
            "kind": "venue_news", "title": v["name"], "type": v["type"], "stage": v["stage"],
            "address": v["address"], "postcode": v["postcode"], "date": v["date"], "date_basis": v["date_basis"],
            "published": (v["published"] or "")[:10] or None, "note": v["note"], "sources": [v["source_id"]],
            "source_type": v["source_type"], "url": v["url"], "event_ids": [], "dates": []}


ZONE_ORDER = ["центр", "до 30 мин", "до часа", geo_COUNTY_FAR]
AGES_RU = [(r"^school age$", "школьники"), (r"^families$", "семьи"), (r"^children, by level$", "дети, по уровню"),
           (r"^primary and secondary$", "начальная и средняя школа"), (r"^Reception – (\d+)$", r"от Reception до \1 лет"),
           (r"^(\d+)\s*[–-]\s*(\d+)(?: \((.*)\))?$", r"\1–\2 лет")]
AUDIENCE = {"eligible": {"en": "for families eligible for free school meals",
                         "ru": "для семей с правом на бесплатное школьное питание"},
            "university": {"en": "only for children of University of Cambridge staff and students",
                           "ru": "только для детей сотрудников и студентов университета"}}


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
        elif c["zone"] not in LISTED_ZONES and not (c["zone"] is None and c["audience"] == "eligible"):
            why[cid] = "вне зоны" if c["zone"] else "зона не определена (нет postcode)"
        else:
            chosen.append(cid)
    return chosen, why


def _ages(a: str | None, lang: str) -> str:
    if not a or lang == "en":
        return a or ""
    for pat, rep in AGES_RU:
        if re.match(pat, a):
            return re.sub(pat, rep, a)
    return a


def holiday_groups(p: Pools, w: Window, lang: str) -> list[dict]:
    """Подразделы «Каникул»: по каникулам, внутри — по зоне (Кембридж → до 30 мин → дальше). Одинаковые программы
    одного провайдера на разных площадках — одной строкой со списком площадок."""
    chosen, _ = holiday_selection(p)
    lines: dict[tuple, dict] = {}
    for cid in chosen:
        c = p.candidates[cid]
        t = c.get("text") or {}
        key = (c["holiday"], c["provider"], t.get(f"title_{lang}") or c["title"])
        x = lines.setdefault(key, {"c": c, "ids": [], "where": [], "zone": 9})
        x["ids"].append(cid)
        where, price = t.get(f"where_{lang}") or c["venue"] or "", t.get(f"price_{lang}") or ""
        if (where, price) not in x["where"]:
            x["where"].append((where, price))
        z = ZONE_ORDER.index(c["zone"]) if c["zone"] in ZONE_ORDER else 8
        x["zone"] = min(x["zone"], z)
    groups: dict[str, list] = {}
    for (hol, provider, title), x in sorted(lines.items(), key=lambda kv: (kv[1]["zone"], kv[0][1].lower())):
        c = x["c"]
        places = list(dict.fromkeys(wh for wh, _ in x["where"] if wh))
        prices = list(dict.fromkeys(pr for _, pr in x["where"] if pr))
        if len(prices) > 1:   # разные цены на разных площадках — цена при каждой площадке
            place, price = "; ".join(f"{wh} ({pr})" for wh, pr in x["where"]), ""
        else:
            place, price = "; ".join(places), (prices[0] if prices else "")
        ages = _ages(c["ages"], lang)
        notes = []
        if c["audience"] in AUDIENCE:
            notes.append(AUDIENCE[c["audience"]][lang])
        if c["places"] == "few_left":
            notes.append("few places left" if lang == "en" else "мест мало")
        if c["places"] == "not_open" and c.get("booking_opens"):
            bo = c["booking_opens"]
            bo = _day(d(bo), lang, weekday=False) if re.match(r"\d{4}-\d\d-\d\d", bo) else bo
            notes.append(("booking opens " if lang == "en" else "запись открывается: ") + bo)
        head = f"{provider} — {title}" + (f" ({ages})" if ages else "")
        meta = " · ".join(v for v in [when(c, w, lang), place, price] + notes if v)
        groups.setdefault(hol, []).append({"title": head, "meta": meta, "blurb": "", "url": c["url"], "compact": True,
                                           "ids": x["ids"]})
    out = []
    for hol in ["october_half_term", "christmas", "both"]:
        if hol not in groups:
            continue
        if hol in HOLIDAY_TITLES:
            h = kids.holidays()[hol]
            rng = f"{_day(d(h['start']), lang, weekday=False)} – {_day(d(h['end']), lang, weekday=False, year=d(h['end']).year != w.issue.year)}"
            title = f"{HOLIDAY_TITLES[hol][lang]}, {rng} — {HOLIDAY_NOTES[hol][lang]}"
        else:
            title = "Both holidays" if lang == "en" else "На все каникулы"
        out.append({"title": title, "items": groups[hol]})
    return out


def model_view(p: Pools) -> list[dict]:
    """Кандидаты для модели: только нужные поля, без пустых. «Каникулы» собираются без модели."""
    out = []
    for cid, c in p.candidates.items():
        if c["kind"] == "programme":
            continue
        item = {"id": cid} | {k: v for k, v in c.items()
                              if k not in ("url", "event_ids", "importance_reason") and v not in (None, "", [], False)}
        if item.get("summary") and (c.get("importance") or 0) < 6:   # экономия: полный состав нужен крупным событиям
            item["summary"] = item["summary"][:400]
        out.append(item)
    return out


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
        return f"{stage} {_day(dt, lang, weekday=False, year=dt.year != w.issue.year)}" if dt else stage
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
    return max((p.candidates[i].get("importance") or 0) for i in it["ids"])


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
        if rub != "theme":   # «Тема недели» — порядок по смыслу, как у модели (правки по v3); остальное — по важности
            items = sorted(items, key=lambda it: -importance_of(p, it))
        if not items:
            continue  # пустые рубрики не выводим (правки по v2)
        sec = {"rubric": rub, "title": rubric_title(rub, w, lang, result.get(f"theme_title_{lang}", "")),
               "intro": result.get(f"theme_intro_{lang}", "") if rub == "theme" else "", "groups": []}
        groups: dict[str, list] = {}
        for it in items:
            c = p.candidates[it["ids"][0]]
            evs = [p.candidates[i] for i in it["ids"] if p.candidates[i]["kind"] == c["kind"] == "event"]
            if len(evs) > 1:  # два дня одной выставки на разных площадках и т.п.
                c = c | {"dates": sorted({x for e in evs for x in e["dates"]}, key=lambda x: tuple(y or "" for y in x))}
            price = "" if c["kind"] == "venue_news" else it[f"price_{lang}"]
            meta = " · ".join(x for x in (when(c, w, lang), it[f"where_{lang}"], price) if x)
            # правки по v4: забеги и триатлоны с регистрацией участников — подраздел «Поучаствовать» в «Спорте»
            key = "take_part" if rub == "sport" and any(p.candidates[i].get("participant") for i in it["ids"]) else ""
            groups.setdefault(key, []).append({"title": it[f"title_{lang}"], "meta": meta,
                                               "blurb": it[f"blurb_{lang}"].strip(), "url": c["url"], "ids": it["ids"]})
        for key in sorted(groups, key=lambda k: k == "take_part"):
            sub_title = ("Take part" if lang == "en" else "Поучаствовать") if key == "take_part" else ""
            sec["groups"].append({"title": sub_title, "items": groups[key]})
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
                    lines += [f"- **[{it['title']}]({it['url']})** — {it['meta']}"]
                    continue
                lines += [f"**{it['title']}** — {it['meta']}  ",
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
                body.append(item_html(it, more))
        body.append("</section>")
    return READER_HTML.format(lang=lang, title=e(L["title"]), body="\n".join(body), extra_css="")


def item_html(it: dict, more: str) -> str:
    from html import escape as e
    if it.get("compact"):   # «Каникулы»: одна строка на программу
        return f'<p class="line"><a href="{e(it["url"])}">{e(it["title"])}</a> — <span class="m2">{e(it["meta"])}</span></p>'
    return ('<article class="item">'
            f'<p class="t"><a href="{e(it["url"])}">{e(it["title"])}</a></p>'
            f'<p class="m">{e(it["meta"])}</p>'
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
.editor { font:14px/1.5 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
.editor h3 { margin:16px 0 4px; }
.editor ul { padding-left:18px; margin:4px 0; }
.badge { display:inline-block; font:600 12px -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color:var(--card);
  background:var(--accent); border-radius:4px; padding:1px 6px; margin-left:6px; vertical-align:middle; }
:root { --hl:#f6ecd9; }
@media (prefers-color-scheme: dark) { :root { --hl:#2f2a22; } }"""


def _cands_html(rows: list[dict], lang: str, placed_n: int) -> str:
    from html import escape as e
    if not rows:
        return ""
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
        out.append(f'<li class="{"in" if r["in"] else ""}"><span class="mark">{"✓" if r["in"] else ""}</span>{title}'
                   f'{(" — " + e(meta)) if meta else ""} {score} {src}{why}</li>')
    out.append("</ul></details>")
    return "\n".join(out)


def render_editor_html(result: dict, p: Pools, w: Window, lang: str, editor: dict, lists: dict) -> str:
    """Та же вёрстка, что у читательской версии, плюс под каждой рубрикой — все кандидаты (в выпуске отмечены, у
    остальных — причина), рубрика «Не попало никуда» и блок «Для редактора» в конце."""
    from html import escape as e
    L = layout(result, p, w, lang)
    more = "More" if lang == "en" else "Подробнее"
    badge = "editor's version" if lang == "en" else "редакторская версия"
    body = [f'<h1>{e(L["title"])}<span class="badge">{badge}</span></h1>', f'<p class="sub">{e(L["subtitle"])}</p>',
            f'<p class="intro">{e(L["intro"])}</p>']
    shown = {sec["rubric"]: sec for sec in L["sections"]}
    for rub in w.rubrics():
        rows = lists.get(rub, [])
        sec = shown.get(rub)
        if not sec and not rows:
            continue
        placed = sum(r["in"] for r in rows)
        if sec:
            body.append(f'<section><h2>{e(sec["title"])}</h2>')
            if sec["intro"]:
                body.append(f'<p class="secintro">{e(sec["intro"])}</p>')
            for g in sec["groups"]:
                if g["title"]:
                    body.append(f'<h3>{e(g["title"])}</h3>')
                for it in g["items"]:
                    body.append(item_html(it, more))
        else:
            title = "Theme of the week" if rub == "theme" and lang == "en" else \
                "Тема недели" if rub == "theme" else rubric_title(rub, w, lang)
            hidden = "not in the issue" if lang == "en" else "в выпуск не вошла"
            body.append(f'<section class="stub"><h2>{e(title)} — {hidden}</h2>')
        body.append(_cands_html(rows, lang, placed))
        body.append("</section>")
    nowhere = lists.get("nowhere", [])
    body.append(f'<section><h2>{"Didn’t fit anywhere" if lang == "en" else "Не попало никуда"}</h2>')
    body.append(_cands_html(nowhere, lang, 0).replace(
        "Все события рубрики", "События окна вне рубрик").replace("All candidates of this rubric", "Events of the window outside all rubrics"))
    body.append("</section>")
    body.append(f'<section class="editor"><h2>{"For the editor" if lang == "en" else "Для редактора"}</h2>')
    for title, entries in editor[lang]:
        body.append(f"<h3>{e(title)}</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in (entries or ["—"])) + "</ul>")
    body.append("</section>")
    return READER_HTML.format(lang=lang, title=e(L["title"] + (" — editor" if lang == "en" else " — редактор")),
                              body="\n".join(body), extra_css=EDITOR_CSS)
