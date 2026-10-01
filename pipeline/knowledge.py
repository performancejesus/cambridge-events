"""Этап 7e: база знаний о городе, а не только конвейер рассылки (бриф, «Что строим», решение 30.09).

Сущности базы:
- события — `events` (+ `event_sources`, `status_history`); прошедшие не удаляются, а получают статус `past`;
- программы — `kids_programmes` (детские: каникулярные лагеря и регулярные секции) и `courses` (курсы и мастер-классы
  для взрослых, этап 7e), общий вид — представление `programmes`;
- места — `venues` (площадки и достопримечательности) с постоянной информацией (этап 7e: вид места, город, сайт,
  часы работы, для кого, цены, контакты — колонки `kind`, `town`, `website`, `opening_hours`, …);
- организации — `organizations` (клубы, организаторы, провайдеры программ, операторы площадок; этап 7e);
- открытия — `venue_news`; ежегодные события — `recurring_events`.

У каждой записи — `last_verified_at` (когда наш бот последний раз видел запись у источника) и источник. Постоянные
записи (места, организации, программы) перепроверяются по расписанию: раз в месяц и к началу триместров
(`next_check_at`, `due`). Миграция только добавляет колонки, таблицы и представления — ничего не удаляет и не
переименовывает; снимок базы до миграции обязателен (бриф).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

from .db import ROOT

RECHECK_DAYS = 30            # постоянные записи — раз в месяц
TERM_LEAD_DAYS = 14          # и за две недели до начала триместра (сентябрь, январь, апрель)

COLUMNS = [
    # события: когда источник последний раз подтвердил событие (сбор или перепроверка страницы)
    ("events", "last_verified_at", "TEXT"),
    # места — постоянная информация (для будущего сайта)
    ("venues", "kind", "TEXT"),             # museum | estate | farm | park | theatre | cinema | music | college | sport | club | school | other
    ("venues", "town", "TEXT"),
    ("venues", "website", "TEXT"),
    ("venues", "opening_hours", "TEXT"),    # как у источника: «Tue–Sun 10:00–17:00»
    ("venues", "audience", "TEXT"),         # для кого: семьи, взрослые, все
    ("venues", "prices", "TEXT"),           # вход: «free», «£12 adult, £6 child»
    ("venues", "phone", "TEXT"),
    ("venues", "email", "TEXT"),
    ("venues", "description", "TEXT"),      # одна фраза своими словами (не копия)
    ("venues", "org_id", "INTEGER"),        # оператор места (organizations)
    ("venues", "profile_source", "TEXT"),   # откуда постоянная информация (URL)
    ("venues", "last_verified_at", "TEXT"),
    ("venues", "next_check_at", "TEXT"),
    # детские программы: статус записи (не удаляем — архив), набор, перепроверка
    ("kids_programmes", "status", "TEXT"),  # active | past | gone (пропала со страницы провайдера)
    ("kids_programmes", "last_seen_at", "TEXT"),
    ("kids_programmes", "gone_at", "TEXT"),
    ("kids_programmes", "last_verified_at", "TEXT"),
    ("kids_programmes", "next_check_at", "TEXT"),
    ("kids_programmes", "org_id", "INTEGER"),
    ("kids_programmes", "category", "TEXT"),     # football | netball | swimming | gymnastics | dance | chess | arts | …
    ("kids_programmes", "recruiting", "TEXT"),   # этап 7e: open (набор объявлен) | waitlist | closed | unknown
    ("kids_programmes", "trial_free", "INTEGER"),
    ("kids_programmes", "recruiting_note", "TEXT"),   # фраза со страницы: «new players welcome», «free taster session»
    # открытия и ежегодные события
    ("venue_news", "last_verified_at", "TEXT"),
    ("recurring_events", "last_verified_at", "TEXT"),
    ("recurring_events", "tags", "TEXT"),        # JSON: ["quirky"] — необычные местные традиции (этап 7e)
    ("recurring_events", "description", "TEXT"),  # коротко, что это за традиция (для «Главного на выходные»)
    ("recurring_events", "status_note", "TEXT"),  # не проводится / раз в два года / нет в программе этого года
    ("recurring_events", "on_sale_note", "TEXT"), # где подтверждена продажа билетов текущего цикла
    # кинотеатры: не удаляем фильмы, которые сошли с экрана (архив), а отмечаем
    ("regional_showings", "last_seen_at", "TEXT"),
    ("regional_showings", "gone_at", "TEXT"),
    ("cinema_showings", "gone_at", "TEXT"),
]

TABLES = """
-- Организации: клубы, организаторы, провайдеры программ, операторы площадок, источники (этап 7e).
CREATE TABLE IF NOT EXISTS organizations (
    org_id      INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT,                 -- venue_operator | organiser | kids_provider | course_provider | sports_club | college | council | media | aggregator
    host        TEXT UNIQUE,          -- домен сайта (ключ сопоставления)
    website     TEXT,
    town        TEXT,
    description TEXT,
    source_id   TEXT,                 -- ID реестра, если организация — источник
    source_url  TEXT,                 -- откуда сведения
    first_seen_at TEXT NOT NULL,
    last_verified_at TEXT,
    next_check_at TEXT,
    note        TEXT
);

