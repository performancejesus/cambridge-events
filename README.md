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
python scripts/run_collectors.py S128 S129 S123 S108 S010 S017 S051   # новые коллекторы
python scripts/update_db.py && python scripts/locate_venues.py && python scripts/score_importance.py
python scripts/build_registry_v05.py              # data/cambridge_event_sources_v0.5.xlsx, лист «Проверка P2»
python scripts/stage5_report.py                   # docs/stage5_report.md
```

- Новые коллекторы: S128/S129 (Ents24/Skiddle — 12 городов зоны), S123 Peterborough United (iCal), S108 Wisbech Town
  Council (iCal без заседаний), S010 Peterborough Telegraph (RSS → извлечение), S017 Saffron Hall (HTML: наличие
  билетов, отмены), S051 Kettle's Yard (HTML). S027 RunThrough отключён после этапа 5 (в регионе 0 событий).
- Решения по каждому источнику — `data/p2_decisions.json`.
- Частичный запуск коллекторов: `_run.json` хранит `_run_id`; `update_db` загружает только источники этого запуска.

## Этап 5b — решения после этапа 5, черновик v3

```bash
python scripts/run_collectors.py S116 S117 S118 S119   # газеты Newsquest (RSS)
python scripts/update_db.py                           # + дедупликация между газетами и предфильтр (без модели)
python scripts/extract_articles.py --batch --max-cost 0.30   # Haiku через Message Batches API (−50 %)
python scripts/check_recurring.py                     # ежегодные: + Cambridge Film Festival, Cats, parkrun
python scripts/locate_venues.py && python scripts/score_importance.py   # + правило 40–60 км
python scripts/build_issue.py --issue 2026-10-01 --version v3   # период: дата отправки … +10 дней
python scripts/stage5b_report.py                      # docs/stage5b_report.md
```

- География вне графства: до 40 км по прямой — как раньше; 40–60 км — «до часа» только при оценке ≥ 7, иначе
  `out_of_zone` (`geo.zone` → метка «до часа, если важно» → `importance.resolve_neighbours` после оценки).
  West Suffolk (Бери) — исключение, на подтверждение (`geo.NEIGHBOUR_EXEMPT_DISTRICTS`).
- Newsquest: `extract.newsquest_prefilter` — дубли (номер материала в URL, нормализованный заголовок) →
  `duplicate`, нет ключевых слов или криминал в заголовке → `filtered`; остальные ждут модель. Пакеты Batch API —
  таблица `llm_batches`; не дождались результата — `extract_articles.py --collect` заберёт позже.
- Выпуск (правки по v2): окно начинается с даты отправки; описание у каждого пункта; пустые рубрики не выводятся;
  смешанные алфавиты проверяются в обе стороны; статус открытия не дублируется в названии; «За городом» — без
  оценок < 3 при наличии альтернатив; связанные события (`data/issue_links.json`) — один пункт.

## Этап 6 — непокрытые P1, семейные источники, поля и церкви, отложенные P2, P3

```bash
python scripts/check_ai_robots.py                  # ИИ-запреты в robots.txt → source_ai_policy (то же — в run_collectors)
python scripts/run_collectors.py S052 S069 S012 S001 S048 S054 S055 S131 S130 S132 S134 S071 S126 S113 S022 S043
python scripts/update_db.py && python scripts/locate_venues.py && python scripts/score_importance.py
python scripts/family_count.py                     # семейные события на 14 дней
python scripts/stage6_report.py <копия базы до этапа>   # docs/stage6_report.md, docs/stage6_unique.json
python scripts/build_registry_v06.py               # data/cambridge_event_sources_v0.6.xlsx, лист «Этап 6»
```

- `collectors/htmlevents.py` — общий коллектор HTML-страниц без JSON-LD (дата/время/цена из текста, кэш страниц).
- Новые коллекторы: UCM (S052), Junction (S012), Botanic Garden (S069), Visit Cambridge (S001), University What's On
  (S048), Science Centre (S054), библиотеки через Eventbrite (S055), CPPF (S131), Museum of Cambridge (S130), Milton
  Country Park (S132), Centre for Computing History (S134), Ely Cathedral (S071), Theatre Royal Bury (S126), Visit Ely
  (S113), Huntingdon Racecourse (S022), Mumford Theatre (S043). Решения по всем источникам — `data/p6_decisions.json`.
- Семейный тег: слова в данных (KIDS_RE) или семейная категория, которой источник размечает события (`issue.FAMILY_CATEGORIES`).
- `events.open_space` — события на лугах, в парках и на площадях (`pipeline/open_spaces.py`); запросы для этапа 6b —
  `data/keenable_queries.json`.
- `data/pipeline_config.json` → `respect_ai_disallow` (по умолчанию false): источники с ИИ-запретом в robots.txt →
  режим «заголовок + ссылка, без модели» (`pipeline/ai_policy.py`).

## Этап 6-v4 — выпуск v4 для читателей

```bash
python scripts/update_db.py                        # + evergreen, дубли внутри источника, kids_programmes
python scripts/extract_articles.py --batch         # Cambridge BID снова через модель
python scripts/build_issue.py --issue 2026-10-01 --version v4        # md (с «Для редактора») + reader HTML
python scripts/build_issue.py --issue 2026-10-01 --version v4 --from-json issues/issue_2026-10-01_v4_model.json \
       --add-rubrics holidays,out_of_town         # догенерировать пропущенные моделью рубрики
