"""Схема events.db (SQLite). Сырые записи источников хранятся вечно; события не удаляются."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "events.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

-- Прогоны сборщика (по источникам).
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT NOT NULL,           -- метка прогона (ISO-время начала)
    source_id   TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    items       INTEGER,
    error       TEXT,
    PRIMARY KEY (run_id, source_id)
);

-- Записи источников как есть (одна строка = одно событие/статья/магазин у одного источника).
CREATE TABLE IF NOT EXISTS raw_items (
    raw_id        INTEGER PRIMARY KEY,
    source_id     TEXT NOT NULL,
    item_key      TEXT NOT NULL,         -- external_id | url | title|start
    kind          TEXT NOT NULL,         -- event | article | store
    title         TEXT NOT NULL,
    url           TEXT,
    start         TEXT, "end" TEXT, all_day INTEGER,
    venue         TEXT, address TEXT, postcode TEXT, lat REAL, lon REAL,
    price         TEXT, status TEXT, organizer TEXT, categories TEXT,
    summary       TEXT, published TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    disappeared_at TEXT,                 -- пропало из источника до своей даты
    event_id      INTEGER REFERENCES events(event_id),
    UNIQUE (source_id, item_key)
);

-- Площадки и их синонимы.
CREATE TABLE IF NOT EXISTS venues (
    venue_id  INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    address   TEXT, postcode TEXT, lat REAL, lon REAL,
    zone      TEXT,                      -- центр | до 30 мин | до часа | Кембриджшир, дальше часа | out_of_zone
    origin    TEXT                       -- events | manual | postcodes.io
);
CREATE TABLE IF NOT EXISTS venue_aliases (
    alias     TEXT PRIMARY KEY,          -- нормализованное название
    venue_id  INTEGER NOT NULL REFERENCES venues(venue_id)
);

-- Канонические события (после дедупликации).
CREATE TABLE IF NOT EXISTS events (
    event_id     INTEGER PRIMARY KEY,
    title        TEXT NOT NULL,
    norm_title   TEXT NOT NULL,
    date_start   TEXT NOT NULL, time_start TEXT,
    date_end     TEXT, time_end TEXT,
    venue_id     INTEGER REFERENCES venues(venue_id),
    venue_name   TEXT, address TEXT, postcode TEXT, lat REAL, lon REAL, zone TEXT,
    price_from   REAL,                   -- 0 = бесплатно
    price_text   TEXT,
    status       TEXT NOT NULL,          -- scheduled | announced | on_sale | sold_out | postponed | cancelled | disappeared | past
    on_sale_date TEXT,
    source_type  TEXT NOT NULL DEFAULT 'feed',   -- feed | article | recurring
    url          TEXT,                   -- основная ссылка на первоисточник
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_date ON events(date_start);

CREATE TABLE IF NOT EXISTS event_sources (
    event_id  INTEGER NOT NULL REFERENCES events(event_id),
    source_id TEXT NOT NULL,
    url       TEXT,
    raw_id    INTEGER REFERENCES raw_items(raw_id),
    article_id INTEGER REFERENCES articles(article_id),
    PRIMARY KEY (event_id, source_id, url)
);

CREATE TABLE IF NOT EXISTS status_history (
    event_id   INTEGER NOT NULL REFERENCES events(event_id),
    status     TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    source_id  TEXT,
    note       TEXT
);

-- Статьи из RSS и результат извлечения.
CREATE TABLE IF NOT EXISTS articles (
    article_id  INTEGER PRIMARY KEY,
    source_id   TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    published   TEXT,
    summary     TEXT,
    first_seen_at TEXT NOT NULL,
    extract_status TEXT NOT NULL DEFAULT 'pending',  -- pending | useful | empty | error | keyword | skipped | duplicate | filtered (Newsquest, до модели)
    extracted_at TEXT,
    model       TEXT,
    result_json TEXT                                 -- ответ модели (структура, не текст статьи)
);

-- «Новое в городе».
CREATE TABLE IF NOT EXISTS venue_news (
    news_id     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT,                    -- ресторан | кафе | бар | магазин | другое
    address     TEXT, postcode TEXT,
    stage       TEXT NOT NULL,           -- coming_soon | opened | closed
    date        TEXT,                    -- ожидаемая или фактическая
    source_id   TEXT NOT NULL,
    source_type TEXT NOT NULL,           -- article | store_list | rss_title (без LLM, требует проверки)
    url         TEXT,
    article_id  INTEGER REFERENCES articles(article_id),
    note        TEXT,
    first_seen_at TEXT NOT NULL,
    UNIQUE (name, stage, source_id)
);

-- Анонсы ключевых фактов из статей, которые не стали отдельным событием (отмена, старт продаж).
CREATE TABLE IF NOT EXISTS event_updates (
    update_id   INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,           -- cancelled | postponed | on_sale
    event_name  TEXT NOT NULL,
    date        TEXT, new_date TEXT, on_sale_date TEXT,
    event_id    INTEGER REFERENCES events(event_id),
    article_id  INTEGER REFERENCES articles(article_id),
    source_id   TEXT, url TEXT,
    note        TEXT,
    first_seen_at TEXT NOT NULL
);

-- Ежегодные события.
CREATE TABLE IF NOT EXISTS recurring_events (
    rec_id        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    expected_month TEXT NOT NULL,
    official_url  TEXT,
    check_method  TEXT NOT NULL,         -- page | news | manual
    patterns      TEXT,                  -- JSON: ключевые слова для поиска в событиях/статьях
    last_checked_at TEXT,
    found_date    TEXT,                  -- начало текущего цикла (YYYY-MM-DD)
    found_date_end TEXT,                 -- окончание (многодневные: Straw Bear, Folk Festival)
    found_source  TEXT,
    event_id      INTEGER REFERENCES events(event_id),
    note          TEXT
);

-- Кэш страниц событий для инкрементального сбора (без HTML — только извлечённые поля).
CREATE TABLE IF NOT EXISTS detail_pages (
    url        TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    fields     TEXT                      -- JSON RawEvent-полей или NULL, если JSON-LD нет
);

-- Кэш postcodes.io: координаты и административная принадлежность (для зоны «Кембриджшир, дальше часа»).
CREATE TABLE IF NOT EXISTS postcodes (
    postcode       TEXT PRIMARY KEY,     -- как вернул postcodes.io («CB2 1RB»)
    lat REAL, lon REAL,
    admin_county   TEXT,                 -- Cambridgeshire | Suffolk | … (у Питерборо — NULL)
    admin_district TEXT,                 -- Peterborough | Fenland | …
    fetched_at     TEXT NOT NULL
);

-- Простые настройки/состояние скриптов (архив Foodies и т.п.).
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Населённые пункты postcodes.io /places (координаты для площадок без postcode).
CREATE TABLE IF NOT EXISTS places (
    query      TEXT PRIMARY KEY,
    name       TEXT, lat REAL, lon REAL,
    county     TEXT, district TEXT,
    fetched_at TEXT NOT NULL
);

-- Поиск адреса площадки в тексте страницы события или статьи (pipeline/locate.py).
CREATE TABLE IF NOT EXISTS venue_lookups (
    event_id   INTEGER PRIMARY KEY REFERENCES events(event_id),
    url        TEXT,
    result     TEXT,                     -- JSON ответа модели
    resolved   TEXT,                     -- postcode | place | city | none
    checked_at TEXT NOT NULL
);

-- Внешние сигналы известности (Wikipedia), кэш.
CREATE TABLE IF NOT EXISTS wiki_cache (
    title      TEXT PRIMARY KEY,         -- запрошенное название статьи
    exists_    INTEGER,
    resolved   TEXT,                     -- итоговое название после редиректа
    views_30d  INTEGER,
    fetched_at TEXT NOT NULL
);

-- Оценка известности моделью (сигнал важности), кэш по событию.
CREATE TABLE IF NOT EXISTS fame_cache (
    event_id   INTEGER PRIMARY KEY REFERENCES events(event_id),
    title      TEXT,                     -- название на момент оценки (сменилось — оценить заново)
    result     TEXT NOT NULL,            -- JSON ответа модели
    model      TEXT, rated_at TEXT NOT NULL
);

-- Расход Claude API.
CREATE TABLE IF NOT EXISTS llm_usage (
    called_at   TEXT NOT NULL,
    purpose     TEXT NOT NULL,
    model       TEXT NOT NULL,
    article_id  INTEGER,
    input_tokens INTEGER, output_tokens INTEGER,
    cost_usd    REAL
);

-- ИИ-запреты в robots.txt источников статей (pipeline/ai_policy.py)
CREATE TABLE IF NOT EXISTS source_ai_policy (
    source_id   TEXT PRIMARY KEY,
    host        TEXT,
    ai_disallow INTEGER,
    agents      TEXT,                   -- ИИ-агенты Anthropic, которым закрыт доступ
    checked_at  TEXT
);

-- пакеты Message Batches API (извлечение из статей): результат забирается, когда пакет обработан
CREATE TABLE IF NOT EXISTS llm_batches (
    batch_id    TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    purpose     TEXT NOT NULL,
    items       INTEGER,
    text_sources TEXT,                  -- JSON article_id → page | rss
    collected_at TEXT
);
"""