-- Курсы и мастер-классы для взрослых (этап 7e, рубрика «Научиться»). Разовые занятия с датой — ещё и события.
CREATE TABLE IF NOT EXISTS courses (
    course_id   TEXT PRIMARY KEY,     -- K:<host>:<sha8>
    org_id      INTEGER REFERENCES organizations(org_id),
    provider    TEXT, provider_host TEXT,
    title       TEXT NOT NULL,
    category    TEXT,                 -- cookery | wine | pottery | drawing | crafts | photography | dance | language | music | gardening | other
    kind        TEXT,                 -- workshop (разовое занятие) | course (несколько занятий) | tasting
    level       TEXT,                 -- beginners | all | improvers
    date_start  TEXT, date_end TEXT, time_start TEXT,
    sessions    INTEGER,              -- число занятий курса
    days        TEXT, hours TEXT,
    price       TEXT, price_from REAL,
    venue       TEXT, address TEXT, postcode TEXT, zone TEXT,
    places      TEXT,                 -- open | few_left | full | unknown
    url         TEXT,
    source_id   TEXT,                 -- ID реестра
    evidence    TEXT,                 -- фраза со страницы (для проверки), не публикуется
    status      TEXT NOT NULL DEFAULT 'active',   -- active | past | gone
    event_id    INTEGER REFERENCES events(event_id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT,
    last_verified_at TEXT,
    next_check_at TEXT,
    gone_at     TEXT
);

-- Общий вид программ: детские (каникулы, секции) и взрослые (курсы).
CREATE VIEW IF NOT EXISTS programmes AS
    SELECT prog_id AS programme_id, 'kids' AS audience_group, coalesce(kind, 'holiday') AS kind, provider, provider_host,
           org_id, title, category, ages, date_start, date_end, days, hours, price, venue, address, postcode, zone,
           places, recruiting, url, coalesce(status, 'active') AS status, first_seen_at, last_verified_at, next_check_at
      FROM kids_programmes
    UNION ALL
    SELECT course_id, 'adults', kind, provider, provider_host, org_id, title, category, 'adults', date_start, date_end,
           days, hours, price, venue, address, postcode, zone, places, NULL, url, status, first_seen_at,
           last_verified_at, next_check_at
      FROM courses;
"""

# Курированные места (этапы 6–7d): вид места — для постоянной информации и будущего сайта.
PLACE_KINDS = {
    "museum": ["Fitzwilliam Museum", "Kettle's Yard", "Museum of Zoology", "Whipple Museum", "Sedgwick Museum",
               "Museum of Archaeology and Anthropology", "Polar Museum", "Museum of Classical Archaeology",
               "Museum of Cambridge", "Centre for Computing History", "Cambridge Museum of Technology", "Ely Museum",
               "Royston Museum", "Oliver Cromwell's House", "Lynn Museum", "True's Yard", "IWM Duxford",
               "David Parr House", "Cambridge Science Centre", "Kettle's Yard"],
    "estate": ["Wimpole Estate", "Anglesey Abbey", "Wicken Fen", "Audley End House", "Wandlebury",
               "Cambridge University Botanic Garden", "Milton Country Park", "Hinchingbrooke Country Park",
               "Ferry Meadows", "Ely Cathedral", "Leper Chapel"],
    "farm": ["Bury Lane Farm Shop", "Gog Magog Hills Farm Shop", "Shepreth Wildlife Park", "Linton Zoo",
             "Hamerton Zoo Park", "Wimpole Home Farm"],
    "theatre": ["Cambridge Arts Theatre", "ADC Theatre", "Cambridge Corn Exchange", "Cambridge Junction",
                "Mumford Theatre", "Theatre Royal Bury St Edmunds", "Saffron Hall", "The Maltings", "Corn Exchange King's Lynn",
                "West Road Concert Hall", "Key Theatre", "The Apex"],
    "cinema": ["Arts Picturehouse", "Light Cinema", "Vue Cambridge", "The Light Wisbech", "Royal Cinema St Ives",
               "Screen St Ives", "Majestic Cinema", "Peterborough Arts Cinema", "The Luxe Cinema Wisbech",
               "Haverhill Arts Centre", "Babylon Cinema", "Abbeygate Cinema", "Saffron Screen"],
    "sport": ["Abbey Stadium", "Newmarket Racecourse", "Huntingdon Racecourse", "Grange Road", "Weston Homes Stadium",
              "Parkside Pools", "Abbey Leisure Complex"],
}


def migrate(con: sqlite3.Connection) -> dict:
    """Добавить колонки, таблицы и представление (идемпотентно) и заполнить новые поля из имеющихся данных."""
    from .kids_collect import init as kids_init
    from collectors.sources.stage7d import REGIONAL_SQL
    from .cinema import SCHEMA as CINEMA_SCHEMA
    kids_init(con)
    con.execute(REGIONAL_SQL)
    con.executescript(CINEMA_SCHEMA) if ";" in CINEMA_SCHEMA else con.execute(CINEMA_SCHEMA)
    added = []
    for table, col, typ in COLUMNS:
        if col not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            added.append(f"{table}.{col}")
    con.executescript(TABLES)
    st = {"columns_added": added}
    st |= backfill(con)
    con.commit()
    return st


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def backfill(con: sqlite3.Connection, today: date | None = None) -> dict:
    """Заполнить last_verified_at, статусы архива и расписание перепроверки по уже имеющимся данным."""
    today = today or date.today()
    t = today.isoformat()
    st = {}
    # события: последний раз видели у источника; перепроверка страницы (page_status) — тоже подтверждение
    has_ps = con.execute("SELECT 1 FROM sqlite_master WHERE name='page_status'").fetchone()
    st["events"] = con.execute(f"""UPDATE events SET last_verified_at = max(last_seen_at, coalesce(
        {"(SELECT max(checked_at) FROM page_status p WHERE p.event_id = events.event_id)" if has_ps else "NULL"}, ''))
        WHERE last_verified_at IS NULL OR last_verified_at < last_seen_at""").rowcount
    # детские программы: прошедшие — past, остальные — active; last_verified_at = последняя проверка на сайте
    con.execute("UPDATE kids_programmes SET last_seen_at = coalesce(last_seen_at, checked_at)")
    con.execute("UPDATE kids_programmes SET last_verified_at = coalesce(last_verified_at, checked_at)")
    st["kids_past"] = con.execute("""UPDATE kids_programmes SET status='past' WHERE coalesce(status,'active')='active'
        AND coalesce(kind,'holiday')='holiday' AND date_end IS NOT NULL AND date_end < ?""", (t,)).rowcount
    con.execute("UPDATE kids_programmes SET status='active' WHERE status IS NULL")
    con.execute("UPDATE venue_news SET last_verified_at = coalesce(last_verified_at, first_seen_at)")
    con.execute("UPDATE recurring_events SET last_verified_at = coalesce(last_verified_at, last_checked_at)")
    con.execute("UPDATE regional_showings SET last_seen_at = coalesce(last_seen_at, checked_at)")
    st["courses_past"] = con.execute("""UPDATE courses SET status='past' WHERE status='active'
        AND coalesce(date_end, date_start) < ?""", (t,)).rowcount
    st |= seed_organizations(con)
    st |= seed_places(con)
    st["schedule"] = schedule(con, today)
    return st


# --- организации ---

def _host(url: str | None) -> str | None:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower().removeprefix("www.") if m else None


ORG_KIND_BY_CATEGORY = {"Сквозные агрегаторы": "aggregator", "Агрегатор": "aggregator", "СМИ": "media",
                        "Газета": "media", "Совет": "council", "Колледж": "college", "Спорт": "sports_club"}


def upsert_org(con: sqlite3.Connection, name: str, url: str | None, kind: str, source_id: str | None = None,
               town: str | None = None, source_url: str | None = None, verified_at: str | None = None,
               note: str | None = None) -> int | None:
    host = _host(url)
    if not host:
        return None
    row = con.execute("SELECT org_id, kind FROM organizations WHERE host=?", (host,)).fetchone()
    if row:
        con.execute("""UPDATE organizations SET kind = coalesce(kind, ?), source_id = coalesce(source_id, ?),
            town = coalesce(town, ?), last_verified_at = max(coalesce(last_verified_at, ''), coalesce(?, ''))
            WHERE org_id=?""", (kind, source_id, town, verified_at, row[0]))
        return row[0]
    cur = con.execute("""INSERT INTO organizations(name, kind, host, website, town, source_id, source_url, first_seen_at,
        last_verified_at, note) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                      (name, kind, host, f"https://{host}/", town, source_id, source_url or url, _now(), verified_at, note))
    return cur.lastrowid