python scripts/stage6v4_report.py                  # docs/stage6v4_report.md
```

- `data/kids_programmes.json` → таблица `kids_programmes` (`pipeline/kids.py`): детские программы на каникулы
  (провайдер, возраст, даты, часы, цена, место, статус мест, для кого, проверено ли на сайте провайдера).
- Рубрики выпуска: + «Выставки» (длительные, > 14 дней), «Каникулы: куда записать ребёнка» (октябрьские /
  рождественские). Читательская версия — `issue.render_reader_html` (без блока «Для редактора»).
- `data/pipeline_config.json` → `respect_ai_disallow`: `off` / `claude_user_only` / `any_ai_agent`; замер того, что
  пропало бы из выпуска в каждом режиме, — в блоке «Для редактора» и `issues/<выпуск>_ai_measure.json`.
- Цена в HTML-коллекторах — из поля «Price» блока события (у Junction прежний разбор цеплял рекламу членства).


## Этап 6b — аудит пропусков через Keenable, выпуск v5

```bash
python scripts/keenable_search.py                 # 100 запросов аудита + 29 о детских программах (кэш keenable_cache)
python scripts/gap_audit.py extract               # выдача → Haiku по заголовку и сниппету (сайты с ИИ-запретом — без модели)
python scripts/gap_audit.py match                 # сравнение с базой, склейка пропусков (search_gaps)
python scripts/gap_audit.py verify                # проверка пропуска на странице: название и дата рядом (robots.txt, без модели)
python scripts/newspaper_primary.py               # газетные пункты → поиск первоисточника (п. 5 брифа)
python scripts/kids_providers.py list && python scripts/kids_providers.py check   # провайдеры детских программ для 6c
python scripts/load_search_findings.py && python scripts/update_db.py            # подтверждённые находки → S148
python scripts/score_importance.py
python scripts/build_issue.py --issue 2026-10-01 --version v5   # md + reader HTML + editor HTML
python scripts/stage6b_report.py                  # docs/stage6b_report.md
```

- `pipeline/keenable.py` — клиент Keenable (`/v1/search`, заголовок `X-API-Key`, ключ `KEENABLE_API_KEY`), кэш и учёт запросов.
  `/v1/fetch` не используется: страницы читает наш бот (`collectors/http.py`) с учётом robots.txt; тексты — `data/cache/` (не в git).
- `pipeline/domains.py` — robots.txt доменов выдачи (наш бот и ИИ-агенты Anthropic) и связь домена с реестром.
- S148 «Keenable — поиск»: подтверждённые на странице события и открытия, а также ссылки на первоисточник для пунктов,
  которые были только в газетах с ИИ-запретом. В `ingest.rank` газеты с ИИ-запретом идут после S148 — основная ссылка
  события ведёт на первоисточник.
- `data/kids_providers.json` — провайдеры детских программ и лагерей (тип, каникулы, robots.txt) — вход этапа 6c.
- Выпуск v5 (правки по v4): основная часть ≤ 45 пунктов (`build_issue.trim`), «Каникулы» — без модели, одна строка на
  программу (`issue.holiday_groups`), состав участников из всех склеенных записей (`pipeline/lineup.py`, Haiku, кэш),
  забеги и триатлоны — «Спорт → Поучаствовать», а не «Успейте купить билеты», пустые описания убираются,
  «По графству» — от 5. Редакторская версия `_v5_editor_{ru,en}.html` — все кандидаты каждой рубрики под катом с причиной.

## Этап 6c — детские программы, зрительский спорт, кино и лекции, выпуск v6

```bash
python scripts/recheck_blocked.py                 # robots.txt 4xx по RFC 9309 → перепроверка закрытых источников и провайдеров
python scripts/run_collectors.py S149 S150 S151 S152 S105 S153 S019 S154 S020 S155 S045 S144 S163 S164
python scripts/split_roundups.py                  # подборки «Things to do…» → отдельные ссылки, проверка на страницах (S165)
python scripts/kids_collect.py                    # 76 сайтов детских провайдеров → kids_programmes (Haiku, кэш страниц)
python scripts/kids_collect.py --reminders        # за 6 недель до каникул: сколько программ и у кого данных нет
python scripts/update_db.py && python scripts/locate_venues.py && python scripts/score_importance.py
python scripts/enrich_pages.py --issue 2026-10-01 # страницы событий без фактов или цены — одна загрузка у первоисточника
python scripts/build_issue.py --issue 2026-10-01 --version v6    # md, reader и editor HTML, _dropped.csv
python scripts/build_registry_v07.py              # реестр v0.7: листы «Этап 6c» и «Не разобрано»
```

- `collectors/http.py`, `pipeline/domains.py` — robots.txt: 4xx (кроме 429) = правил нет; 429, 5xx, обрыв = запрет.
  Страница с 403 или заглушкой → `unparsed_sources` («Не разобрано», `pipeline/unparsed.py`).
- `collectors/sources/stage6c.py` — коллекторы этапа; `collectors/llmlist.py` — видимый текст страницы → список событий
  (Haiku, кэш по содержимому) для сайтов клубов без структурированных данных.
- `pipeline/school_holidays.py` — все школьные каникулы Cambridgeshire (term dates совета) → `recurring_events` (H-…).
- `pipeline/kids_collect.py` — коллектор провайдеров, зоны без postcode (адрес → справочник площадок → город в названии
  → город провайдера), тексты строк «Каникул» (en/ru), напоминания.
- `pipeline/roundups.py` — признаки подборки; такие записи в выпуск не идут.
- `pipeline/enrich.py` — `event_pages`: фрагмент страницы события и цена (газеты и сайты с ИИ-запретом не загружаются).
- Выпуск: рубрики «В кино», «Лекции и встречи», «Спорт → Также играют» (матчи подключённых клубов без модели),
  «Каникулы» с «Успейте записаться» и «Куда сходить с детьми в каникулы»; правки по v5 — см. `docs/stage6c_report.md`.

## Этап 6d — доделки 6c: партнёрские программы, причины отбора, длина выпуска, кино, выпуск v7

```bash
python scripts/ticket_vendors.py --issue 2026-10-01   # продавец билетов каждого события окна и пунктов v5–v7
python scripts/monetization.py                       # доли и оценка дохода (допущения — data/monetization_params.json)
python scripts/build_registry_v08.py                 # реестр v0.8: «Партнёрская программа», листы «Монетизация», «Не разобрано»
python scripts/talks_audit.py --issue 2026-10-01     # списки talks.cam: что это и сколько событий
python -c "from pipeline.db import connect; from pipeline import film_releases; from collectors.http import PoliteClient; print(film_releases.refresh(connect(), PoliteClient()))"
python scripts/enrich_pages.py --issue 2026-10-01
python scripts/build_issue.py --issue 2026-10-01 --version v7          # + kids_<каникулы>_<год>_{ru,en}.html
python scripts/build_issue.py ... --from-json issues/…_model.json --redo-post   # заново постобработка без основного запроса
```

- `pipeline/vendors.py` — продавец по странице события (домен продавца, кнопка покупки, кассовая система, один переход
  с афиши); `data/affiliates_6d.json` — условия партнёрских программ с источником и датой (только исследование).
- «Причины отбора — явно»: поле `passed_over` в ответе модели → метка «модель предпочла пункт с меньшей оценкой — …»;
  пропуск без причины — в «Для редактора»; заданное и фактическое число пунктов по рубрикам (`RUBRIC_LIMITS`).
- Длина: полных пунктов ≤ 45, компактные строки («Также играют», библиотеки, релизы) — отдельно; сокращение не опускает
  рубрику ниже минимума.
- «Каникулы»: ближайшие — до 12 строк (не больше 2 одного типа) + «Ещё N программ →» на `kids_<каникулы>.html`
  (фильтр по возрасту и зоне) + «Ещё проверьте» для провайдеров за защитой; следующие — до 5 строк.
- `pipeline/film_releases.py` (S167) — «В прокате с пятницы» из открытого календаря релизов UK.

## Этап 7 — контур отмен и изменений, выпуск v8

```bash
python scripts/run_collectors.py && python scripts/update_db.py         # свежий сбор (≈22 мин, 66 коллекторов)
python scripts/extract_articles.py --max-cost 1.00 && python scripts/update_db.py --no-load && python scripts/check_recurring.py
python scripts/locate_venues.py && python scripts/score_importance.py
python scripts/kids_collect.py                        # + страницы совета и лагеря Cambridge United (data/kids_providers_extra.json)
python scripts/ticket_vendors.py --issue 2026-10-08  # страницы продавцов — для перепроверки
python scripts/recheck_status.py --issue 2026-10-08  # статусы и сигналы срочности со страниц → page_status
python scripts/update_db.py --no-load                 # статусы со страниц → events.status, status_history
python -c "from pipeline.db import connect; from pipeline import ai_sources; print(ai_sources.refresh(connect()))"
python scripts/enrich_pages.py --issue 2026-10-08 && python scripts/build_issue.py --issue 2026-10-08 --version v8
```

- `pipeline/status_check.py` — перепроверка страницы события: метки «Cancelled», «Sold out», «Limited availability»,
  «Last few tickets», кнопки покупки; из свободного текста — только однозначные фразы («this event has been cancelled»).
  Результат — `page_status`; `ingest.refresh` учитывает его при пересчёте статуса (отмена, перенос, распродано,
  открытие продаж у анонса); `disappeared` — в выпуск не идёт, только редактору.
- Сигналы срочности → кандидаты `T-p…` для «Успейте купить билеты» и пометка «мало билетов» у пункта.
- `pipeline/ai_sources.py` — источники с ИИ-запретом определяются по robots.txt всех источников (`data/ai_sources.json`).
- Постобработка выпуска: имена кириллицей → Haiku переписывает латиницей; пропуски без причины → один короткий
  запрос за причинами; даты релизов — пятница.
- `docs/stage8_options.md` — варианты хостинга, рассылки и публикации страниц (исследование).

## Этап 7b — Cambridge Union, колледжи, кино, выпуск v9

```bash
python scripts/college_audit.py                       # 31 колледж: страницы событий, фиды, robots.txt, события в базе
python scripts/run_collectors.py && python scripts/update_db.py   # + S049 Union, S067 NGS, S157 Light, S168 Camdram, S169–S175
python scripts/extract_articles.py --max-cost 1.00 && python scripts/update_db.py --no-load && python scripts/check_recurring.py
python scripts/locate_venues.py && python scripts/score_importance.py
python scripts/college_coverage.py                    # решение по каждому колледжу, до/после → data/college_coverage_7b.json
python scripts/build_registry_v09.py                  # реестр v0.9: лист «Колледжи», новые источники, «Не разобрано»
python scripts/recheck_status.py --issue 2026-10-08 && python scripts/update_db.py --no-load
python -c "from pipeline.db import connect; from pipeline import ai_sources; print(ai_sources.refresh(connect()))"
python scripts/enrich_pages.py --issue 2026-10-08 && python scripts/build_issue.py --issue 2026-10-08 --version v9
```

- `pipeline/access.py` — поле `access` у события: `open` / `members` (членство может купить любой: пометка и цена
  членства в строке с датой) / `restricted` (только студенты и сотрудники — не в выпуск).
- `collectors/sources/cambridge_union.py` — cus.org: записи `event_jet` из открытого REST WordPress, уровень доступа и
  площадка со страницы события, стоимость членства Open со страницы членства.
- `collectors/sources/stage7b.py` — Camdram (все площадки, кроме ADC), National Garden Scheme (API findagarden),
  Light Cinema (мини-гид JSON: event cinema и спецпоказы), страницы событий колледжей через Haiku (выпускники и
  студенты отсекаются).
- `pipeline/cinema.py` — «В кино»: где идёт (Light, Arts Picturehouse), оценка фильма (просмотры Wikipedia, широкий
  прокат, местный повод), описание из Wikipedia; 2–4 главных фильма — полными пунктами (кандидаты `F…`).
- `pipeline/history.py` — история выпусков `issue_items`: уже показанное в прошлых выпусках не повторяется.
- `pipeline/glossary.py` — общий глоссарий перевода для выпуска и «Каникул» (Junior gym → тренажёрный зал для подростков).

## Этап 7c — обязательные проверки каждого выпуска, правки по v9, «В колледжах», Cambridge Union, выпуск v10

```bash
python scripts/run_collectors.py && python scripts/update_db.py     # свежий сбор (S144 — ссылка на страницу события и «Free»)
python scripts/extract_articles.py --max-cost 1.00 && python scripts/update_db.py --no-load && python scripts/check_recurring.py
python scripts/locate_venues.py && python scripts/score_importance.py
python scripts/union_watch.py                         # Cambridge Union: Varsity RSS + termcard текущего триместра на Issuu
python scripts/union_watch.py --termcard michaelmas_term_2025_the_cambridge_union --year 2025   # архивная termcard
python scripts/build_registry_v10.py                  # реестр v0.10: S176 Varsity, S177 termcard на Issuu
python scripts/recheck_status.py --issue 2026-10-08 && python scripts/update_db.py --no-load
python scripts/enrich_pages.py --issue 2026-10-08     # + страницы открытий, найденных поиском (Arbury Social, Bridge Bagels)
python scripts/build_issue.py --issue 2026-10-08 --version v10       # сборка + все проверки + плашка «НЕ ОТПРАВЛЯТЬ»
python scripts/check_issue.py --issue 2026-10-08 --version v9        # проверки на готовом выпуске без пересборки
python -m pytest tests -q                             # регрессионные тесты (Барретт, дубли имён, заголовки, лига)
```

- `tests/issue_rules/` — обязательные проверки, один файл на правило (`r01_…` – `r34_…`): `RULE`, `TITLE`, `LEVEL`
  (`block` — красная плашка «НЕ ОТПРАВЛЯТЬ: …» вверху редакторской версии и `send_allowed: false` в
  `issues/<выпуск>_checks.json`; `fix` — исправляется при сборке, проверка — что не осталось), `check(ctx)`.
  Правила 1–28 — из брифа, 29–34 — правки по v9 и новые рубрики. Снять блокирующую находку может только редактор —
  запись в `data/check_overrides.json` (правило, фрагмент находки, почему, кто, когда). Таблица «проверка → уровень → результат» — первым
  блоком в «Для редактора». Проверки не удаляются и не отключаются без решения редактора.
- `tests/issue_rules/claims.py` — сверка утверждений с текстами источников (тема недели, вступления и пункты из статей —
  Sonnet, остальные — Haiku; кэш `claim_checks`): «искажено» в строгих пунктах блокирует (правило 2), «нет в
  источнике» — в «Факты из знаний модели (проверить)» (правило 29). `links.py` — проверка ссылок нашим ботом (кэш
  `link_checks`, сутки).
- `pipeline/verified_facts.py` + `data/verified_facts.json` — таблица проверенных фактов (дата рождения Барретта, лига
  Cambridge United 2026/27); модель видит их во входных данных, правило 1 сверяет с ними дни рождения и юбилеи.
- `pipeline/issue_fixes.py` — исправления по v9: цена и ссылка из лучшего источника события и его несклеенных дублей
  (`issue._siblings`: The bEAT на Corn Exchange и musiclivecambridge), приписки в заголовках, дубли имён кириллицей,
  неподтверждённая лига, пустые описания «Нового в городе».
- `pipeline/colleges.py` — рубрика «В колледжах» (3–6 компактных строк без модели, не больше 2 от колледжа).
- `pipeline/union_termcard.py`, `scripts/union_watch.py` — termcard Cambridge Union на Issuu (изображения страниц →
  один запрос к модели) и статьи Varsity → таблица кандидатов `union_termcard`; строка «В Cambridge Union на этой неделе
  (для членов клуба): …» — только из termcard.

## Этап 7d — музеи, усадьбы, фермы, Кингс-Линн, кино округи, ежегодные фестивали, правки по v10, выпуск v11

```bash
python scripts/run_collectors.py && python scripts/update_db.py     # + S070 NT, S139 Audley End, S178–S183
python scripts/check_recurring.py                     # фестивали: статус (ожидаем / дата объявлена / в продаже)
python scripts/places_7d.py --probe                   # закрытые места и кинотеатры → лист «Не разобрано» (две попытки)
python scripts/build_registry_v11.py                  # реестр v0.11
python scripts/build_issue.py --issue 2026-10-08 --version v11
python scripts/places_7d.py --table issues/issue_2026-10-08_v11_model.json   # таблица мест → data/places_7d.json
python -m pytest tests -q
```

- `collectors/sources/stage7d.py` — National Trust (S070: Wimpole, Anglesey Abbey, Wicken Fen; данные страницы
  `__NEXT_DATA__`), English Heritage (S139: открытый API поиска событий, Audley End), Bury Lane Farm Shop (S178), Museum
  of Technology (S179), Ely Museum (S180), Corn Exchange King's Lynn (S181), кинотеатры зоны (S182: таблица
  `regional_showings` с городом; событиями — только трансляции и спецпоказы), Visit West Norfolk (S183).
- `pipeline/geo.py` — `EXEMPT_TOWNS_KM`: Кингс-Линн (6 км от центра) — зона «до часа», как West Suffolk; остальной
  Норфолк — вне зоны.
- `pipeline/museums.py` — рубрика «В музеях и усадьбах» (4–6 компактных строк без модели, ≤ 2 от места; выставки — в
  первую неделю открытия; без регулярных занятий). Проверка 37.
- Кино округи: `issue.build_pools` снимает показ S182, если фильм идёт в Light или Arts Picturehouse (проверка 38).
- Ежегодные фестивали (`recurring_events.festival`, `stage`, `stage_since`, `town`, `shared_page`): пункт в «Новых
  анонсах», когда объявлены дата или продажа билетов (за 21 день до выпуска), и напоминание за 4–6 недель; в остальных
  выпусках не повторяются (проверка 39). Cambridge Pride — R25 (сайт закрыт robots.txt — через события и статьи).
  Огни и ярмарки — только в Кембридже (`town`); дата со страницы-календаря — только рядом с названием (`shared_page`).
- Правки по v10: проверка 35 — грамматика русских текстов одним запросом к Haiku (`issue_fixes.fix_grammar`, кэш
  `text_fixes`); 36 — стадия открытия не противоречит описанию (Bridge Bagels), дата «скоро откроется» — не дата
  открытия; 9 — имена режиссёров и актёров «В кино» латиницей (имена из Wikipedia фильма, транслитерация целиком для
  коротких фамилий); 1 — неподтверждённое «одна из старейших» переписывается по тексту источника
  (`issue_fixes.fix_superlatives`); промпт — факт для описания = то, что важно зрителю сейчас; склейка дублей
  musiclivecambridge по slug + дате + площадке (`ingest.merge_mlc`).