# Колонки, добавленные после создания базы: (таблица, колонка, тип).
MIGRATIONS = [
    ("recurring_events", "found_date_end", "TEXT"),
    ("recurring_events", "tickets", "INTEGER"),       # 1 — билеты/регистрация (событие announced), 0 — scheduled
    ("recurring_events", "page_date", "TEXT"),        # end — единственная дата на странице означает окончание
    ("recurring_events", "manual_start", "TEXT"),     # дата, внесённая владельцем проекта (важнее найденной)
    ("recurring_events", "manual_end", "TEXT"),
    ("recurring_events", "venue", "TEXT"),            # место проведения — для зоны события
    ("recurring_events", "postcode", "TEXT"),
    ("venue_news", "date_basis", "TEXT"),             # stated | publication_date (дата статьи о свежем открытии)
    ("articles", "text_source", "TEXT"),              # page | rss | feed — что ушло в модель
    ("events", "address_unknown", "INTEGER"),         # 1 — город Cambridge без адреса, зона «центр» условно
    ("events", "multi_venue", "INTEGER"),             # 1 — фестиваль на разных площадках («разные площадки, Кембридж»)
    ("events", "importance_score", "REAL"),           # 1–10, pipeline/importance.py
    ("events", "importance_reason", "TEXT"),
    ("events", "importance_sig", "TEXT"),             # сигнатура входных данных оценки (пересчёт только при изменении)
    ("venues", "capacity", "INTEGER"),                # вместимость (вручную, data/venue_capacity.json)
    ("venues", "precision", "TEXT"),                  # postcode | place (населённый пункт) | city (только «Кембридж»)
]


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    for table, col, typ in MIGRATIONS:
        if col not in {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    return con
