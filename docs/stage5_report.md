# Этап 5 — источники приоритета 2 и расширение географии (2026-09-28)

Проверка: `scripts/probe_sources.py --set p2` → `data/probe_results_p2.json` (кандидаты — `data/p2_candidates.json`).
Решения по источникам — `data/p2_decisions.json`. Новые уникальные события — будущие события в зоне, у которых нет ни одного источника P1.

## Итог проверки

- Источников проверено: 65 (32 из реестра с приоритетом 2, 30 новых S098–S127, 2 страницы агрегаторов S128/S129, Kettle's Yard S051 из P1).
- Состояние: живой — 45, закрыт — 14, — — 3, нет событий — 2, частично — 1.
- Решение: не нужен — 18, отложен — 14, закрыт — 13, подключён — 8, ежегодное — 8, нужно решение — 4.

| ID | Источник | Состояние | Решение | Новых уникальных | Всего в зоне | Вне зоны | Примечание |
|---|---|---|---|---|---|---|---|
| S128 | Ents24 — города зоны | живой | подключён | 135 | 137 | 24 | Ents24: 12 страниц городов зоны (расширение S006) |
| S017 | Saffron Hall | живой | подключён | 74 | 74 | — | HTML-карточки: дата, время, наличие билетов (Nearly full → «мало билетов»), отмены |
| S129 | Skiddle — города зоны | живой | подключён | 70 | 111 | 92 | Skiddle: 12 страниц городов зоны (расширение S007) |
| S051 | Kettle's Yard | живой | подключён | 20 | 20 | — | приоритет 1, коллектора не было: HTML страниц событий (контрольный пример этапа 5) |
| S123 | Peterborough United — домашние матчи | живой | подключён | 20 | 20 | — | iCal fixtur.es, домашние матчи |
| S108 | Wisbech Town Council | живой | подключён | 2 | 2 | — | iCal совета без заседаний: городские события (иллюминация, ярмарки) |
| S010 | Peterborough Telegraph | живой | подключён | — | — | — | RSS (HTML сайта — 403); статьи → извлечение через Claude |
| S027 | RunThrough — события в Кембридже | живой | подключён | — | — | — | JSON-LD SportsEvent, но список — 24 ближайших забега по стране; сейчас в регионе 0 (фильтр по почтовым зонам). Ценность низкая — пересмотреть на этапе 6 |
| S013 | The Portland Arms | закрыт | не нужен | — | — | — | robots.txt отвечает 403; концерты есть на Ents24/Skiddle (S006/S007) |
| S014 | Storey's Field Centre (Eddington) | живой | не нужен | — | — | — | фид — 3 новости; события продаются через Eventbrite (S008) и Cambridge Live Tickets (S091) |
| S015 | West Road Concert Hall | живой | не нужен | — | — | — | HTML без JSON-LD; концерты уже приходят из S091, S005, S007, S008 |
| S020 | Cambridge Rugby Club | закрыт | закрыт | — | — | — | страница-проверка (HTTP 202, бот-защита); обходить не будем |
| S023 | CUCBC — May Bumps / Lent Bumps | живой | ежегодное | — | — | — | Lent/May Bumps — сезонно; RSS новостей есть; даты — через recurring_events |
| S029 | Let's Do This — Cambridgeshire | закрыт | закрыт | — | — | — | robots.txt отвечает 403 |
| S034 | Whittlesea Straw Bear Festival | живой | ежегодное | — | — | — | уже в recurring_events (R01) |
| S035 | Cambridge Film Festival | живой | ежегодное | — | — | — | фестиваль раз в год (осень); HTML без фида — предлагаю добавить в recurring_events |
| S036 | Cambridge Literary Festival | закрыт | закрыт | — | — | — | 403 на сайт и /events |
| S044 | Постановки в садах колледжей (лето) | живой | ежегодное | — | — | — | летний сезон постановок; ручной сезонный календарь |
| S046 | Кино под открытым небом (летние сезоны) | нет событий | ежегодное | — | — | — | летние показы; адрес организатора не подтверждён — ручной сезонный |
| S049 | Cambridge Union | живой | не нужен | — | — | — | мероприятия в основном для членов Union; публичные крупные гости попадают в новости |
| S053 | IWM Duxford | закрыт | закрыт | — | — | — | iwm.org.uk — 403 (бот-защита) на все страницы; в Ents24/Skiddle Duxford не найден |
| S054 | Cambridge Science Centre | живой | отложен | — | — | — | WordPress, тип записей events без дат в API — нужен разбор HTML (детские события — ценно) |
| S055 | Библиотеки Cambridgeshire | живой | отложен | — | — | — | Contensis, события библиотек — на сторонних сервисах; нужен разбор |
| S057 | Eat Cambridge | живой | ежегодное | — | — | — | фестиваль в мае; фид — 3 записи |
| S058 | Открытия ресторанов | — | не нужен | — | — | — | производный источник: открытия через S092/S093 (извлечение из статей) |
| S066 | Heritage Open Days | живой | ежегодное | — | — | — | Heritage Open Days — сентябрь; поиск по региону в HTML |
| S067 | National Garden Scheme | живой | отложен | — | — | — | findagarden.ngs.org.uk — сезон весна–лето; разбор HTML |
| S071 | Ely Cathedral | живой | отложен | — | — | — | Spektrix без JSON-LD; часть концертов уже из Ents24/Skiddle (S128/S129) и Eventbrite |
| S075 | Воркшопы в музеях | — | не нужен | — | — | — | производный (музеи) |
| S076 | Love Mill Road / Mill Road Fringe | живой | отложен | — | — | — | Mill Road Fringe — сезонно; страница WordPress без событийных данных |
| S077 | Районные FB-группы и Nextdoor | — | не нужен | — | — | — | соцсети — по правилам не парсим |
| S078 | Перекрытия дорог (county council / one.network) | закрыт | закрыт | — | — | — | robots.txt запрещает |
| S079 | Greater Anglia / Thameslink / National Rail | живой | не нужен | — | — | — | не события (транспорт); вернуться к этому, если понадобится практический блок |
| S083 | «Nihao! China» Cambridge Dragon Boat Festival | живой | ежегодное | — | — | — | фестиваль в июне; билеты на Eventbrite (S008) |
| S084 | Cambridgeshire Cats (американский футбол) | живой | отложен | — | — | — | сайт WordPress (новости), страницы расписания нет; сезон BAFA — весна–лето, сейчас матчей нет |
| S086 | Addenbrooke's Charitable Trust — события | живой | отложен | — | — | — | WordPress events + RSS; благотворительные забеги и челленджи — разбор HTML |
| S088 | parkrun — Cambridge, Wimpole и др. | закрыт | закрыт | — | — | — | parkrun.org.uk: robots.txt отвечает 403 — считаем запретом; регулярные забеги — статичный справочник вручную |
| S098 | South Cambridgeshire District Council | живой | отложен | — | — | — | страница /events есть, событийных данных нет |
| S099 | East Cambridgeshire District Council | живой | отложен | — | — | — | Drupal, /events без структурированных данных |
| S100 | Huntingdonshire District Council | живой | отложен | — | — | — | события Hinchingbrooke Country Park — через TicketSource; разбор HTML |
| S101 | Fenland District Council | закрыт | закрыт | — | — | — | robots.txt отвечает 403 |
| S102 | Peterborough City Council | живой | не нужен | — | — | — | раздела событий нет (404) |
| S103 | Ely City Council | закрыт | закрыт | — | — | — | cityofelycouncil.org.uk: robots.txt отвечает 403 |
| S104 | St Ives Town Council | закрыт | закрыт | — | — | — | stivestowncouncil.gov.uk: robots.txt отвечает 403 |
| S105 | St Neots Town Council | живой | отложен | — | — | — | WordPress council_events — разбор HTML |
| S106 | Huntingdon Town Council | закрыт | закрыт | — | — | — | robots.txt отвечает 403 |
| S107 | Ramsey Town Council | нет событий | не нужен | — | — | — | iCal совета пуст |
| S109 | March Town Council | живой | не нужен | — | — | — | RSS — новости и заседания |
| S110 | Chatteris Town Council | живой | не нужен | — | — | — | RSS — новости и заседания |
| S111 | Whittlesey Town Council | живой | отложен | — | — | — | WordPress, раздел событий — разбор HTML |
| S112 | Soham Town Council | закрыт | закрыт | — | — | — | soham-tc.gov.uk: robots.txt отвечает 403 |
| S113 | Visit Ely | живой | отложен | — | — | — | WordPress (API закрыт, 401); события — разбор HTML |
| S114 | Visit Peterborough | закрыт | закрыт | — | — | — | robots.txt отвечает 403 |
| S115 | Visit Huntingdonshire | живой | отложен | — | — | — | cPortals, календарь HTML |
| S116 | Hunts Post | живой | нужно решение | — | — | — | RSS /news/rss/ (50 статей, ~неделя); у четырёх газет Newsquest много общих материалов. Извлечение через Claude ≈ 200 статей в неделю ≈ $0.5–0.9/нед (Haiku) — не запускал без вашего решения |
| S117 | Cambs Times | живой | нужно решение | — | — | — | RSS /news/rss/ (50 статей, ~неделя); у четырёх газет Newsquest много общих материалов. Извлечение через Claude ≈ 200 статей в неделю ≈ $0.5–0.9/нед (Haiku) — не запускал без вашего решения |
| S118 | Wisbech Standard | живой | нужно решение | — | — | — | RSS /news/rss/ (50 статей, ~неделя); у четырёх газет Newsquest много общих материалов. Извлечение через Claude ≈ 200 статей в неделю ≈ $0.5–0.9/нед (Haiku) — не запускал без вашего решения |
| S119 | Ely Standard | живой | нужно решение | — | — | — | RSS /news/rss/ (50 статей, ~неделя); у четырёх газет Newsquest много общих материалов. Извлечение через Claude ≈ 200 статей в неделю ≈ $0.5–0.9/нед (Haiku) — не запускал без вашего решения |
| S120 | Peterborough Cathedral | закрыт | не нужен | — | — | — | HTTP 202 (бот-защита); концерты собора есть на Ents24/Skiddle (S128/S129) |
| S121 | Key Theatre (Peterborough) | живой | не нужен | — | — | — | покрыт Ents24/Skiddle по городу (S128/S129) |
| S122 | New Theatre Peterborough | живой | не нужен | — | — | — | покрыт Ents24 по городу (S128) |
| S124 | Royston — Town Council / события | живой | не нужен | — | — | — | Royston — через Skiddle/Ents24 по городу (S128/S129) |
| S125 | Haverhill — Arts Centre / Town Council | живой | не нужен | — | — | — | Haverhill Arts Centre — через Ents24 по городу (S128) |
| S126 | Bury St Edmunds — Apex / Theatre Royal / Visit Bury | живой | не нужен | — | — | — | Apex и Theatre Royal — через Ents24 по городу (S128) |
| S127 | Saffron Walden / Newmarket — Town Councils | частично | закрыт | — | — | — | saffronwalden.gov.uk — 403; newmarket.gov.uk — robots.txt недоступен |

## События по районам (будущие, в зоне)

| Район | Всего событий | из них новых (этап 5) |
|---|---|---|
| Cambridge | 324 | 20 |
| Uttlesford | 82 | 80 |
| Peterborough | 74 | 74 |
| West Suffolk | 64 | 47 |
| East Cambridgeshire | 39 | 30 |
| South Cambridgeshire | 35 | 5 |
| Cambridge (адрес не уточнён) | 16 | — |
| Stevenage | 14 | — |
| Huntingdonshire | 13 | 8 |
| Chelmsford | 11 | 8 |
| North Hertfordshire | 10 | 4 |
| Central Bedfordshire | 10 | 9 |
| Bedford | 8 | 7 |
| Fenland | 6 | 5 |
| East Hertfordshire | 5 | 3 |
| Welwyn Hatfield | 4 | 4 |
| Luton | 4 | 4 |
| Harlow | 3 | 2 |
| St Albans | 2 | 2 |
| North Northamptonshire | 2 | 2 |
| Mid Suffolk | 2 | 2 |
| King's Lynn and West Norfolk | 1 | 1 |
| Breckland | 1 | 1 |
| Braintree | 1 | 1 |

## Контрольные позиции

| Что | В базе (будущие) | Откуда / почему нет |
|---|---|---|
| parkrun | нет | parkrun.org.uk: robots.txt отвечает 403 — считаем запретом; регулярные забеги — только вручную |
| Cambridgeshire Cats | нет | сайт живой (WordPress, новости), расписания на сайте нет; сезон BAFA — весна–лето |
| IWM Duxford | нет | iwm.org.uk — 403 (бот-защита) на все страницы; в Ents24/Skiddle не найден |
| Kettle's Yard | 20 | коллектор S051 (этап 5): страницы событий |
| Saffron Hall | 76 | коллектор S017 (этап 5) + Ents24 по Saffron Walden (S128) |

## Вне зоны

- Помечено `out_of_zone` (будущие): S129 — 92, S128 — 24. Страница города у Skiddle включает соседние регионы — зона считается по postcode площадки, в выпуск не идут.

## Решения после этапа 4b: оценка важности

Wikipedia и известность — только за того, кто на сцене (поле `performer`); трибьюты, шоу «по мотивам» и составы с одним известным именем — с потолком; у постановок классики считается труппа, не пьеса; бесплатно / цена неизвестна и площадка без вместимости — нейтральный сигнал; лекции без билетов — известность × 1.6; пересчёт — только при изменении входных данных (сигнатура); «Главное на выходные» — 3–5 лучших, не ниже 4.

| # | Оценка | Дата | Событие | Главные причины |
|---|---|---|---|---|
| 1 | 9 | 2026-10-11 | ROACHFORD + HUE AND CRY | Cambridge Corn Exchange ~1800 мест (+1.9); Wikipedia «Andrew Roachford»: 4 883 просмотров за 30 дней (+1.7); модель: Roachford 6/10 — известный соул-исполнитель 80-х (+1.4) |
| 2 | 8.9 | 2026-10-06 | Don Broco | Cambridge Corn Exchange ~1800 мест (+1.9); Wikipedia «Don Broco»: 5 710 просмотров за 30 дней (+1.7); модель: Don Broco 6/10 — известная британская рок-группа (+1.4) |
| 3 | 8.5 | 2026-09-28 | Quantum gravity, from philosophy to the detection of a Planck-scale pa | Wikipedia «Carlo Rovelli»: 17 494 просмотров за 30 дней (+3.2); модель: Carlo Rovelli 7/10 — известный физик-популяризатор (+2.7); Ray Dolby Auditorium ~400 мест (+1.1) |
| 4 | 8.4 | 2026-09-29 | My Royal Life: An Audience with Lucy Worsley | Wikipedia «Lucy Worsley»: 32 156 просмотров за 30 дней (+2.2); Cambridge Corn Exchange ~1800 мест (+1.9); модель: Lucy Worsley 8/10 — известный телеведущий и историк (+1.9) |
| 5 | 8.4 | 2026-10-08 | Simon Amstell: I Love It Here | Cambridge Corn Exchange ~1800 мест (+1.9); модель: Simon Amstell 8/10 — известный британский комик и телеведущий (+1.9); Wikipedia «Simon Amstell»: 7 630 просмотров за 30 дней (+1.8) |
| 6 | 8.2 | 2026-10-01 | JOE JACKSON - HOPE AND FURY TOUR 2026 | Wikipedia «Joe Jackson (musician)»: 29 016 просмотров за 30 дней (+2.2); Cambridge Corn Exchange ~1800 мест (+1.9); модель: Joe Jackson 7/10 — известный британский музыкант с карьерой с 1970-х (+1.7) |
| 7 | 8.2 | 2026-10-09 | Alison Moyet | Wikipedia «Alison Moyet»: 25 534 просмотров за 30 дней (+2.1); Cambridge Corn Exchange ~1800 мест (+1.9); модель: Alison Moyet 7/10 — известная британская певица, экс-Yazoo (+1.7) |
| 8 | 8.2 | 2026-10-10 | Cambridge United FC - Blackpool FC | Abbey Stadium ~8000 мест (+2.7); футбол: чемпионат, соперник Blackpool FC (+2.5); есть статья в новостях (+1) |
| 9 | 8.1 | 2026-10-02 | Steve Hackett – Best of Genesis & Solo Gems | Wikipedia «Steve Hackett»: 16 408 просмотров за 30 дней (+2); Cambridge Corn Exchange ~1800 мест (+1.9); модель: Steve Hackett 7/10 — бывший гитарист Genesis, известный солист (+1.7) |
| 10 | 7.9 | 2026-10-10 | A Tribute to Syd Barrett - Official 80th Anniversary Celebrations | Cambridge Corn Exchange ~1800 мест (+1.9); модель: Kula Shaker 5/10 (тема: Syd Barrett — основатель Pink Floyd) (+1.1); билеты до £132 (+1) |
| 11 | 7.2 | 2026-10-03 | Gianmarco Soresi: The Misery Loves Tour | Wikipedia «Gianmarco Soresi»: 25 165 просмотров за 30 дней (+2.1); Cambridge Corn Exchange ~1800 мест (+1.9); билеты до £44 (+0.9) |
| 12 | 6.8 | 2026-10-07 | Kevin Bloody Wilson | Cambridge Corn Exchange ~1800 мест (+1.9); Wikipedia «Kevin Bloody Wilson»: 2 435 просмотров за 30 дней (+1.5); модель: Kevin Bloody Wilson 5/10 — известный австралийский комик (+1.1) |
| 13 | 6.5 | 2026-10-02 | City of Birmingham Symphony Orchestra | модель: City of Birmingham Symphony Orchestra 8/10 — известный оркестр национального уровня (+1.9); Saffron Hall ~740 мест (+1.4); Wikipedia «City of Birmingham Symphony Orchestra»: 875 просмотров за 30 дней (+1.2) |
| 14 | 6.5 | 2026-10-10 | Martin Kemp | Wikipedia «Martin Kemp»: 40 610 просмотров за 30 дней (+2.3); модель: Martin Kemp 7/10 — актер и музыкант Spandau Ballet (+1.7); вместимость неизвестна — нейтрально (+1) |
| 15 | 6.4 | 2026-10-11 | Shine with Jess Gillam and her Band | Wikipedia «Jess Gillam»: 6 409 просмотров за 30 дней (+1.8); модель: Jess Gillam 7/10 — известная саксофонистка, телеведущая BBC (+1.7); Saffron Hall ~740 мест (+1.4) |

Проверочные события:

- **Quantum gravity, from philosophy to the detection of a Planc** — 8.5: Wikipedia «Carlo Rovelli»: 17 494 просмотров за 30 дней (+3.2); модель: Carlo Rovelli 7/10 — известный физик-популяризатор (+2.7); Ray Dolby Auditorium ~400 мест (+1.1); цена неизвестна — нейтрально (+0.5); лекция без билетов: известность выступающего × 1.6
- **Boyband In The Buff** — 5: Cambridge Corn Exchange ~1800 мест (+1.9); билеты до £55 (+1); модель: Gareth Gates 3/10 — финалист Pop Idol, известен в Британии (+0.6); 2 источника (+0.5); трибьют / шоу по мотивам / одно известное имя в составе: Wikipedia не учитывается, модель не выше 3
- **CAST 2026: King Lear** — 2.3: ADC Theatre ~230 мест (+0.8); цена неизвестна — нейтрально (+0.5); постановка: известность «King Lear» не считается, считается труппа

## Примечания

- **Способ расширения географии.** У большинства сайтов Питерборо и соседних городков нет ни фидов, ни JSON-LD. Ents24
  и Skiddle (уже в P1) отдают страницы по 12 городам зоны с JSON-LD — это дало основную часть новых событий
  (S128, S129). Площадки Key Theatre, New Theatre, Apex, Theatre Royal Bury, Haverhill Arts Centre, собор Питерборо
  приходят отсюда. Минус: только первая страница листинга (продолжение подгружается скриптом), так что крупные
  площадки покрыты частично.
- **Skiddle по городу** включает соседние регионы: 92 будущих события помечены `out_of_zone` по postcode площадки.
- **Saffron Hall** (S017): отдельный коллектор даёт полный календарь (74 уникальных события; Ents24 по Saffron Walden
  дал только 3 концерта Saffron Hall) и новые сигналы: «Nearly full» → `few_left` («мало билетов», +0.5 к важности;
  сейчас у 4 концертов), отмены («MILOŠ & Ksenija Sidorova»,
  3.10 — статус `cancelled`, пойдёт в рубрику «Отменено и перенесено»).
- **Закрытые сайты** — robots.txt отвечает 403 (считаем запретом, как на этапе 1): городские советы Ely, St Ives,
  Huntingdon, Soham, Fenland DC, Visit Peterborough, parkrun, Let's Do This, Portland Arms; бот-защита: IWM Duxford,
  Cambridge Rugby Club, собор Питерборо, Cambridge Literary Festival. Не обходим.
- **Отложено (живые, но без структурированных данных)** — 14 источников: нужен разбор HTML под каждый сайт. Это
  кандидаты для этапа 6 вместе с P3; самые ценные — Cambridge Science Centre (детские события), Visit Ely, Discover
  Huntingdonshire, Ely Cathedral.
- **Нужно ваше решение:** четыре газеты Newsquest (Hunts Post, Cambs Times, Wisbech Standard, Ely Standard) — RSS
  найден (`/news/rss/`, по 50 статей в неделю, много общих материалов). Извлечение через Claude ≈ 200 статей в неделю ≈
  $0.5–0.9/нед (Haiku). Не запускал.
- **Частичный прогон коллекторов.** Найдены и исправлены две ошибки конвейера: (1) при запуске части коллекторов
  `update_db` брал метку прогона из старых записей `_run.json` — новые события получили бы вчерашнюю дату первого
  появления (теперь `_run_id` текущего запуска, старые файлы не перечитываются); (2) магазины ТЦ, чьи коллекторы не
  запускались, считались «пропавшими» — 98 ложных закрытий в «Новом в городе» появились и были откачены; сравнение
  списков ТЦ теперь только для источников текущего прогона.
- **Реестр:** `data/cambridge_event_sources_v0.5.xlsx` — строки P2 с решением в «Заметках», новые S098–S129, лист
  «Проверка P2». Бриф ссылается на v0.4 — v0.5 создан рядом, v0.4 не менялся.

## Расход Claude API

| Что | Модель | $ |
|---|---|---|
| Решения после 4b: полная переоценка известности (новое поле «кто на сцене») + 3 склеенных события | claude-sonnet-5 | 0.6673 |
| Этап 5: оценка известности новых событий зоны (без `out_of_zone`) | claude-sonnet-5 | 0.4980 |
| Этап 5: извлечение из 19 статей Peterborough Telegraph | claude-haiku-4-5 | 0.0508 |
| Этап 5: поиск площадок без postcode | claude-haiku-4-5 | 0.0026 |
| **Итого за ход** | | **1.2186** |

С начала проекта: $4.70.
