# Этап 6 — непокрытые P1, семейные источники, поля и церкви, отложенные P2, P3 (2026-09-28)

Решения по источникам — `data/p6_decisions.json`, реестр — `data/cambridge_event_sources_v0.6.xlsx` (лист «Этап 6»). Новые уникальные — будущие события в зоне, которых не было ни в одном источнике до этапа 6.

## Семейные события на ближайшие 14 дней

Окно: 2026-09-28 … +14 дней, события в зоне. Семейное — явная пометка в данных: family / kids / children / ages / half-term и т.п. в названии, описании или категориях, либо семейная категория, которой источник сам размечает события (фильтры UCM «Families / Under 5s / 5+ / Family events», раздел Visit Cambridge family-friendly, раздел Families университетского What's On, Science Centre).

- **До этапа 6: 5** — Pa-Kua Martial Art & Self-Defense for Kids (years 5-12) (2026-09-30); Things to do in Cambridge for Halloween (2026-10-01); Kids K-Pop Party - Cambridge (2026-10-03); NCT Cambridge Autumn Nearly New Sale (2026-10-03); Royston Fundraising Event (Halloween pottery) (2026-10-05).
- **После: 29**. По источникам: S001 — 14, S052 — 8, S054 — 4, S008 — 3, S012 — 2, S069 — 2, S055 — 1, S130 — 1, S005 — 1, S007 — 1, S129 — 1, S048 — 1.

<details><summary>Список</summary>

- 2024-10-16 — Cambridge Murder Mystery (S001)
- 2025-01-18 — Children's Craft Drop-In at Cambridge Central Library (S055)
- 2025-08-16 — The Wonderful Wizard of Oz Experience – Cambridge (S001)
- 2026-01-17 — The Art of Deception (S052)
- 2026-05-09 — Discover Cambridge: The Ultimate City Exploration Game (S001)
- 2026-06-26 — Live Piano in the Heart of Cambridge (S001)
- 2026-06-27 — Bach to Baby Family Concert in Cambridge (S001)
- 2026-07-01 — Cambridge Bank Heist Experience (S001)
- 2026-07-31 — Cats of Cambridge – Exhibition through the Museum (S001)
- 2026-07-31 — Cats of Cambridge (S001)
- 2026-09-30 — Pa-Kua Martial Art & Self-Defense for Kids (years 5-12) (S008)
- 2026-09-30 — Little Feet, Big Impressions (S130)
- 2026-10-01 — Things to do in Cambridge for Halloween (S005)
- 2026-10-02 — Animal Tails: Fossil Fun (S052)
- 2026-10-02 — STEMtots – Space Exploration (S054)
- 2026-10-03 — Kids K-Pop Party - Cambridge (S007, S012, S129)
- 2026-10-03 — NCT Cambridge Autumn Nearly New Sale (S008)
- 2026-10-03 — Fun with Fungi (S001, S052, S069)
- 2026-10-03 — Discover the Science Around Us (S054)
- 2026-10-04 — Nearly New Bay and Children’s sale (S001)
- 2026-10-05 — Royston Fundraising Event (Halloween pottery) (S008)
- 2026-10-07 — Family Friendly Drop In (S052)
- 2026-10-09 — STEMtots – Marvellous Magnets (S054)
- 2026-10-10 — Fungi Field Day (S001, S048, S052, S069)
- 2026-10-10 — Fungi Field Day 2026 (S001, S052)
- 2026-10-10 — Get Curious, Get Creative, Get Scientific (S054)
- 2026-10-11 — Studio Sunday Relaxed Session (S001, S052)
- 2026-10-11 — Studio Sunday (S001, S052)
- 2026-10-11 — Dance In The Dark | Cambridge Junction (S012)

</details>

## HTML-источники P1 без коллектора

| ID | Решение | Новых уникальных | Всего в зоне | Вне зоны | Запросов / сек | Примечание |
|---|---|---|---|---|---|---|
| S012 | подключён | 239 | 260 | — | 15 / 37.9 | HTML /whats-on/page/N + страницы событий («Event Information»: дата, время, цена); кэш страниц |
| S052 | подключён | 87 | 99 | — | 6 / 12.3 | сводная афиша 8 музеев (HTML, один запрос на весь список) + 4 запроса по фильтрам «для кого»/«тип» → категория family по разметке музеев |
| S001 | подключён | 83 | 98 | — | 116 / 323.7 | 7 разделов /event-categories/ (постранично) + страницы событий; раздел family-friendly → категория family |
| S048 | подключён | 41 | 46 | 2 | 7 / 15.3 | недельные страницы admin.cam.ac.uk/whatson (3 недели) + раздел Families; iCal/RSS на webservices закрыты robots.txt — не используем |
| S069 | подключён | 17 | 18 | — | 4 / 9.9 | HTML /whats-on/ + страницы событий; часть событий есть и в S052 |
| S026 | ежегодное | — | — | — | — | через recurring_events (R11) |
| S028 | ежегодное | — | — | — | — | через recurring_events (R03) |
| S030 | ежегодное | — | — | — | — | Cambridge Festival — весна; дата через recurring_events (R04); коллектор программы — перед фестивалем (март) |
| S031 | ежегодное | — | — | — | — | через recurring_events (R09) |
| S041 | покрыт | — | — | — | — | защита от ботов; афиша — через Ents24 (S006) |
| S045 | не нужен | — | — | — | — | сеансы — только через внутренний AJAX с XSRF-токеном сессии (не используем); обычные сеансы — не события выпуска; спецпоказы приходят через Visit Cambridge, статьи и Cambridge Film Festival (recurring R17) |
| S056 | производный | — | — | — | — | тег «дети» из музейных источников — теперь по разметке S052/S048/S001 (категория family) и KIDS_RE |
| S062 | производный | — | — | — | — | тег «комедия» из S011, S012, S042 |
| S065 | ежегодное | — | — | — | — | через recurring_events (R12) |
| S070 | вручную | — | — | — | — | National Trust — защита Radware; ручной сезонный календарь |
| S081 | ежегодное | — | — | — | — | через recurring_events (R02) |
| S082 | ежегодное | — | — | — | — | через recurring_events (R10) |
| S089 | ежегодное | — | — | — | — | Cloudflare; через статьи и recurring_events (R14, вручную) |
| S090 | не собираем | — | — | — | — | robots.txt запрещает раздел событий |

## Семейные источники

| ID | Решение | Новых уникальных | Всего в зоне | Вне зоны | Запросов / сек | Примечание |
|---|---|---|---|---|---|---|
| S131 | подключён | 106 | 108 | — | 2 / 5.7 | Cambridge Past, Present & Future: Wandlebury, Leper Chapel, Hinxton Watermill, Coton, Bourn Windmill, Grantchester — список /events-list/ (Eventin), один запрос |
| S055 | подключён | 12 | 12 | — | 14 / 27.9 | события библиотек — на Eventbrite (страница организатора со страницы совета), JSON-LD страниц событий; серии помечены «recurring series» |
| S054 | подключён | 9 | 9 | — | 11 / 22.8 | ссылки — из RSS /whats-on/feed/, дата и время — со страницы события; все события — семейные (family) |
| S130 | подключён | 7 | 7 | — | 2 / 4.2 | Museum of Cambridge — REST The Events Calendar |
| S134 | подключён | 6 | 6 | — | 2 / 11.2 | Centre for Computing History — страница What's On, дата и название в ссылке |
| S100 | закрыт | — | — | — | — | Hinchingbrooke Country Park: события только на TicketSource (robots.txt отвечает 403 — считаем запретом) и в Facebook (не парсим); страница совета без дат — проверить на этапе 6b через поиск |

## Семейные места и аттракционы (новая категория, P2)

| ID | Решение | Новых уникальных | Всего в зоне | Вне зоны | Запросов / сек | Примечание |
|---|---|---|---|---|---|---|
| S132 | подключён | 7 | 7 | — | 2 / 3.6 | Milton Country Park (Wix): список /events — название, день, место |
| S133 | отложен | — | — | — | — | Nene Park / Ferry Meadows: при проверке JSON-LD Event на /events/ (24 события), но при сборе сайт начал обрывать соединение и отвечать 403 — защита от ботов, не обходим; коллектор написан (family_misc.NenePark), из прогона убран — повторить позже / этап 6b |
| S135 | закрыт | — | — | — | — | Shepreth Wildlife Park: сайт отвечает 403 / обрывает соединение — не обходим; этап 6b |
| S136 | не нужен | — | — | — | — | Linton Zoo: на сайте и в DigiTickets — только входные билеты, событий нет; сезонные события — через статьи |
| S137 | закрыт | — | — | — | — | Hamerton Zoo Park: 429 на robots.txt и главную — считаем запретом, повторить на этапе 6b |
| S138 | вручную | — | — | — | — | Wimpole Home Farm — National Trust (S070): защита Radware, ручной сезонный календарь |
| S139 | отложен | — | — | — | — | Audley End (English Heritage): события на странице загружаются скриптом, в HTML дат нет; JSON-LD нет — этап 6b (поиск) или ручной сезонный календарь |
| S140 | отложен | — | — | — | — | Woburn Safari Park: страница событий отвечает 500; вне графства, ~55 км — только события ≥ 7 по правилу 40–60 км |

## Поля, церкви, ярмарки

| ID | Решение | Новых уникальных | Всего в зоне | Вне зоны | Запросов / сек | Примечание |
|---|---|---|---|---|---|---|
| S071 | подключён | 29 | 32 | — | 2 / 4.2 | Ely Cathedral: карточки /events (дата + название), один запрос; отложен в P2 на этапе 5 |
| S039 | ежегодное | — | — | — | — | Christmas in Cambridge (Parker's Piece: каток, маркет, колесо) — recurring R21, дата со страницы (13.11.2026 – 3.01.2027) |
| S141 | не нужен | — | — | — | — | A Church Near You: robots.txt разрешает (кроме /christmas/events/), но события — по страницам каждого прихода (сотни в епархии Ely) и в основном регулярные службы; единого источника на графство нет. Концерты крупных церквей уже приходят через Ents24 (King's Chapel, Great St Mary's), University What's On (обеденные концерты GSM) и Visit Cambridge; пропуски — проверить на этапе 6b |
| S142 | закрыт | — | — | — | — | ChurchSuite: churchsuite.com за Cloudflare (403) — не обходим; календари отдельных приходов (<приход>.churchsuite.com) — если найдутся на этапе 6b |
| S143 | покрыт | — | — | — | — | King's College Chapel: страница концертов без дат в HTML; концерты есть в Ents24 (S006) и Visit Cambridge |
| S144 | покрыт | — | — | — | — | St John's College Chapel: события — отдельными страницами без списка с датами; крупные концерты — в Visit Cambridge |
| S145 | закрыт | — | — | — | — | Trinity College Chapel: ошибка сертификата TLS; Great St Mary's (gsm.cam.ac.uk — 502, greatstmarys.org — страница на скриптах): обеденные концерты — через University What's On (S048) |
| S146 | не нужен | — | — | — | — | Round Church: сайт визит-центра, событий в афише нет; St Botolph's — домен отвечает 502 |
| S147 | ежегодное | — | — | — | — | Stourbridge Fair (Leper Chapel, CPPF) — recurring R22; Big Weekend — R23; включение рождественских огней — R24 |

## Отложенные P2

| ID | Решение | Новых уникальных | Всего в зоне | Вне зоны | Запросов / сек | Примечание |
|---|---|---|---|---|---|---|
| S126 | подключён | 30 | 33 | — | 35 / 96.7 | Theatre Royal Bury St Edmunds: список — REST WordPress /wp-json/wp/v2/events (~33), дата и цена — со страниц спектаклей; RSS /feed/ — новости театра, не афиша |
| S113 | подключён | 10 | 11 | — | 3 / 6.3 | Visit Ely: /whats-on/ (JetEngine), дата начала и конца в карточке; площадка не указана — зона по городу Эли |
| S067 | отложен | — | — | — | — | NGS (открытые сады): приложение findagarden на скриптах; сезон апрель–сентябрь — проверить API весной |
| S076 | отложен | — | — | — | — | Mill Road Fringe: страница без дат, фестиваль летом — проверить к сезону; Winter Fair — в recurring (R16) |
| S086 | не нужен | — | — | — | — | Addenbrooke's Charitable Trust: благотворительные забеги и акции для участников, не события для зрителей; Dragon Boat Festival — в recurring (R10) |
| S098 | не нужен | — | — | — | — | South Cambridgeshire DC: календарь — заседания совета, не публичные события |
| S099 | не нужен | — | — | — | — | East Cambridgeshire DC: страница событий пуста |
| S105 | не нужен | — | — | — | — | St Neots Town Council: 5–6 событий в год (Bands in the Park, Dragon Boat Race, включение огней), на страницах без дат — ловятся статьями Hunts Post (S116) |
| S111 | не нужен | — | — | — | — | Whittlesey Town Council: страницы событий без дат; Straw Bear — в recurring (R01), остальное — статьи Cambs Times (S117) |
| S115 | отложен | — | — | — | — | Discover Huntingdonshire: афиша загружается скриптом, в HTML дат нет — этап 6b (поиск) |

## Источники P3

| ID | Решение | Новых уникальных | Всего в зоне | Вне зоны | Запросов / сек | Примечание |
|---|---|---|---|---|---|---|
| S022 | подключён | 11 | 11 | — | 2 / 3.4 | Huntingdon Racecourse: JSON-LD на странице событий Jockey Club (как Newmarket S021) |
| S009 | не нужен | — | — | — | — | Songkick: страница города — 404, API для новых партнёров закрыт; концерты покрыты Ents24/Skiddle (S006, S007) |
| S016 | не нужен | — | — | — | — | хоровая музыка колледжей — покрыто: King's/GSM через Ents24 и University What's On (S048), St John's/Trinity — Visit Cambridge (S001); регулярный evensong в выпуск не идёт |
| S019 | не нужен | — | — | — | — | Cambridge City FC: 8-й уровень (Isthmian North, стадион в Sawston), матчи низкой значимости; сайт лиги без календаря в HTML, Football Web Pages — 403 |
| S024 | ежегодное | — | — | — | — | Town Bumps: сайт Cambridgeshire Rowing Association отвечает 502; летние Town Bumps — в бэклог recurring (дата вручную) |
| S025 | вручную | — | — | — | — | Varsity-матчи: календарь вручную (даты публикуются университетскими клубами), крупные — через статьи |
| S037 | не нужен | — | — | — | — | Cambridge Science Festival слит с Cambridge Festival — дубль R04 |
| S040 | покрыт | — | — | — | — | деревенские fetes — через Eventbrite (S008), Visit Cambridge (S001), статьи Newsquest (S116–S119); Facebook-группы не парсим |
| S043 | подключён | — | — | — | 1 / 0.5 | Mumford Theatre (ARU): афиша на Eventbrite (страница организатора), JSON-LD страниц событий; сейчас у организатора 0 предстоящих (upcomingEventsTotal: 0) — межсезонье |
| S059 | не нужен | — | — | — | — | Cambridge Market — ежедневный рынок, стабильное расписание: справочник, не событие |
| S060 | не нужен | — | — | — | — | All Saints Garden Art & Craft Market — регулярный (суббота), справочник |
| S061 | не нужен | — | — | — | — | car boot sales — агрегатора с разрешающим robots.txt не нашлось; регулярные — справочник |
| S063 | покрыт | — | — | — | — | Resident Advisor — 403; клубные события — Skiddle (S007, S129) |
| S064 | не нужен | — | — | — | — | квизы в пабах — справочник, не лента событий |
| S068 | вручную | — | — | — | — | дни открытых дверей колледжей — Open Cambridge (R12) и University What's On (S048) |
| S073 | вручную | — | — | — | — | традиции (Remembrance, Pancake Race) — статичный календарь / recurring вручную; Remembrance в Эли — пришло из статьи Ely Standard |
| S074 | закрыт | — | — | — | — | Makespace: 429 на robots.txt — считаем запретом; курсы для членов, не публичные события |
| S080 | не нужен | — | — | — | — | Stagecoach / Park & Ride — транспорт, не события (рубрики «Практическое» в выпуске нет) |
| S085 | отложен | — | — | — | — | Cambridge Pythons: сайт отвечает 502, сезон BAFA весна–лето — проверить весной вместе с Cambridgeshire Cats (R18) |

## Нагрузка на ежедневный прогон

Новые коллекторы этапа 6 (16): первый прогон — 224 запросов, 10 мин (пауза 2 с на хост; страницы событий Junction, Visit Cambridge, What's On, Theatre Royal, Science Centre, Eventbrite кэшируются на 7–14 дней, поэтому в обычный день запрашиваются только новые). В обычный день — примерно 35–45 списков + новые страницы событий (оценка: 60–100 запросов, 3–5 минут).

## ИИ-запреты в robots.txt: флаг respect_ai_disallow

`data/pipeline_config.json` → `respect_ai_disallow: false` (по брифу — до решения выключен). Включённый флаг переводит источники с ИИ-запретом в режим «заголовок + ссылка, без модели» (`extract.keyword_news`, как Cambridge BID). Список определяется автоматически при каждом прогоне коллекторов (`pipeline/ai_policy.py` → таблица `source_ai_policy`; отдельно — `scripts/check_ai_robots.py`).

| Источник | Хост | ИИ-запрет | Агенты |
|---|---|---|---|
| S002 | www.whatsonincambridge.com | нет | — |
| S003 | www.cambridgeindependent.co.uk | да | anthropic-ai,ClaudeBot,Claude-Web,Claude-SearchBot |
| S004 | www.cambridge-news.co.uk | да | anthropic-ai,ClaudeBot,Claude-Web |
| S005 | cambridge105.co.uk | нет | — |
| S010 | www.peterboroughtoday.co.uk | да | anthropic-ai,ClaudeBot,Claude-Web |
| S050 | fitzmuseum.cam.ac.uk | нет | — |
| S087 | cambridgefoodies.me.uk | нет | — |
| S092 | www.cambridgeindependent.co.uk | да | anthropic-ai,ClaudeBot,Claude-Web,Claude-SearchBot |
| S093 | www.cambridge-news.co.uk | да | anthropic-ai,ClaudeBot,Claude-Web |
| S097 | www.cambridgebid.co.uk | нет | — |
| S116 | www.huntspost.co.uk | да | anthropic-ai,ClaudeBot,Claude-User,Claude-Web,Claude-SearchBot |
| S117 | www.cambstimes.co.uk | да | anthropic-ai,ClaudeBot,Claude-User,Claude-Web,Claude-SearchBot |
| S118 | www.wisbechstandard.co.uk | да | anthropic-ai,ClaudeBot,Claude-User,Claude-Web,Claude-SearchBot |
| S119 | www.elystandard.co.uk | да | anthropic-ai,ClaudeBot,Claude-User,Claude-Web,Claude-SearchBot |

## Итог в цифрах

- **Новых уникальных будущих событий в зоне: 650**, из них 156 — на ближайшие 14 дней. Крупнейшие источники: Junction 239, CPPF 106, UCM 87, Visit Cambridge 83, What's On 41, Theatre Royal Bury 30, Ely Cathedral 29.
- **Семейные события на 14 дней: 5 → 29.**
  - 19 из них начинаются в этом окне: Science Centre (STEMtots, выходные программы), UCM (Fossil Fun, Family Friendly Drop In, Studio Sunday), Botanic (Fun with Fungi, Fungi Field Day), Museum of Cambridge, библиотеки.
  - 10 — длительные: городские квесты и «experiences» с Visit Cambridge, выставки с семейной пометкой. Для рубрики «С детьми» полезны прежде всего первые 19.
  - «Fungi Field Day» и «Fungi Field Day 2026» не склеились: из-за «2026» в названии. Этот дубль будет виден в блоке «Для редактора».
- Расход на этапе — в основном оценка известности 651 нового события (Sonnet, 14 вызовов, $0.96). Поиск площадок — $0.04, статьи Newsquest — $0.007.

## Что ещё сделано на этапе 6

- **Решения после этапа 5b.** West Suffolk остаётся исключением (обычная зона «до часа»). Stevenage теперь всегда идёт по правилу 40–60 км, даже ближе 40 км (`geo.NEIGHBOUR_ALWAYS_DISTRICTS`). Четыре статьи Newsquest из очереди обработаны пакетом Batch API ($0.0074): 3 события и 1 обновление, среди них Gruffalo и Peppa Pig на Nene Valley Railway.
- **Флаг `respect_ai_disallow`** (`data/pipeline_config.json`, по умолчанию `false`, поведение не менялось).
  - Список источников с ИИ-запретом определяется автоматически по robots.txt хоста статей при каждом прогоне коллекторов: `pipeline/ai_policy.py`, таблица `source_ai_policy`.
  - Если включить флаг, эти источники уходят в режим «заголовок + ссылка, без модели», так же как Cambridge BID.
  - Проверено: при `true` без модели остаются S003, S004, S010, S092, S093, S116–S119 и S097; из очереди модели уходят все статьи этих источников.
- **Находка по Cambridge BID.** В robots.txt Cambridge BID ИИ-агенты (anthropic-ai, ClaudeBot) перечислены в одной группе с `User-agent: *` и получают те же правила, что все остальные: статьи сайта им **открыты**. Решение этапа 3 «BID — без модели» основано на моём неверном прочтении этого файла. Сейчас ничего не менял, BID по-прежнему в `NO_LLM_SOURCES`. Это стоит учесть при решении открытого вопроса.
- **P1 без коллектора.** До этапа 6 их было 19 (лист «Этап 6» реестра v0.6).
  - Коллекторы написаны для 5: S052, S069, S012, S001, S048.
  - Ещё 7 источников — ежегодные события, они идут через `recurring_events`: S026, S028, S031, S065, S081, S082, S089.
  - S030 Cambridge Festival и S039 рождественские маркеты — сезонные, тоже через `recurring_events`.
  - S041 Arts Theatre покрыт Ents24, S070 National Trust вносится вручную, S090 DesignMyNight закрыт robots.txt, S056 и S062 — производные теги.
  - S045 Arts Picturehouse отдаёт сеансы только через внутренний AJAX с XSRF-токеном сессии. Его не используем: спецпоказы приходят через Visit Cambridge, статьи и Cambridge Film Festival.
- **Общий HTML-коллектор** (`collectors/htmlevents.py`) для страниц без JSON-LD: ссылки со страниц списка, дата, время и цена из текста страницы события, с тем же инкрементальным кэшем страниц. На нём работают Junction, Botanic Garden, Visit Cambridge, Science Centre и Theatre Royal.
  - Внутри одного прогона повторная ссылка больше не запрашивается заново: What's On за 3 недели — 157 ссылок, но около 60 уникальных страниц.
- **Поля и парки.** Событие с местом на лугу, в парке или на площади помечается в `events.open_space` (`pipeline/open_spaces.py`). Список: Jesus Green, Midsummer Common, Parker's Piece, Christ's Pieces, Coldham's, Stourbridge Common, Cherry Hinton Hall и другие; аналоги в Эли, St Ives, Huntingdon, St Neots, Питерборо. Пометка ставится и событиям из статей.
- **Новые ежегодные события в `recurring_events`:**
  - R21 Christmas in Cambridge (Parker's Piece, дата найдена: 13.11.2026 – 3.01.2027);
  - R22 Stourbridge Fair (Leper Chapel);
  - R23 Big Weekend;
  - R24 включение рождественских огней.
- Запросы для этапа 6b (поля и парки, церкви, закрытые семейные места) — в `data/keenable_queries.json`.
- **Церкви.**
  - A Church Near You открыт для ботов, но это отдельные страницы сотен приходов, и там в основном регулярные службы. Единым источником на графство он не станет.
  - ChurchSuite закрыт Cloudflare.
  - Концерты King's Chapel и Great St Mary's уже приходят через Ents24 и University What's On.
  - Подключён Ely Cathedral (32 события).
- **Ограничения данных:**
  - Библиотеки на Eventbrite — в основном регулярные серии (Rhymetime, Storytime). JSON-LD даёт начало и конец всей серии, а не ближайшее занятие, поэтому такие записи помечены категорией «recurring series». В выпуске их нужно подавать как «регулярные занятия». Это правило для следующей сборки.
  - У Theatre Royal Bury и Ely Cathedral нет времени начала: оно указано только на странице бронирования.
  - Nene Park при сборе стал отвечать 403. Коллектор написан, но из прогона убран.

## Расход Claude API на этап

| Назначение | Модель | Запросов | $ |
|---|---|---|---|
| importance | claude-sonnet-5 | 14 | 0.9559 |
| venue_locate | claude-haiku-4-5 | 26 | 0.0442 |
| article_extract_batch | claude-haiku-4-5 | 4 | 0.0074 |
| **итого** | | | **1.0075** |

Всего за проект: $6.21.