def _registry_rows() -> list[dict]:
    """Последний реестр источников: ID, название, тип, URL, дата проверки."""
    import glob
    import openpyxl
    path = sorted(glob.glob(str(ROOT / "data" / "cambridge_event_sources_v0.*.xlsx")),
                  key=lambda p: [int(x) for x in re.findall(r"v0\.(\d+)", p)])[-1]
    ws = openpyxl.load_workbook(path, read_only=True)["Источники"]
    rows = list(ws.iter_rows(values_only=True))
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:] if r and r[0]]


def _registry_kind(r: dict) -> str:
    typ = f"{r.get('Категория') or ''} {r.get('Тип источника') or ''}".lower()
    for key, kind in (("агрегатор", "aggregator"), ("газет", "media"), ("сми", "media"), ("rss", "media"),
                      ("совет", "council"), ("council", "council"), ("колледж", "college"), ("college", "college"),
                      ("спорт", "sports_club"), ("клуб", "sports_club"), ("туристич", "tourism"),
                      ("музе", "venue_operator"), ("площадк", "venue_operator"), ("театр", "venue_operator"),
                      ("кино", "venue_operator")):
        if key in typ:
            return kind
    return "organiser"


def seed_organizations(con: sqlite3.Connection) -> dict:
    """Организации из реестра источников, провайдеров детских программ и курсов; связь программ с организацией."""
    n0 = con.execute("SELECT count(*) FROM organizations").fetchone()[0]
    try:
        for r in _registry_rows():
            upsert_org(con, r.get("Источник") or r["ID"], r.get("URL"), _registry_kind(r), source_id=r["ID"],
                       verified_at=str(r.get("Проверено") or "") or None)
    except Exception:  # noqa: BLE001 — нет реестра (тесты на пустой базе)
        pass
    for fn in ("kids_providers.json", "kids_providers_extra.json"):
        p = ROOT / "data" / fn
        if p.exists():
            for x in json.loads(p.read_text())["providers"]:
                upsert_org(con, x["provider"], f"https://{x['host']}/", "kids_provider",
                           town=", ".join(x.get("towns") or []) or None)
    for r in con.execute("SELECT DISTINCT provider, provider_host, max(checked_at) FROM kids_programmes "
                         "WHERE provider_host IS NOT NULL GROUP BY provider_host").fetchall():
        upsert_org(con, r[0] or r[1], f"https://{r[1]}/", "kids_provider", verified_at=r[2])
    for r in con.execute("SELECT DISTINCT provider, provider_host, max(last_verified_at) FROM courses "
                         "WHERE provider_host IS NOT NULL GROUP BY provider_host").fetchall():
        upsert_org(con, r[0] or r[1], f"https://{r[1]}/", "course_provider", verified_at=r[2])
    con.execute("""UPDATE kids_programmes SET org_id = (SELECT org_id FROM organizations o WHERE o.host = provider_host)
                   WHERE org_id IS NULL""")
    con.execute("""UPDATE courses SET org_id = (SELECT org_id FROM organizations o WHERE o.host = provider_host)
                   WHERE org_id IS NULL""")
    return {"organizations_new": con.execute("SELECT count(*) FROM organizations").fetchone()[0] - n0}


