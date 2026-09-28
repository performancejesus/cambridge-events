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

from .db import ROOT
from .normalize import norm_title, norm_venue, title_similarity

LISTED_ZONES = {"центр", "до 30 мин", "до часа", "Кембриджшир, дальше часа"}
OUT_OF_TOWN = {"до 30 мин", "до часа"}
NO_VENUE_RE = re.compile(r"^\s*(various|multiple locations|location to be announced|tba|tbc|online)\b", re.I)
TBC_RE = re.compile(r"title to be confirmed", re.I)
# Матчи из загруженного целиком календаря сезона — не «новые анонсы» (бриф, этап 4).
SEASON_CALENDAR = {"S018", "S123"}
# Статусы ADC и Cambridge United без данных о продаже: в выпуске — обычные события, не «анонсы».
NO_SALE_DATA = {"S018", "S042", "S123"}
ANNOUNCE_DAYS = 21          # «объявлено недавно»: статья или старт продаж не старше стольких дней
VENUE_NEWS_DAYS = 90

# Рубрики после «Темы недели» и «Главного на выходные» (их по одной на каждые выходные периода).
FIXED_RUBRICS = ["weekdays", "free", "kids", "sport", "out_of_town", "county", "new_announcements", "tickets",
                 "cancelled", "new_in_town"]
RUBRIC_TITLES = {
    "en": {"theme": "Theme of the week: {theme}", "weekend": "The weekend: {weekend}",
           "weekdays": "Weekdays: concerts, theatre, comedy", "free": "Free", "kids": "With kids", "sport": "Sport",
           "out_of_town": "Out of town (within an hour)", "county": "Around the county",
           "new_announcements": "Just announced", "tickets": "Get your tickets",
           "cancelled": "Cancelled and postponed", "new_in_town": "New in town"},
    "ru": {"theme": "Тема недели: {theme}", "weekend": "Главное на выходные {weekend}",
           "weekdays": "На неделе: концерты, театр, комедия", "free": "Бесплатно", "kids": "С детьми", "sport": "Спорт",
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
OUT_OF_TOWN_MIN = 3.0       # «За городом»: слабее — только если нет альтернатив (правки по v2)
WINDOW_DAYS = 10            # период выпуска = дата отправки … +10 дней (правки по v2)
# «С детьми» — только если дети явно названы в данных (решение после этапа 4).
KIDS_RE = re.compile(r"\b(family[- ]friendly|for (all the |the whole )?famil(y|ies)|famil(y|ies) (fun|day|event|show|"
                     r"activit\w*|workshop|ticket)s?|all the family|whole family|kids|children'?s?|toddlers?|babies|"
                     r"baby|half[- ]term|ages? \d|aged \d|years? \d+\s*[-–]\s*\d+|under[- ]?\d+s)\b", re.I)
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
    return " | ".join(u[:300] for u in uniq)[:600]


def _categories(con, event_id: int) -> list[str]:
    cats = set()
    for (c,) in con.execute("SELECT categories FROM raw_items WHERE event_id=?", (event_id,)):
        cats.update(json.loads(c or "[]"))
    return sorted(cats)[:6]


def _merge_notes() -> dict[tuple[str, str], str]:
    rules = json.loads(MERGES.read_text()) if MERGES.exists() else []
    return {(r["keep"]["date"], r["keep"]["title"]): r["note"] for r in rules}


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
        "kids_tag": bool(KIDS_RE.search(" ".join([e["title"], summary] + cats))),
        "free_tag": e["price_from"] == 0,
    }
    note = _merge_notes().get((e["date_start"], e["title"]))
    if note:
        facts["editor_note"] = note
    return facts


def _exclusion(e: sqlite3.Row) -> str | None:
    if TBC_RE.search(e["title"]):
        return "лекции talks.cam с «Title to be confirmed»"
    if (not e["venue_name"] or NO_VENUE_RE.match(e["venue_name"])) and not e["multi_venue"]:
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
        p.candidates[f"E{first['event_id']}"] = facts
    _find_duplicates(p, excluded_rows)
    _links(p)
    _announcements(con, w, p)
    _tickets(con, w, p)
    _cancellations(con, w, p)
    _venue_news(con, w, p)
    return p


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
        facts |= {"kind": "tickets", "on_sale_date": u["on_sale_date"], "url": u["url"],
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


def model_view(p: Pools) -> list[dict]:
    """Кандидаты для модели: только нужные поля, без пустых."""
    out = []
    for cid, c in p.candidates.items():
        item = {"id": cid} | {k: v for k, v in c.items()
                              if k not in ("url", "event_ids", "importance_reason") and v not in (None, "", [], False)}
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


def render(result: dict, p: Pools, w: Window, lang: str, editor: dict) -> str:
    weekends = (" and " if lang == "en" else " и ").join(_range(a, b, lang) for a, b in w.weekends)
    period = f"{_day(w.start, lang, weekday=False)} – {_day(w.end, lang, weekday=False)}"
    if lang == "en":
        head = [f"# What's on in Cambridge — {w.issue.day} {MONTHS_EN[w.issue.month - 1]} {w.issue.year}", "",
                f"*Events {period} · weekends: {weekends}*", ""]
    else:
        head = [f"# Что происходит в Кембридже — {w.issue.day} {MONTHS_RU[w.issue.month - 1]} {w.issue.year}", "",
                f"*События {period} · выходные: {weekends}*", ""]
    lines = head + [result[f"intro_{lang}"], ""]
    sections = {s["rubric"]: s["items"] for s in result["sections"]}
    more = "More" if lang == "en" else "Подробнее"
    for rub in w.rubrics():
        items = sorted(sections.get(rub) or [], key=lambda it: -importance_of(p, it))
        if not items:
            continue  # пустые рубрики не выводим (правки по v2)
        lines += [f"## {rubric_title(rub, w, lang, result.get(f'theme_title_{lang}', ''))}", ""]
        if rub == "theme" and result.get(f"theme_intro_{lang}"):
            lines += [result[f"theme_intro_{lang}"], ""]
        for it in items:
            c = p.candidates[it["ids"][0]]
            evs = [p.candidates[i] for i in it["ids"] if p.candidates[i]["kind"] == c["kind"] == "event"]
            if len(evs) > 1:  # два дня одной выставки на разных площадках и т.п.
                c = c | {"dates": sorted({x for e in evs for x in e["dates"]})}
            price = "" if c["kind"] == "venue_news" else it[f"price_{lang}"]
            meta = " · ".join(x for x in (when(c, w, lang), it[f"where_{lang}"], price) if x)
            blurb = it[f"blurb_{lang}"].strip()
            lines += [f"**{it[f'title_{lang}']}** — {meta}  ",
                      (f"{blurb} " if blurb else "") + f"[{more} →]({c['url']})", ""]
    lines += ["---", "", "## For the editor" if lang == "en" else "## Для редактора", ""]
    for title, entries in editor[lang]:
        lines += [f"**{title}**", ""]
        lines += [f"- {x}" for x in entries] if entries else ["- —"]
        lines += [""]
    return "\n".join(lines).rstrip() + "\n"
