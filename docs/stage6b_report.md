# Этап 6b — аудит пропусков через Keenable (2026-09-28)

## Проверка ключей и тестовый запрос

- `KEENABLE_API_KEY` и `EVENTS_ANTHROPIC_KEY` заданы (значения не выводились).
- Тестовый запрос `POST https://api.keenable.ai/v1/search` («Cambridge events October 2026», 5 результатов) — **HTTP 200** за 0,44 с. Клиент — `pipeline/keenable.py` (заголовок `X-API-Key`, кэш `keenable_cache`, учёт `keenable_usage`); `/v1/fetch` не используется — страницы читает наш бот с учётом robots.txt.

## 1. Запросы

Аудит — 100 запросов (`data/keenable_queries.json`), по 10 результатов: категории — 27, городки — 20, открытия — 15, поля и парки — 26, церкви — 6, семейные места — 6. Отдельно — 29 запросов о провайдерах детских программ (для 6c) и 40 запросов о первоисточниках газетных пунктов (п. 5).

Уникальных страниц в выдаче аудита — 945. Из них 152 — на сайтах, чей robots.txt закрыт для ИИ-агентов Anthropic (газеты Cambridge News, Cambridge Independent, Peterborough Telegraph, Newsquest, talks.cam, BBC и др.): их сниппеты в модель не передавались. Остальные разобраны Haiku по заголовку и сниппету (`prompts/search_extract.md`): о зоне — 591, о другом месте (в т.ч. Cambridge, Massachusetts) — 188, неясно — 13.

## 2. Сравнение с базой

Из сниппетов извлечены конкретные события и открытия; каждое сравнивалось с базой (название + даты, нечётко; затем — то же название на другую дату ±120 дней; открытия — с `venue_news` и списками арендаторов ТЦ).

|  | события | открытия/закрытия |
|---|---|---|
| уже в базе | 72 | 6 |
| в базе, но на другую дату (ошибка даты в сниппете) | 10 | — |
| в списке арендаторов ТЦ (база, не новость) | — | 1 |
| **нет в базе (кандидат в пропуски)** | **157** | **23** |
| прошедшие | 101 | — |
| без даты | 36 | — |
| вне зоны / неясно | 18 | 1 |

Покрытие будущих событий зоны, которые нашёл поиск: 82 из 239 (34%) уже в базе — по сырым кандидатам (в них много ошибок извлечения из сниппетов); по подтверждённым пропускам — см. ниже.