# --- места ---

def seed_places(con: sqlite3.Connection) -> dict:
    """Вид места и город у курированных площадок справочника (по названию и синонимам)."""
    n = 0
    for kind, names in PLACE_KINDS.items():
        for name in names:
            like = f"%{name.lower().replace('’', chr(39))}%"
            n += con.execute("UPDATE venues SET kind=? WHERE kind IS NULL AND lower(replace(name, '’', ?)) LIKE ?",
                             (kind, "'", like)).rowcount
    # город — из адреса (последняя часть до postcode) для площадок с адресом
    for r in con.execute("SELECT venue_id, address FROM venues WHERE town IS NULL AND address IS NOT NULL").fetchall():
        parts = [p.strip() for p in re.sub(r"[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}", "", r[1]).split(",") if p.strip()]
        town = next((p for p in reversed(parts) if re.fullmatch(r"[A-Z][A-Za-z' .-]{2,30}", p)
                     and p.lower() not in ("uk", "united kingdom", "england", "cambridgeshire", "suffolk", "essex",
                                           "norfolk", "hertfordshire", "bedfordshire")), None)
        if town:
            con.execute("UPDATE venues SET town=? WHERE venue_id=?", (town, r[0]))
    # последнее подтверждение места — последнее событие, которое мы на нём видели
    con.execute("""UPDATE venues SET last_verified_at = (SELECT max(e.last_seen_at) FROM events e
                   WHERE e.venue_id = venues.venue_id) WHERE last_verified_at IS NULL OR kind IS NOT NULL""")
    return {"places_kind_set": n}


