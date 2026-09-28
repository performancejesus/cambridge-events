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
- Cambridge BID (S097): статьи в Claude не передаются; заголовки RSS со словами opening / opens / now open /
  coming soon / closing / closes / closed → `venue_news` «требует проверки».
- `python scripts/extract_articles.py --rerun-venue-news` — повторное извлечение статей, чьи записи `venue_news`
  без номера дома/postcode или без даты (их записи заменяются новым результатом; `--articles 30,44` — выборочно).
- Ключ Claude API — только в окружении или в `.env` (файл в `.gitignore`).

## Этап 4 — черновик выпуска

```bash
python scripts/build_issue.py --issue 2026-10-01 --start 2026-09-28 --end 2026-10-11 --version v2
python scripts/build_issue.py ... --dry-run                      # только пулы кандидатов, без API
python scripts/build_issue.py ... --from-json issues/issue_2026-10-01_v2_model.json   # перерисовать без API
```

- `pipeline/issue.py` — пулы кандидатов из базы (события окна, серии одним пунктом, новые анонсы, старт продаж,
  отмены, «новое в городе»), поиск несклеенных дублей, даты и рендер Markdown.
- `prompts/issue.md` + `prompts/issue.schema.json` — отбор и тексты (Claude Sonnet 5): модель выбирает кандидатов
  по id и пишет название, место, цену и 1–2 предложения на английском и русском; даты, время и ссылки — из базы.
- `scripts/build_issue.py` — вызов модели, проверка ответа (id, повторы, соответствие рубрике, цена по данным,
  латиница в русском тексте), блок «Для редактора». Ответ модели сохраняется в `issues/issue_<дата>_model.json`
  (туда же — ручные правки `manual_fixes` и заметки ревью `review_notes`, они выводятся редактору).
- Результат: `issues/issue_<дата>_en.md`, `issues/issue_<дата>_ru.md`.

## Этап 4b — баги данных, важность, черновик v2

```bash
python scripts/update_db.py --no-load     # даты (окончание до 06:00 → однодневное), ручные склейки, зоны
python scripts/locate_venues.py           # площадки без postcode: справочник → текст страницы (Haiku) → postcodes.io
python scripts/score_importance.py        # importance_score / importance_reason (Sonnet + Wikipedia, кэш)
python scripts/build_issue.py --issue 2026-10-01 --start 2026-09-28 --end 2026-10-11 --version v2
```

- Даты: `normalize.end_date` — окончание на следующий день до 06:00 = тот же день (Cambridge 105 «весь день»
  00:00–23:59:59 UTC, ночные вечеринки); iCal `DTEND` с датой — исключающая граница.
- `data/manual_merges.json` — ручные склейки дублей (матч United — Blackpool, концерт и выставка Syd Barrett).
- `pipeline/locate.py` + `prompts/venue_locate.md` — адрес площадки из текста страницы события или статьи; найденные
  площадки попадают в справочник (`venues.origin = located`, `precision`: postcode / place / city). Населённые
  пункты — postcodes.io `/places` (кэш `places`). Фестивали на разных площадках — `events.multi_venue`.
- `pipeline/importance.py` + `prompts/importance.md` — оценка важности: вместимость (`data/venue_capacity.json`,
  примерно), цена, источники, статья, sold out, ежегодный флагман, Wikipedia (кэш `wiki_cache`), футбол по метке
  турнира, известность по оценке модели (кэш `fame_cache`); веса — `data/importance_weights.json`.

## Этап 5 — источники приоритета 2 и расширение географии

```bash
python scripts/probe_sources.py --set p2          # data/p2_candidates.json → data/probe_results_p2.json
python scripts/run_collectors.py S128 S129 S123 S108 S010 S017 S051 S027   # новые коллекторы
python scripts/update_db.py && python scripts/locate_venues.py && python scripts/score_importance.py
python scripts/build_registry_v05.py              # data/cambridge_event_sources_v0.5.xlsx, лист «Проверка P2»
python scripts/stage5_report.py                   # docs/stage5_report.md
```

- Новые коллекторы: S128/S129 (Ents24/Skiddle — 12 городов зоны), S123 Peterborough United (iCal), S108 Wisbech Town
  Council (iCal без заседаний), S010 Peterborough Telegraph (RSS → извлечение), S017 Saffron Hall (HTML: наличие
  билетов, отмены), S051 Kettle's Yard (HTML), S027 RunThrough (JSON-LD, фильтр по региону).
- Решения по каждому источнику — `data/p2_decisions.json`.
- Частичный запуск коллекторов: `_run.json` хранит `_run_id`; `update_db` загружает только источники этого запуска.

