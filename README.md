# Cambridge Events

Сборщик событий Кембриджа и окрестностей (до ~1 часа езды) для еженедельной рассылки. Бриф: [`docs/BRIEF.md`](docs/BRIEF.md).

## Установка

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Этап 1 — проверка источников приоритета 1

```bash
python scripts/probe_sources.py            # все источники из data/p1_candidates.json (≈15 мин из-за пауз)
python scripts/probe_sources.py S047 S018  # только выбранные
python scripts/build_registry_v04.py       # data/cambridge_event_sources_v0.4.xlsx + docs/stage1_report.md
```

- `data/cambridge_event_sources_v0.3.xlsx` — исходный реестр, не изменяется.
- `data/p1_candidates.json` — кандидатные URL (официальный сайт, страница событий, возможные фиды).
- `data/p1_overrides.json` — ручные решения после разбора результатов.
- Контрольные события — `data/control_events.json` (они же на листе «Контрольные события» реестра).
- Скрипт соблюдает robots.txt, делает паузу 2 с между запросами к одному хосту и представляется как `CambridgeEventsBot/0.1`.

## Этап 2 — коллекторы

```bash
python scripts/run_collectors.py            # все коллекторы (≈10 мин из-за пауз)
python scripts/run_collectors.py S005 S047  # только выбранные
python scripts/stage2_report.py             # docs/stage2_report.md: счётчики и контрольные события
```

- `collectors/base.py` — общий интерфейс (`Collector.collect(http) -> list[RawEvent]`) и единый формат сырого события.
- `collectors/http.py` — вежливый клиент: robots.txt, пауза ≥ 2 с на хост (или Crawl-delay), бэк-офф на 429/503, опционально curl.
- `collectors/parsers.py` — iCal, JSON-LD `schema.org/Event`, RSS/Atom; `collectors/generic.py` — типовые коллекторы.
- `collectors/sources/` — один модуль на источник.
- Результат: `data/raw/<ID>_<модуль>.json` (сырые события) и `data/raw/_run.json` (сводка прогона).

## Этап 3 — база, дедупликация, извлечение из статей

```bash
python scripts/run_collectors.py          # сбор (страницы событий — только новые, известные раз в 7 дней)
python scripts/update_db.py               # data/raw → data/events.db: история, дедупликация, площадки, статусы
python scripts/check_recurring.py         # ежегодные события: дата текущего цикла (раз в неделю)
python scripts/extract_articles.py --dry-run          # оценка стоимости извлечения из статей
python scripts/extract_articles.py --max-cost 2.00    # извлечение через Claude (Haiku), нужен EVENTS_ANTHROPIC_KEY
python scripts/update_db.py --no-load     # события из статей → общая дедупликация
python scripts/foodies_archive.py [--extract] [--status]  # архив Foodies за 12 месяцев: одна страница в день
python scripts/stage3_report.py           # docs/stage3_report.md
```

- `pipeline/db.py` — схема `events.db`: `raw_items` (записи источников, не удаляются), `events` (уникальные события),
  `event_sources`, `status_history`, `venues`/`venue_aliases`, `articles`, `venue_news`, `event_updates`,
  `recurring_events`, `detail_pages` (кэш страниц событий), `llm_usage` (расход Claude API).
- `pipeline/ingest.py` — загрузка прогона, пометка `disappeared`, дедупликация (название + дата + площадка,
  нечёткое сравнение), сведение полей, жизненный цикл `announced → on_sale → sold_out/postponed/cancelled → past`.
- `pipeline/venues.py`, `pipeline/geo.py` — справочник площадок (`data/venues_seed.json` + события), postcodes.io, зоны.
- `pipeline/extract.py` + `prompts/article_extract.md` + `prompts/article_extract.schema.json` — извлечение из статей.
- `pipeline/recurring.py` + `data/recurring_events.json` — ежегодные события (даты начала и окончания; `tickets` —
  нужны ли билеты; `manual_start`/`manual_end` — дата, внесённая вручную, например начало Folk Festival).
- Статусы: `scheduled` (без билетов) · `announced` (билеты ожидаются) → `on_sale` → `sold_out` / `postponed` / `cancelled` → `past`.
- Зоны: `центр` · `до 30 мин` · `до часа` · `Кембриджшир, дальше часа` (районы Peterborough и Fenland) · `out_of_zone`.
- Cambridge BID (S097): статьи в Claude не передаются; заголовки RSS с словами opening/opens/new/closing →
  `venue_news` «требует проверки».
- Ключ Claude API — только в окружении или в `.env` (файл в `.gitignore`).