# --- расписание перепроверки ---

def term_starts(today: date | None = None) -> list[date]:
    """Начала триместров: день после рождественских, пасхальных и летних каникул (сентябрь, январь, апрель)."""
    from . import school_holidays
    out = []
    for h in school_holidays.load():
        if h["key"] in ("christmas", "easter", "summer"):
            out.append(date.fromisoformat(h["end"]) + timedelta(days=1))
    return sorted(out)


def next_check(last_verified: str | None, today: date | None = None) -> str:
    """Раз в месяц и за две недели до начала триместра — что раньше."""
    today = today or date.today()
    base = date.fromisoformat(last_verified[:10]) if last_verified else today
    monthly = base + timedelta(days=RECHECK_DAYS)
    term = next((t - timedelta(days=TERM_LEAD_DAYS) for t in term_starts()
                 if t - timedelta(days=TERM_LEAD_DAYS) > base), None)
    nxt = min(x for x in (monthly, term) if x)
    return max(nxt, today if not last_verified else nxt).isoformat()


PERMANENT = (  # таблица, ключ, условие «постоянная запись»
    ("venues", "venue_id", "kind IS NOT NULL"),
    ("organizations", "org_id", "kind IN ('kids_provider', 'course_provider', 'sports_club', 'venue_operator')"),
    ("kids_programmes", "prog_id", "coalesce(kind,'holiday')='regular' AND coalesce(status,'active')='active'"),
    ("courses", "course_id", "status='active'"),
)


def schedule(con: sqlite3.Connection, today: date | None = None) -> dict:
    out = {}
    for table, key, cond in PERMANENT:
        rows = con.execute(f"SELECT {key}, last_verified_at FROM {table} WHERE {cond}").fetchall()
        for r in rows:
            con.execute(f"UPDATE {table} SET next_check_at=? WHERE {key}=?", (next_check(r[1], today), r[0]))
        out[table] = len(rows)
    return out


def due(con: sqlite3.Connection, today: date | None = None) -> dict[str, list]:
    """Постоянные записи, которые пора перепроверить (next_check_at ≤ сегодня)."""
    t = (today or date.today()).isoformat()
    return {table: [r[0] for r in con.execute(
        f"SELECT {key} FROM {table} WHERE {cond} AND (next_check_at IS NULL OR next_check_at <= ?)", (t,))]
        for table, key, cond in PERMANENT}


# --- сводка для отчёта: сущность → записей → будущих / постоянных / архивных → самая дальняя дата ---