Одинаковые пункты с разных страниц склеены: **145 пропусков** (129 событий, 16 открытий/закрытий). Каждый проверен на странице нашим ботом (robots.txt, без модели): название есть на странице, и ближайшая к названию дата — нужная (у листингов на странице много дат подряд; первая версия проверки «дата где-то рядом» подтверждала, например, органные концерты King's на каждое воскресенье).

| проверка | пропусков |
|---|---|
| подтверждено на странице | 63 |
| название есть, даты рядом нет | 42 |
| страница не открылась | 21 |
| на странице не найдено | 8 |
| robots.txt закрывает | 7 |
| не проверялось (вне зоны или позже 31.12) | 4 |

Подтверждённые я просмотрел вручную и отклонил 10 (`data/search_review.json`): Independent café — «Independent café» — без названия заведения; Inflatable Aquapark — надувной аквапарк — сезонный, работал летом; Cambridge Sunday Market — еженедельный рынок — не событие; Organ recital: Daniel Hyde — Daniel Hyde — руководитель хора King's; его имя стоит рядом с каждой д; Concerts at King's — «Concerts at King's» — раздел сайта, не событие; Organ recital: Daniel Hyde — то же: Daniel Hyde, 18 октября играет David Newsholme; Day Trip to Cambridge — автобусный тур «Day Trip to Cambridge» — туристический продукт (evergr; Organ recital: Daniel Hyde — то же: Daniel Hyde, 25 октября играет Hamish Wagstaff; Ely Maltings — «Ely Maltings» — площадка, не событие; Day Trip to Cambridge — то же, туристический продукт.
Дальше «пропуск» = подтверждённый на странице и не отклонённый; остальные — кандидаты, не факты.

### Пропуски по категориям

Подтверждённых событий-пропусков — 41 (из них в окне выпуска 1–11 октября — 14), открытий/закрытий — 12.

| категория | подтверждено | кандидатов всего |
|---|---|---|
| концерты | 11 | 34 |
| церковная музыка | 4 | 19 |
| спорт | 7 | 18 |
| другое | 5 | 16 |
| рынки и ярмарки | 4 | 12 |
| лекции | 4 | 9 |
| вечеринки | 2 | 6 |
| выставки | 1 | 4 |
| прогулки и природа | 0 | 3 |
| фестивали | 1 | 3 |
| комедия | 1 | 2 |
| семейное | 1 | 2 |
| театр | 0 | 1 |

По группам запросов (подтверждённые; пропуск может прийти из нескольких групп): городки — 18, категории — 17, открытия — 11, церкви — 8, поля и парки — 1.

## 3. Откуда пропуски — топ-20 доменов

Домен считается для пропуска, если он был среди страниц, где пропуск найден. «Реестр» — есть ли домен среди источников реестра v0.6 (URL, endpoint или ссылки собранных событий).

| домен | подтв. | всего | реестр | robots.txt | тип | примеры |
|---|---|---|---|---|---|---|
| allevents.in | 6 | 12 | нет | открыт | агрегатор | Great Fen Apple and Harvest Fair; Open Evening - Wisbech campus; Live Music with The Arcades |
| kingscollegechoir.com | 4 | 29 | нет | открыт | первоисточник/сайт | Organ recital: Paul Greally; Organ recital: David Newsholme; Organ recital: Hamish Wagstaff |
| buff.ly | 3 | 5 | нет | открыт | агрегатор | Workshop: Crafted Connections presents R; Music at the Museum; Spark Art Club |
| timeoutdoors.com | 2 | 8 | нет | открыт | агрегатор | Grafham Water Trail Races; AEPG Great Eastern Run |
| findarace.com | 2 | 3 | нет | открыт | агрегатор | Abington Festival of Running; AEPG Great Eastern Run |
| tickettailor.com | 2 | 3 | нет | открыт | первоисточник/сайт | Workshop: Crafted Connections presents R; Music at the Museum |
| runningeventsnearme.com | 2 | 3 | нет | открыт | агрегатор | Abington Festival of Running; Bidwells Cambridge 10k |
| dovetailevents.co.uk | 2 | 2 | нет | открыт | агрегатор | OASSIS – From Knebworth to The Met Loung; Unified Dating – Meet Singles in Ely |
| runabc.co.uk | 2 | 2 | нет | открыт | агрегатор | Grafham Water Trail Races; Cambridgeshire Halloween Run |
| gotrail.run | 2 | 2 | нет | открыт | первоисточник/сайт | Phoenix Cambridgeshire - KiSS CHARITY RU; Cambridgeshire Halloween Run |
| cmp.cam.ac.uk | 1 | 3 | нет | открыт | первоисточник/сайт | Poulenc and Vaughan Williams |
| online.bright-publishing.com | 1 | 2 | нет | открыт | первоисточник/сайт | Marvin's |
| trip.com | 1 | 2 | нет | открыт | агрегатор | A Night at the Opera by Candlelight |
| musiclivecambridge.com | 1 | 2 | нет | открыт | первоисточник/сайт | Open Mic Night @ The Boathouse |
| eventslist.co.uk | 1 | 2 | нет | открыт | агрегатор | Fishies Cambridge WEVS | LAUNCH NIGHT ft |
| joh.cam.ac.uk | 1 | 2 | S144 | открыт | первоисточник/сайт | Chapel Lecture – If humans are unique… ? |
| alfiebsmith.com | 1 | 1 | нет | закрыт | первоисточник/сайт | BrewDog |
| fashionunited.uk | 1 | 1 | нет | открыт | первоисточник/сайт | River Island |
| bbc.com.im | 1 | 1 | нет | открыт | первоисточник/сайт | The Grafton Ping Pong Parlour |
| tindli.com | 1 | 1 | нет | открыт | первоисточник/сайт | TINDLI Peterborough |

### Какие сайты добавить в реестр, а что ловится только поиском

Смотрел на подтверждённые пропуски и на то, повторяются ли они (у сайта есть своя афиша с датами, а не одна
страница). Все сайты ниже открыты для нашего бота; ИИ-запретов в robots.txt у них нет.

**Добавить как обычные источники (коллекторы):**

| сайт | что даёт | почему не было | решение |
|---|---|---|---|
| kingscollegechoir.com | концерты King's College Chapel: воскресные органные концерты (бесплатно, 14:15), Tallis Scholars 28.10, выступления хора | S143 (kings.cam.ac.uk) на этапе 6 помечен «покрыт через Ents24/Visit Cambridge» — но органной серии и части концертов там нет. У сайта хора — страницы концертов с датой, временем и программой | P2, коллектор HTML (страницы `/concert/…`) |
| cmp.cam.ac.uk (факультет музыки / CUMS) | концерты в West Road Concert Hall и капеллах колледжей (Poulenc & Vaughan Williams 24.10, Bantock 16.10, Live on Wednesdays) | S015 West Road на этапе 5 — «не нужен, концерты приходят из S091/S005/S007/S008»; студенческие и факультетские концерты оттуда не приходят | P2, коллектор HTML |
| runabc.co.uk (или findarace.com) | забеги и трейлы зоны с датой и взносом (Grafham Water Trail Races, Halloween Run St Neots, Great Eastern Run) | в реестре нет источника забегов с регистрацией (RunThrough S027 отключён — национальный список) | P3, коллектор календаря по графству; в выпуске — «Спорт → Поучаствовать» |
| Royston Museum (через tickettailor.com) | концерты, мастер-классы, детский арт-клуб, лекции (Music at the Museum 2.10, Spark Art Club 8.10) | S124 Royston — «через Ents24/Skiddle»: музейные события туда не попадают | P3, коллектор TicketTailor-страницы музея |
| musiclivecambridge.com | открытые микрофоны и концерты в пабах Кембриджа | пабы в реестре только частично | P3, проверить robots и структуру; если листинг стабильный — подключить |
| stneots-tc.gov.uk (S105, уже в реестре) | Farm & Craft Market по субботам (10.10, 24.10, 14.11, 28.11), Bands in the Park | этап 6: «не нужен, 5–6 событий в год» — но рынков больше | пересмотреть решение: подключить (WordPress `council_events`) |

**Ловится только поиском (в реестр не добавлять):**
- **Открытия магазинов и кафе** (12 подтверждённых, которых нет в базе): Nobody's Child (Grand Arcade, июль), Astrid & Miyu (Trinity Street, июль), River Island и Ping Pong Parlour (The Grafton), Marvin's (Mill Road), Arbury Social (25.09), Bridge Bagels (28.09), Burger King и Jamaica Blue (Питерборо) и др. Они приходят из отраслевых изданий (fashionunited, retailtimes, klm-re — сайты недвижимости, франчайзинговые сайты), сайтов самих брендов и совета — у каждого по одной новости, регулярного источника нет. Списки арендаторов ТЦ (S094–S096) их не ловят: магазин, который был в списке при первом прогоне, считается базой (решение этапа 3).
- **Даты ежегодных событий с закрытыми сайтами**: Town & Gown 10K нашёлся как «Bidwells Cambridge Town & Gown 10K», 4 октября, Midsummer Common (страница Bidwells), `recurring_events` R14 теперь с датой — это контрольный пример брифа, который раньше ожидался только из новостей или вручную.
- **Единичные события** агрегаторов-зеркал (allevents.in, dovetailevents, eventslist, stayhappening/happeningnext): это перепечатки чужих афиш с большим количеством ошибок в датах; брать как кандидатов поиска, но не как источник. Исключение — Питерборо и Fenland: allevents даёт концерты в пабах, которых нет больше нигде (Met Lounge, Secret Garden в Wisbech, Pig N Falcon), но они почти всегда ниже порога «По графству».
- Bury St Edmunds Literary Festival (10–11.10) — в `recurring_events` (кандидат), страница фестиваля без дат рядом с названиями — проверить вручную.

### Итоговая рекомендация по Keenable

**Оставить Keenable постоянным еженедельным слоем, но узким, и одновременно добавить в реестр 5 сайтов из таблицы выше.**

- Регулярные афиши (King's, West Road/CUMS, забеги, Royston Museum, рынки St Neots) дешевле и надёжнее собирать коллекторами: у них стабильная структура, а поиск даёт ошибки в датах (из 239 будущих событий, извлечённых из сниппетов, 10 оказались в базе на другую дату, у King's модель «размножила» один листинг на все воскресенья).
- Поиск незаменим там, где регулярного источника нет: **открытия** (12 подтверждённых пропусков против 6, которые уже были в базе, — самая большая относительная дыра), **даты ежегодных событий за Cloudflare** (Town & Gown), **первоисточник для газетных пунктов** (66% находятся, см. п. 5) и **провайдеры детских программ** для 6c.
- Предлагаемый еженедельный набор (этап 8): 15 запросов об открытиях, 20 по городкам зоны, запросы по ежегодным событиям, до которых меньше 8 недель и дата ещё не найдена, и по газетным пунктам недели — всего ~50–60 запросов в неделю, ~250 в месяц из 100 000 бесплатных. Разбор сниппетов Haiku — ~$0.05 за неделю на таком объёме (весь аудит этапа — $0.78 на 1041 страницу).
- Найденное поиском — только кандидаты: в базу идёт то, что подтверждено на странице нашим ботом (название + ближайшая дата), как в этом этапе (источник S148).

### Что исправлено по ходу этапа

- **Зона Питерборо по названию города.** postcodes.io `/places` отдаёт унитарный Питерборо как county, а не district, поэтому места без postcode в Питерборо и под ним получали «до часа, если важно» и уходили в `out_of_zone`. Исправлено в `geo.place` и в справочнике площадок: Great Eastern Run, The Gruffalo и Peppa Pig на Nene Valley Railway (Wansford) теперь «Кембриджшир, дальше часа».
- **Детские программы без postcode** получают зону по городу из адреса (Hinchingbrooke School → «до часа», The Peterborough School → «Кембриджшир, дальше часа»); раньше у них зоны не было.
- **Ссылка события — на первоисточник.** В `ingest.rank` газеты с ИИ-запретом идут последними, находки поиска S148 — перед ними: у 8 газетных событий основная ссылка теперь — страница площадки или продавца билетов (WeGotTickets для лекций в Openspace, Jockey Club для Simply Red, The Maltings для Around the World in 80 Days).
- **`--add-rubrics`** считал пункты перегенерируемой рубрики занятыми — исправлено.
- Параллельные скрипты этапа упирались в блокировку SQLite — у соединения теперь `timeout=60`.
## 5. Зависимость от газет с ИИ-запретом

Пункты, которые сейчас есть **только** в статьях Cambridge News (S004, S093), Cambridge Independent (S003, S092), Peterborough Telegraph (S010) и Newsquest (S116–S119): 23 будущих событий (дата ≥ 28.09) и 12 открытий/закрытий, всего **35**. Для каждого — запрос в Keenable (название + место + месяц); результаты с газетных сайтов и сайтов с ИИ-запретом отброшены до модели, совпадение с пунктом Haiku оценивал по заголовку и сниппету (`prompts/primary_match.md`), затем ручная проверка спорных оценок (`data/newspaper_primary_review.json`, 5 поправок).

| нашлось | пунктов | доля |
|---|---|---|
| на первоисточнике (площадка, организатор, бренд, ТЦ, совет) | 20 | 57% |
| только на агрегаторе | 3 | 9% |
| только в других СМИ (не первоисточник) | 5 | 14% |
| нигде, кроме газеты | 7 | 20% |

**Итог: 23 из 35 (66%) «газетных» пунктов находятся через первоисточник или агрегатор; теряется 12 (34%).** По режимам флага:
- `claude_user_only` (Newsquest): 14 пунктов, находится 10, теряется 4;
- газеты с запретом ботов обучения/поиска (S003, S004, S010, S092, S093): 21 пунктов, находится 13, теряется 8.
- Для 8 событий первоисточник дополнительно проверен на странице (название и ближайшая к нему дата) и добавлен к событию как ссылка S148 — теперь основная ссылка пункта ведёт на первоисточник, а не на газету.

<details><summary>Все газетные пункты</summary>

| пункт | дата | газета | нашлось | где | в реестре | заметка |
|---|---|---|---|---|---|---|
| Cambridge Carbon Footprint's Open Eco Homes | 2026-09-22 | S092 | primary | cambridgecarbonfootprint.org | — | Официальный сайт Cambridge Carbon Footprint подтверждает Open Eco Homes 2026 с датами 19 сентября по 18 октябр |
| Radiohead X Nosferatu: A Symphony of Horror | 2026-10-01 | S003 | primary | picturehouses.com | S045 | Picturehouses.com — официальный сайт кинотеатров, подтверждает событие; дата указана как 2 октября, что совпад |
| Digger | 2026-10-02 | S003 | primary | picturehouses.com | S045 | Фильм 'Digger' выходит 2 октября 2026 года, а результат 0 — это страница продажи билетов Picturehouse с подтве |
| Syd Barrett Exhibition: Life, Art and Cultural Imp | 2026-10-03 | S003 | primary | sydbarrett.com | — | Официальный сайт Syd Barrett подтверждает выставку о жизни, искусстве и культурном влиянии Сида Барретта в Ope |
| Clothes, Cake and Coffee Charity Sale | 2026-10-03 | S116 | aggregator | eventbrite.co.uk | S008,S055 | Eventbrite и Ouse Valley Radio подтверждают благотворительную распродажу одежды, кофе и торта 3 октября 2026 г |
| Cambridge South Public Exhibition | 2026-10-05 | S004,S092 | other_media | streamlinefeed.co.ke | — | Событие подтверждено несколькими новостными источниками с точной датой 5 октября 2026 года и местоположением S |
| Around the World in 80 Days | 2026-10-07 | S119 | primary | themaltingsely.org.uk | — | Событие подтверждено на официальном сайте The Maltings Ely с совпадающей датой 7 октября 2026 года и точным на |
| Talk by Rob Chapman - Syd Barrett: A Very Irregula | 2026-10-09 | S003 | primary | wegottickets.com | — | Билет на лекцию Rob Chapman о Syd Barrett подтверждён официальным продавцом билетов WeGotTickets с совпадающей |
| Talk and Film Outtakes by Roddy Bogawa | 2026-10-09 | S003 | primary | wegottickets.com | — | WeGotTickets подтверждает событие: лекция Roddy Bogawa о фильме про Syd Barrett с показом оuttakes 9 октября 2 |
| Have You Got It Yet? The Story of Syd Barrett and  | 2026-10-09 | S003 | other_media | neptunepinkfloyd.co.uk | — | Результат 0 подтверждает событие: фильм "Have You Got It Yet?" в Arts Picturehouse 9 октября в 20:30, но это н |
| Cambridge South Public Exhibition | 2026-10-10 | S004,S092 | other_media | streamlinefeed.co.ke | — | streamlinefeed.co.ke — перепечатка новостей, не агрегатор афиш |
| A Just Transition: Jobs, People, Planet | 2026-10-10 | S117 | none | — | — | Результаты показывают спектакль 'A Just Transition' в разных местах (Manchester, Bristol, Barnsley, London), н |
| Exhibition Duel | 2026-10-15 | S092 | none | — | — | Поиск не обнаружил подтверждения события 'Exhibition Duel' на 15 октября 2026 года; результаты содержат различ |
| Kerry Ellis's Rock Anthems tour | 2026-10-16 | S116 | primary | southhollandcentre.co.uk | — | Официальный сайт South Holland Centre подтверждает концерт Kerry Ellis 16 октября 2026 года в 19:30 на этой же |
| Halloween at Sacrewell | 2026-10-24 | S010 | primary | sacrewell.org.uk | — | Событие подтверждено на официальном сайте Sacrewell Farm с датой 25-31 октября 2026 года, включая хеллоуинские |
| The Gruffalo at Nene Valley Railway | 2026-10-25 | S117 | none | — | — | Поиск не обнаружил информацию о спектакле The Gruffalo на Nene Valley Railway на дату 25 октября 2026 года. |
| 12-hour indoor triathlon | 2026-10-27 | S116 | none | — | — | Результаты содержат информацию об отеле Delta Hotels by Marriott Huntingdon, но не подтверждают проведение 12- |
| Ely's Remembrance Sunday Parade | 2026-11-08 | S119 | primary | counties.britishlegion.org.uk | — | Официальный сайт отделения Британского легиона в Эли подтверждает парад Remembrance Sunday 8 ноября 2026 года  |
| Country in the Country | 2027-05-28 | S117 | aggregator | ibizabible.co.uk | — | ibizabible.co.uk — зеркало листинга Skiddle; сам Skiddle (S007/S129) событие пока не отдаёт |
| Peppa Pig at Nene Valley Railway | 2027-05-31 | S117 | none | nvr.org.uk | — | nvr.org.uk — календарь железной дороги, Peppa Pig 2027 на нём не назван: не подтверждено |
| Olly Murs at Newmarket Nights | 2027-06-25 | S116 | aggregator | discovernewmarket.co.uk | — | discovernewmarket.co.uk называет Olly Murs, но другую дату (18 августа вместо 25 июня 2027) — найден, дата рас |
| The Big Retreat Cambridgeshire 2027 | 2027-08-20 | S003 | none | — | — | Результаты показывают The Big Retreat в Abbots Ripton Estate, но на сентябрь 2026 года, а не август 2027, как  |
| Simply Red at Newmarket Nights | 2027-08-21 | S116 | primary | thejockeyclub.co.uk | S021,S022 | Событие подтверждено на официальном сайте The Jockey Club с точной датой 21 августа 2027 года на July Course,  |
| Rocker's Steakhouse | 2026-07-19 | S004 | none | — | — | Результаты содержат информацию о закрытии различных ресторанов, но ни один не упоминает конкретно Rocker's Ste |
| TG Jones | 2027-01-09 | S093 | other_media | wordupnews.com | — | Результат подтверждает закрытие TG Jones на Bridge Street в Peterborough 9 января 2027 года, но это новостной  |
| Tenpin | — | S004 | primary | publicnoticeportal.uk | — | Лицензионное уведомление от Peterborough City Council подтверждает открытие Tenpin в Queensgate; также упомина |
| Umami World Buffet | — | S004 | primary | rli.uk.com | — | Queensgate Shopping Centre (владелец/управляющая компания) опубликовала официальное объявление об открытии Uma |
| Greggs | — | S004 | other_media | wordupnews.com | — | Статья подтверждает планы открытия Greggs в Unit 7A Cambridge Leisure Park на Clifton Way с предложенным графи |
| Tenpin | — | S116 | primary | publicnoticeportal.uk | — | Официальное уведомление Пeterborough City Council подтверждает открытие Tenpin в Queensgate, Unit LU2, Lower L |
| The Three Horseshoes | — | S004 | primary | threehorseshoesmadingley.co.uk | — | сайт паба есть, но даты открытия на нём нет — первоисточник подтверждает место, не новость |
| The Crown | — | S004 | primary | crownfordham.pub | — | The Crown в Fordham, Ely переоткрылся в ноябре 2025 года после пожара в 2023 году, подтверждено официальным са |
| KFC | — | S116 | primary | kfc.co.uk | — | KFC на Great North Road в St Neots существует и работает, но дата открытия не подтверждена в результатах. |
| Lake View Bereavement Centre | 2026-09-11 | S004 | primary | eastcambs.gov.uk | S099 | Официальный сайт совета (East Cambridgeshire District Council) подтверждает открытие центра, хотя дата в пресс |
| UNIQLO | 2026-09-24 | S093 | primary | uniqlo.com | — | UNIQLO официальный сайт подтверждает открытие магазина в Grand Arcade на St Andrew's Street в Кембридже 24 сен |
| UNIQLO | 2026-09-24 | S116 | primary | uniqlo.com | — | UNIQLO официальный сайт подтверждает открытие магазина в Grand Arcade, Cambridge 24 сентября 2026 года. |

</details>

## Провайдеры детских программ и лагерей (для этапа 6c)

29 запросов (каникулярные лагеря и клубы, спорт, плавание, драма, STEM, лесные школы, HAF, справочник семейных услуг, спорт университетов, частные школы, городки зоны). После отсева шума — **75 сайтов**, из них 65 провайдеров и 10 справочников/туристических сайтов; 13 уже есть в срезе 6-v4; закрыто для бота — 8. Полный список с типом, каникулами и robots.txt — `data/kids_providers.json`.

По типам: справочник — 8, каникулярный клуб — 7, частная школа — 4, гимнастика — 4, верховая езда — 4, теннис — 3, плавание — 3, театр/драма — 3, национальный оператор лагерей — 3, совет — 3, лесная школа — 2, платформа записи — 2, спортивные лагеря — 2, танцы — 2, футбол — 2, туристический сайт — 2, агрегатор каникулярных клубов — 1, футбольный клуб — 1, агрегатор детских занятий — 1, парк — 1, площадка бронирования спортобъектов — 1, оператор досуговых центров — 1, университет — только дети сотрудников и студентов — 1, музыка — 1, конструирование — 1, музей — 1, частная школа — спорт-центр — 1, частная школа — летняя школа — 1, спорт университета — 1, искусство — 1, оператор каникулярных клубов — 1, оператор лагерей — 1, единоборства — 1, скалодром — 1, фитнес-клуб — 1, National Trust — 1, оператор бассейнов и спортцентров — 1.

Сайты, где поиск упоминал октябрьские или рождественские программы и которых нет в срезе, — 17; страницы проверены (robots.txt, текст страницы → Haiku, только то, что написано):

| провайдер | тип | результат |
|---|---|---|
| Butterflies Forest School | лесная школа | на странице нет дат на эти каникулы |
| COME and PLAY HOLIDAY CLUB | каникулярный клуб | на странице нет дат на эти каникулы |
| Culford | частная школа (Бери) | 1 программ(ы) на октябрь/Рождество на странице |
| Fireflies Forest School | лесная школа | на странице нет дат на эти каникулы |
| Mike's Tennis Academy | теннис | ошибка загрузки: HTTP 202 https://mikestennis.com/holiday-camps |
| Cambridge Lawn Tennis Club | теннис | ошибка загрузки: ConnectError: [Errno 104] Connection reset by peer |
| Cambridge City FC | футбольный клуб | на странице нет дат на эти каникулы |
| S4 Swim School | плавание | на странице нет дат на эти каникулы |
| Dramatic Moments | театр/драма | на странице нет дат на эти каникулы |
| Dramatic Moments | агрегатор детских занятий (Hoop) | на странице нет дат на эти каникулы |
| University of Cambridge | площадка бронирования спортобъектов | на странице нет дат на эти каникулы |
| Kettle's Yard | музей | ошибка загрузки: ProxyError: 502 Bad Gateway |
| Primary Sports Stars | платформа записи (Pebble) | 1 программ(ы) на октябрь/Рождество на странице |
| Tsa Sports | спортивные лагеря | на странице нет дат на эти каникулы |
| West Suffolk Council | совет | на странице нет дат на эти каникулы |
| 020.co.uk | справочник | — |
| Barracudas Activity Day Camps | туристический сайт | — |

В `kids_programmes` добавлены K24 (Culford, октябрьские каникулы, 5–12 лет — проверено, без цены и часов) и K25 (Primary Sports Stars, Mildenhall — не проверено: страница записи без JavaScript пустая).

<details><summary>Все провайдеры</summary>

| провайдер | сайт | тип | каникулы | robots.txt | в срезе 6-v4 |
|---|---|---|---|---|---|
| Butterflies Forest School | butterfliesforestschool.co.uk | лесная школа | окт, Рожд, фев, Пасха, май, лето | открыт |  |
| COME and PLAY HOLIDAY CLUB | comeandplay-holidayclub.co.uk | каникулярный клуб | окт, Рожд, фев, Пасха, май, лето | открыт |  |
| Culford | culford.co.uk | частная школа (Бери) | окт, Рожд, фев, Пасха, май, лето | открыт |  |
| Fireflies Forest School | firefliesforestschool.co.uk | лесная школа | окт, Рожд, фев, Пасха, май, лето | открыт |  |
| Mike's Tennis Academy | mikestennis.com | теннис | окт, Рожд, фев, Пасха, май, лето | открыт |  |
| Cambridge Lawn Tennis Club | cambridgeltc.com | теннис | окт, Рожд, фев, Пасха, май | открыт |  |
| Active Play Education | clubhubuk.co.uk | агрегатор каникулярных клубов (Club Hub UK) | окт, Пасха, май, лето | открыт | да |
| Cambridge City FC | cambridgecityfc.com | футбольный клуб | окт, фев, Пасха, май | открыт |  |
| S4 Swim School | s4swimschool.uk | плавание | окт, Пасха, май, лето | открыт |  |
| Dramatic Moments | dramaticmoments.co.uk | театр/драма | Рожд, лето, в четверть | открыт |  |
| Premier Education | premier-education.com | национальный оператор лагерей | фев, Пасха, в четверть | открыт | да |
| Dramatic Moments | hoop.co.uk | агрегатор детских занятий (Hoop) | Рожд, лето | открыт |  |
| Gymfinity Kids | gymfinitykids.com | гимнастика | Пасха, май | открыт | да |
| Kings Camps | kingscamps.org | национальный оператор лагерей | Пасха, лето | открыт |  |
| Nene Park | nenepark.org.uk | парк (Питерборо) | май, лето | закрыт для бота | да |
| The Young Actors Company | theyoungactorscompany.com | театр/драма | Пасха, лето | открыт |  |
| University of Cambridge | pitchgurus.co | площадка бронирования спортобъектов | окт, лето | открыт |  |
| Vivacity | vivacity.org | оператор досуговых центров (Питерборо) | май, лето | открыт |  |
| Cambridge Gymnastics Academy | cambridgegymnastics.co.uk | гимнастика | окт | открыт | да |
| Childcare Services | childcare.admin.cam.ac.uk | университет — только дети сотрудников и студентов | лето | закрыт для бота | да |
| Chorus Music Therapy | chorusmusictherapy.co.uk | музыка | Пасха | закрыт для бота |  |
| Kapla Clubs UK | kaplaclubs.co.uk | конструирование (Kapla) | лето | открыт |  |
| Kettle's Yard | kettlesyard.cam.ac.uk | музей | окт | открыт |  |
| King's College School Cambridge | kcs.cambs.sch.uk | частная школа | лето | открыт |  |
| Primary Sports Stars | activities.bookpebble.co.uk | платформа записи (Pebble) | окт | открыт |  |
| The Little Gym | cambridge.thelittlegym.co.uk | гимнастика | лето | открыт |  |
| The Perse Sports Centre | sportscentre.perse.co.uk | частная школа — спорт-центр | май | открыт |  |
| The Perse Summer School | persesummerschool.co.uk | частная школа — летняя школа | Пасха | открыт |  |
| Tsa Sports | tsasports.co.uk | спортивные лагеря | окт | открыт |  |
| University of Cambridge Sport | sport.cam.ac.uk | спорт университета | фев | закрыт для бота | да |
| West Suffolk Council | haverhill-tc.gov.uk | совет | Рожд | открыт |  |
| Wild @ Art | wild-at-art-workshops.classforkids.io | искусство | Пасха | открыт |  |
| A1 Fun Club | a1funclub.co.uk | каникулярный клуб | — | открыт |  |
| Active Play Education | activeplayeducation.co.uk | оператор каникулярных клубов | — | открыт |  |
| Adventure Camps | adventure-camps.co.uk | оператор лагерей | — | открыт |  |
| Aquastars | aquastarsorg.co.uk | плавание | — | открыт |  |
| Barracudas | barracudas.co.uk | национальный оператор лагерей | — | открыт | да |
| Cambridge and District Riding Club | canddrc.org.uk | верховая езда | — | открыт |  |
| Cambridge Kids Club | cambridgekidsclub.com | каникулярный клуб | — | закрыт для бота | да |
| Cambridge Kung Fu | cambridgekungfu.com | единоборства | — | открыт |  |
| Cambridge Lawn Tennis Club | clubspark.lta.org.uk | теннис (платформа LTA) | — | закрыт для бота |  |
| Cambridgeshire Council | cambridgeshire.gov.uk | совет (HAF, Family Information Directory) | — | открыт | да |
| classforkids.io | classforkids.io | платформа записи (Class For Kids) | — | открыт |  |
| Clip 'n Climb Cambridge | clipnclimbcambridge.co.uk | скалодром | — | открыт |  |
| David Lloyd Clubs | davidlloyd.co.uk | фитнес-клуб (детские лагеря) | — | открыт |  |
| Dreamweaver Gymnastics | dreamweavergymnastics.com | гимнастика | — | открыт |  |
| Elite Swimming Academy | eliteswimmingacademy.co.uk | плавание | — | открыт |  |
| Formations Dance Company | formationsdance.co.uk | танцы | — | открыт |  |
| Fun Times Cambridgeshire | funtimeschildcare.com | каникулярный клуб | — | открыт |  |
| GK Fit Ltd | gkfit.co.uk | спортивные лагеря | — | открыт |  |
| Kids Club Ely | kidsclubely.co.uk | каникулярный клуб | — | открыт |  |
| Monach Farm Horse Riding Stables | monachriding.co.uk | верховая езда | — | открыт |  |
| National Trust | nationaltrust.org.uk | National Trust | — | открыт |  |
| Newborough Kidz Club | newboroughkidzclub.co.uk | каникулярный клуб | — | открыт |  |
| Parkside Pools And Gym | better.org.uk | оператор бассейнов и спортцентров (GLL/Better) | — | открыт | да |
| peterborough.gov.uk | peterborough.gov.uk | совет (HAF) | — | открыт |  |
| Sawston Riding School | horseridinguk.co.uk | верховая езда (справочник) | — | закрыт для бота |  |
| South Cambridgeshire Equestrian Centre | scec.co.uk | верховая езда | — | открыт |  |
| Stardust Dance Academy | stardustdanceacademy.com | танцы | — | открыт |  |
| Stephen Perse | stephenperse.com | частная школа | — | открыт |  |
| Strike Academy | strikeacademy.classforkids.io | футбол | — | открыт |  |
| The Football Fun Factory | thefootballfunfactory.co.uk | футбол | — | закрыт для бота | да |
| The Leys | theleys.net | частная школа | — | открыт |  |
| Theatretrain | theatretrain.co.uk | театр/драма | — | открыт |  |
| TJKids | tjkids.co.uk | каникулярный клуб | — | открыт |  |
| 020.co.uk | 020.co.uk | справочник | окт, фев, Пасха, май, лето | открыт |  |
| Cambridge City FC | visitsouthcambs.co.uk | туристический сайт | май, лето | открыт |  |
| Farmlings Forest School | eequ.org | справочник (Suffolk) | Пасха, лето | открыт | да |
| Barracudas Activity Day Camps | visitcambridge.org | туристический сайт | окт | открыт |  |
| all4kidsuk.com | all4kidsuk.com | справочник | — | открыт |  |
| dayoutwiththekids.co.uk | dayoutwiththekids.co.uk | справочник | — | открыт |  |
| familiesonline.co.uk | familiesonline.co.uk | справочник | — | открыт |  |
| mumsguideto.co.uk | mumsguideto.co.uk | справочник | — | открыт |  |
| netmums.com | netmums.com | справочник | — | открыт |  |
| ukcollegeholidays.co.uk | ukcollegeholidays.co.uk | справочник | — | открыт |  |

</details>

## Выпуск v5 (1–11 октября)

Файлы: `issues/issue_2026-10-01_v5_ru.md` / `_en.md` (с блоком «Для редактора»), читательские
`_v5_reader_ru.html` / `_en.html`, редакторские `_v5_editor_ru.html` / `_en.html`; ответ модели — `_v5_model.json`.
HTML проверены в headless Chromium на ширине 390 и 1200 px: горизонтальной прокрутки нет, в редакторской версии
16 списков под катом, по умолчанию свёрнуты.

### Пункты по рубрикам

| рубрика | v5 | v4 |
|---|---|---|
| Тема недели (Сид Барретт) | 5 | 4 |
| Главное на выходные 3–4 октября | 3 | 4 |
| Главное на выходные 10–11 октября | 3 | 4 |
| На неделе: концерты, театр, комедия | 4 | 5 |
| Выставки | 3 | 4 |
| Бесплатно | 2 | 3 |
| С детьми | 3 | 4 |
| Спорт (из них «Поучаствовать» — 4) | 5 | 2 |
| За городом (до часа) | 2 | 6 |
| По графству | 0 — скрыта | 1 |
| Новые анонсы | 2 | 4 |
| Успейте купить билеты | 3 | 4 |
| Отменено и перенесено | 1 | 1 |
| Новое в городе | 5 | 5 |
| **основная часть** | **41** | **51** |
| Каникулы: куда записать ребёнка (строк) | 22 | 22 пункта с абзацами |

Из находок 6b в выпуске: Town & Gown 10K, Abington Festival of Running, Grafham Water Trail Races и Great Eastern Run
(«Спорт → Поучаствовать»); в «Каникулах» — Culford (K24). У трёх пунктов, которые раньше вели на газету, ссылка теперь
на первоисточник: лекция Rob Chapman и встреча с Roddy Bogawa (WeGotTickets), Simply Red (Jockey Club). Остальные
41 подтверждённые находки — в базе и в редакторской версии под катом своих рубрик: модель их не взяла, потому что у
них низкая оценка важности (2–4: один источник, вместимость неизвестна). Например, бесплатный органный концерт Paul
Greally в King's 11.10 — в «Бесплатно» с причиной «вытеснен более сильными».

### Как применены «Редакционные правки по черновику v4»

- **Длина.** Основная часть — 41 пункт (цель 30–45, в промпте — не больше 42). Если модель даст больше 45, `build_issue.trim` уберёт самые слабые пункты по оценке в рубриках, где их больше двух («Тема недели», «Главное» и «Новое в городе» не сокращаются). В v5 сокращать не понадобилось.
- **«Каникулы» — компактно и без модели.** Одна строка на программу: провайдер — что (возраст) — даты · место · цена, название — ссылка. Группировка по каникулам, внутри — по зоне (Кембридж → до 30 мин → дальше). Одинаковые программы одного провайдера — одной строкой со списком площадок; если цены на площадках разные, цена стоит при каждой площадке (Better: Parkside Pools и Abbey). Короткие тексты на двух языках хранятся в `data/kids_programmes.json` (`text`) — рубрика больше не стоит токенов модели.
- **Состав участников — полностью.** Состав извлекается из описаний всех склеенных записей (`pipeline/lineup.py`, Haiku, кэш `lineup_cache`; участники группы, которая сама стоит в афише, отдельными исполнителями не считаются). Проверка ответа дописывает недостающие имена («Также в программе: …») и пишет об этом редактору. В v5 у концерта Барретта названы Kula Shaker, Soft Machine и The Mad Alchemist (световое шоу); недостающих имён проверка не нашла.
- **«Успейте купить билеты» — только билеты для зрителей.** Забеги, триатлоны и челленджи помечаются `participant` (по названию, а для «run/race/walk» — если в описании есть регистрация или категория «спорт») и идут в «Спорт → Поучаствовать». 12-часовой триатлон в Хантингдоне в «Билеты» не попал (и в «Спорт» тоже — он 27 октября, за окном).
- **Пустые описания запрещены по-настоящему.** Кандидаты без содержательных фактов помечаются `thin_data` (в описании источников меньше 8 слов сверх названия, нет исполнителя) — модель их не берёт. Проверка ответа убирает пункты с шаблонным описанием («A new café has opened», «Race day», «Home league match») или меньше чем тремя словами сверх названия. В v5 «День скачек» (Sun Chariot Day, Dubai Future Champions) и матчи Peterborough отсеяны ещё моделью, проверке убирать было нечего.
- **«По графству» — порог 5 и без единственного матча лиги.** Кандидатов с оценкой ≥ 5, кроме обычного матча Peterborough, не нашлось — рубрика скрыта.

### Редакторская версия

Под каждой рубрикой — `<details>` «Все события рубрики — N (в выпуске M)» со всеми кандидатами окна, отсортированными
по оценке: название-ссылка, дата и время, площадка и зона, цена, оценка, источники; пункты выпуска отмечены ✓, у
остальных причина: в выпуске в другой рубрике / ниже порога / вытеснен более сильными / лимит рубрики / длительная
выставка / Кембриджшир дальше часа ниже 8 / распродажа / регистрация участников / мало данных для описания / дубль /
сокращено по длине. Рубрики, которых нет в выпуске («По графству»), показаны заглушкой со списком. Для «Каникул» —
все 25 программ (в выпуске 24 — 22 строки, две пары склеены по провайдеру; K25 не проверена), ещё 9 провайдеров,
не проверенных на сайте, и 5 отброшенных — с причиной. В конце — «Не попало никуда» (события окна вне
всех рубрик, исключённые до отбора: вне зоны, evergreen, без площадки, распроданные) и блок «Для редактора».

### Замер по ИИ-запретам (для решения на этапе 8)

Из 41 пункта основной части:
- только из источников с запретом `Claude-User` (Newsquest S116–S119) — **1**: Olly Murs at Newmarket Nights → пропадёт в режиме `claude_user_only`;
- только из источников с запретом ботов обучения/поиска (S003, S004, S010, S092, S093) — **4**: выставка о Сиде Барретте, Open Eco Homes, публичная выставка Cambridge South, The Big Retreat 2027;
- в режиме `any_ai_agent` пропадут **6** (ещё UNIQLO: открытие есть только в статьях Cambridge News и Hunts Post; сайт бренда поиск нашёл, но ссылка к записи «Новое в городе» пока не привязывается).
- Без ссылок на первоисточники, найденных поиском (S148), было бы 1 и 8 — поиск вернул 2 пункта (лекции в Openspace).
- Для сравнения, v4: 2 / 6 / 9 из 73.

Флаг `respect_ai_disallow` = `off`.

### На что посмотреть

- **Town & Gown 10K (оценка 7.0) — не в «Главном на выходные».** Правило «≥ 7 на выходных — всегда в Главном» сработало бы, но это забег с регистрацией участников, и он стоит в «Спорт → Поучаствовать»; проверка ответа отметила это в «Для редактора». Если хотите, чтобы крупные забеги с болельщиками шли в «Главное», — это правило надо уточнить.
- Great Eastern Run: сайт организатора закрыт для нашего бота, ссылка — страница события на findarace. «Один из крупнейших забегов региона» — из знаний модели, вынесено редактору.
- «Бесплатно» (2), «За городом» (2), «Новые анонсы» (2) — меньше трёх: модель предпочла сократить, а не добивать слабыми пунктами (по брифу допустимо).
- Семь пунктов с оценкой ≥ 8 описаны одним длинным предложением (как в v4) — отмечено в «Для редактора».
## Расход

| Keenable | запросов | успешных | результатов |
|---|---|---|---|
| gap_audit | 100 | 100 | 1000 |
| gap_primary | 3 | 3 | 18 |
| kids_providers | 29 | 29 | 290 |
| newspaper_primary | 40 | 40 | 400 |
| тестовый запрос (до клиента) | 1 | 1 | 5 |
| **итого** | **173** |  |  |

Бесплатный лимит Keenable — 100 000 запросов в месяц: этап израсходовал 173 (0.17% месячного лимита). Ответы закэшированы — повторный прогон аудита запросов не тратит.

| Claude API — назначение | модель | запросов | вход | выход | $ |
|---|---|---|---|---|---|
| issue 2026-10-01_v5 | claude-sonnet-5 | 2 | 177226 | 78568 | 1.1401 |
| search_extract | claude-haiku-4-5 | 87 | 363665 | 83773 | 0.7825 |
| issue 2026-10-01_v5 add sport | claude-sonnet-5 | 1 | 68004 | 4449 | 0.1805 |
| newspaper_primary | claude-haiku-4-5 | 41 | 82969 | 3941 | 0.1027 |
| importance | claude-sonnet-5 | 2 | 10418 | 5229 | 0.0731 |
| kids_providers | claude-haiku-4-5 | 14 | 61357 | 421 | 0.0635 |
| lineup | claude-haiku-4-5 | 58 | 24643 | 838 | 0.0288 |
| venue_locate | claude-haiku-4-5 | 11 | 12661 | 921 | 0.0173 |
| **итого** |  | 216 |  |  | **2.3885** |

Выпуск v5 собирался дважды ($0.56 + $0.58): после первой сборки выяснилось, что описания находок 6b — фрагменты страниц со скриптами; описания пересобраны из чистого текста, выпуск собран заново, первый ответ не используется. «add sport» — пересборка одной рубрики после исправления Town & Gown 10K.
Всего за проект: $9.50.