def summary(con: sqlite3.Connection, today: date | None = None) -> list[dict]:
    t = (today or date.today()).isoformat()
    q = lambda sql, *a: con.execute(sql, a).fetchone()   # noqa: E731
    rows = []
    e = q("""SELECT count(*), sum(coalesce(date_end, date_start) >= ? AND status NOT IN ('past')),
             sum(status='past' OR coalesce(date_end, date_start) < ?), max(coalesce(date_end, date_start)),
             sum(last_verified_at IS NOT NULL)
             FROM events WHERE coalesce(evergreen, 0) = 0 AND coalesce(roundup, 0) = 0""", t, t)
    rows.append({"entity": "События", "table": "events", "total": e[0], "future": e[1], "permanent": 0,
                 "archive": e[2], "farthest": e[3], "verified": e[4]})
    ev = q("SELECT count(*) FROM events WHERE coalesce(evergreen,0)=1")
    rows.append({"entity": "Постоянные предложения для туристов (evergreen)", "table": "events", "total": ev[0],
                 "future": 0, "permanent": ev[0], "archive": 0, "farthest": None, "verified": ev[0]})
    k = q("""SELECT count(*), sum(coalesce(kind,'holiday')='holiday' AND status='active' AND coalesce(date_end,date_start,'9') >= ?),
             sum(coalesce(kind,'holiday')='regular' AND status='active'), sum(status IN ('past','gone')),
             max(coalesce(date_end, date_start)), sum(last_verified_at IS NOT NULL) FROM kids_programmes""", t)
    rows.append({"entity": "Программы для детей (лагеря и секции)", "table": "kids_programmes", "total": k[0],
                 "future": k[1], "permanent": k[2], "archive": k[3], "farthest": k[4], "verified": k[5]})
    c = q("""SELECT count(*), sum(status='active' AND coalesce(date_end, date_start, '9') >= ?),
             sum(status='active' AND date_start IS NULL), sum(status IN ('past','gone')), max(coalesce(date_end, date_start)),
             sum(last_verified_at IS NOT NULL) FROM courses""", t)
    rows.append({"entity": "Курсы и мастер-классы для взрослых", "table": "courses", "total": c[0], "future": c[1],
                 "permanent": c[2], "archive": c[3], "farthest": c[4], "verified": c[5]})
    v = q("""SELECT count(*), sum(kind IS NOT NULL), sum(opening_hours IS NOT NULL), sum(last_verified_at IS NOT NULL)
             FROM venues""")
    rows.append({"entity": "Места (площадки и достопримечательности)", "table": "venues", "total": v[0], "future": None,
                 "permanent": v[1], "archive": None, "farthest": None, "verified": v[3], "with_hours": v[2]})
    o = q("SELECT count(*), sum(last_verified_at IS NOT NULL) FROM organizations")
    rows.append({"entity": "Организации", "table": "organizations", "total": o[0], "future": None, "permanent": o[0],
                 "archive": None, "farthest": None, "verified": o[1]})
    n = q("""SELECT count(*), sum(stage='coming_soon'), sum(stage='opened'), sum(stage='closed'), max(date),
             sum(last_verified_at IS NOT NULL) FROM venue_news""")
    rows.append({"entity": "Открытия и закрытия (venue_news)", "table": "venue_news", "total": n[0], "future": n[1],
                 "permanent": n[2], "archive": n[3], "farthest": n[4], "verified": n[5]})
    r = q("""SELECT count(*), sum(coalesce(manual_start, found_date) >= ?), sum(rec_id NOT LIKE 'H-%'),
             sum(coalesce(manual_end, found_date_end, manual_start, found_date) < ?),
             max(coalesce(manual_end, found_date_end, manual_start, found_date)), sum(last_verified_at IS NOT NULL)
             FROM recurring_events""", t, t)
    rows.append({"entity": "Ежегодные события (recurring_events, вкл. школьные каникулы)", "table": "recurring_events",
                 "total": r[0], "future": r[1], "permanent": r[2], "archive": r[3], "farthest": r[4], "verified": r[5]})
    s = q("""SELECT count(*), sum(last_date >= ? AND gone_at IS NULL), sum(last_date < ? OR gone_at IS NOT NULL),
             max(last_date) FROM regional_showings""", t, t)
    rows.append({"entity": "Фильмы в кинотеатрах зоны (regional_showings)", "table": "regional_showings",
                 "total": s[0], "future": s[1], "permanent": 0, "archive": s[2], "farthest": s[3], "verified": s[0]})
    return rows
