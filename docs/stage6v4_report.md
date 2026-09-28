# Этап 6-v4 — выпуск v4 для читателей (2026-09-28)

## Решения после этапа 6

- **Cambridge BID снова идёт в модель.** S097 убран из `NO_LLM_SOURCES` и добавлен в `ARTICLE_SOURCES`, записи «требует проверки» из заголовков удалены. 20 статей перепрогнаны пакетом Batch API за $0.034: 4 полезные, из них 4 события (новое одно). Открытий в них нет. Дальше BID подчиняется общему флагу.
- **Флаг `respect_ai_disallow` — три режима:** `off` / `claude_user_only` / `any_ai_agent` (`data/pipeline_config.json`, сейчас `off`). Старое булево значение тоже понимается. Источники по режимам (таблица `source_ai_policy`):
  - `claude_user_only` — S116–S119;
  - `any_ai_agent` — ещё S003, S004, S010, S092, S093.
- **«Вечнозелёные» предложения** (`pipeline/evergreen.py`, поле `events.evergreen`). Пометку ставим, если название похоже на туристический продукт (experience, murder mystery, quest, heist, городская игра, экскурсия), а событие длительное: началось больше 30 дней назад или идёт дольше 60 дней. Выставки пометку не получают. Помечено 4: Cambridge Murder Mystery, Wizard of Oz Experience, Discover Cambridge City Exploration Game, Bank Heist Experience. В выпуск они не идут.
- **Регулярные серии** (библиотеки: Rhymetime, Storytime) выводятся как «регулярные занятия — расписание по ссылке», без дат всей серии.
- **Дубли с годом в названии.** Год и так отбрасывался нормализацией. «Fungi Field Day» / «… 2026» не склеивались по другой причине: сам источник (UCM, Visit Cambridge) публикует событие дважды, а дедупликация не склеивает записи одного источника. Новый проход `ingest.merge_same` склеивает будущие события с одинаковыми датой, временем, площадкой и нормализованным названием. Склеено 6.

## Правки по черновику v3 — как применены в v4

- **Состав в «Теме недели».** Сводное описание обрезалось до 600 символов, и состав концерта (Kula Shaker, Soft Machine) был только в третьем описании. Лимит поднят до 1200, у кандидата появилось поле `performer`, а проверка ответа выносит в «Для редактора» пункт, где исполнитель не назван. В v4 Kula Shaker в тексте есть.
- **Порядок «Темы недели»** — по смыслу, как у модели: концерт → выставка → лекция → фильм. Отрисовка больше не сортирует тему по оценке. Матч United — Blackpool после правки футбола получил 5.5 и ушёл в «Спорт».
- **Футбол:** вместимость стадиона не учитывается, обычный матч лиги ограничен оценкой 6 (`football.league_max_score`). Дерби, кубки и соперник из Премьер-лиги — как раньше. United — Blackpool: 8.2 → 5.5, Peterborough — Notts County: 7.0 → 4.0.
- **«Кембриджшир, дальше часа» в «Главном»** — только от 8. **Длительные выставки** (дольше 14 дней) — новая рубрика «Выставки» (`exhibitions`), в «Главное» они не идут.
- **«За городом» и «По графству»** — от 4 и без распродаж/барахолок (`SALE_RE`).
- **«Новое в городе»** — в первом выпуске открытия за 2 месяца, в промпте 5–6 пунктов. В v4 их 5.
- **Проверка цен:** при расхождении подставляется цена из данных любого из склеенных кандидатов пункта, а не «цена не указана».

## Найдено при ревью v4 и исправлено

- **Цены Junction были неверны массово.** Общий разбор цены цеплял «save £4.50 per ticket» из рекламы членства, а настоящую цену «£ 29.50» (с пробелом после £) пропускал. Отсюда в базе было много £3–£4.50. Теперь цена берётся из поля «Price» блока события. Junction пересобран без кэша (260 страниц), в выпуске Tez Ilyas £4.50 → £29.50.
- **Модель пропустила две рубрики** («Каникулы» и «За городом») при сборке одним вызовом. Добавлен режим `build_issue.py --from-json … --add-rubrics holidays,out_of_town`: он догенерирует только нужные рубрики с учётом уже занятых пунктов и вмерживает их в сохранённый ответ ($0.27 вместо полной пересборки).
- **Ручные правки** (`manual_fixes` в `_v4_model.json`):
  - United — Blackpool: «благотворительный матч» → матч лиги, сборы которого пойдут на благотворительность (по проверенной заметке);
  - Martin Kemp: убран «DJ-сет из хитов 1980-х» — в данных этого нет.
- Проверка «оценка ≥ 8, а описание в одно предложение» сработала на 7 пунктах (Roachford, Amstell, Joe Jackson, Moyet, Hackett, Simply Red, Olly Murs): модель пишет одно длинное предложение. Для читателя это приемлемо, в блоке «Для редактора» отмечено.

## Читательская версия

`_v4_reader_ru.html` / `_v4_reader_en.html` собираются из той же структуры выпуска (`issue.layout`), что и Markdown, но без блока «Для редактора»:
- одна колонка шириной до 640 px, отступы 16 px, светлая и тёмная тема по настройке устройства;
- название пункта и «Подробнее →» — ссылки;
- без внешних ресурсов.

Проверено в headless Chromium на ширине 500 и 1200 px: горизонтальной прокрутки нет.

## Детские программы на каникулы (`kids_programmes`)

Даты каникул — сайт Cambridgeshire County Council: октябрьские 26–30 октября 2026, рождественские 21 декабря 2026 – 1 января 2027. Программы найдены веб-поиском и проверены на сайте провайдера (robots.txt уважается); данные — `data/kids_programmes.json`, таблица `kids_programmes` (схема этапа 6c).

- **октябрьские каникулы (26–30 октября)**: проверено на сайте — 17
- **рождественские (21 декабря – 1 января)**: проверено на сайте — 5
- **обе (университетская программа)**: проверено на сайте — 0, не проверено — 1

| ID | Каникулы | Провайдер | Программа | Возраст | Цена | Место | Для кого | Проверено |
|---|---|---|---|---|---|---|---|---|
| K01 | октябрьские каникулы | Premier Education | Multi-Activity Holiday Camp | school age | from £26.34 a day + £1.25 booking fee | The Cass Centre (Cambridge University Press) | все | да |
| K02 | октябрьские каникулы | Barracudas | School holiday camp (multi-activity: archery, fencing, dance…) | 4–14 | — | St Faith's School | все | да |
| K03 | октябрьские каникулы | Gymfinity Kids | Gymnastics holiday camp | 5–14 | — | Gymfinity Kids, Beehive Centre | все | да |
| K04 | октябрьские каникулы | Better (GLL) | Swim School holiday course (intensive half-term swimming) | children, by level | £45 for five days or £9 a lesson | Parkside Pools | все | да |
| K05 | октябрьские каникулы | Better (GLL) | Swim School holiday course (intensive half-term swimming) | children, by level | £42.50 for five days or £8.50 a lesson | Abbey Leisure Complex | все | да |
| K06 | октябрьские каникулы | Club Hub UK / Professor Fab's | October Half Term Science Camp (Potions Class) | 5–11 | £38 a session | Queen Edith Community Primary School | все | да |
| K07 | октябрьские каникулы | South Cambridgeshire District Council | Holiday camp: netball | Year 3 – Year 9 | £25 (£23 per child for siblings or several days) | Impington Sports Centre | все | да |
| K08 | октябрьские каникулы | Cambridge Past, Present & Future | Holiday Bushcraft | 5–14 | — | Wandlebury Country Park | все | да |
| K09 | октябрьские каникулы | The Outdoors Project | October half-term holiday clubs (outdoor games, bushcraft) | 5–12 (Year 1–6) | — | Cambridge & Royston sites | все | да |
| K10 | октябрьские каникулы | Milton Country Park | The Outdoor Project half-term sessions | — | — | Milton Country Park | все | да |
| K11 | октябрьские каникулы | Cambridge Science Centre | Half-term opening: 2-hour family visits, shows and lab-bench challenges | families | — | Cambridge Science Centre | все | да |
| K12 | октябрьские каникулы | Active Play Education | October half-term holiday club (Halloween crafts, forest school, bake off) | 4–12 | £27–£35 a session | Spring Meadow Infant School | все | да |
| K13 | октябрьские каникулы | Barracudas | October half-term holiday club | 4–14 | — | Hinchingbrooke School | все | да |
| K14 | октябрьские каникулы | Nene Park Trust | Holiday clubs at Ferry Meadows: Adventure (8–13) and Acorn Explorers (5–8) | 5–13 | £45 a day or £180 a week (8–13); £40 a day or £160 a week (5–8) | Lynch Farm, Ferry Meadows | все | да |
| K15 | октябрьские каникулы | Churchill Camps | Multi-activity day camp | — | £235 a week | The Peterborough School | все | да |
| K16 | октябрьские каникулы | Kick-Off Sports | Multi-sport holiday camp (Halloween theme) | 4–12 | £20 a day (£15 for a sibling) | Kick-Off Sports, Whittlesey area | все | да |
| K17 | октябрьские каникулы | School's Out Activities | Half-term day camps (Early Explorers, Creative Crew, Adrenaline Adventure, soccer) | 4–16 | — | School's Out, Bury St Edmunds | все | да |
| K18 | рождественские | Cambridgeshire County Council | HAF Christmas programme: funded holiday club places with a meal | primary and secondary | free for eligible families | clubs across Cambridgeshire | HAF: по критериям | да |
| K19 | рождественские | Peterborough City Council | HAF Christmas: funded holiday activity sessions | school age | free for eligible families | clubs across Peterborough | HAF: по критериям | да |
| K20 | рождественские | Premier Education | Multi-Activity Holiday Camp | school age | from £24.64 a day + £1.25 booking fee | The Cass Centre (Cambridge University Press) | все | да |
| K21 | рождественские | Churchill Camps | Christmas day camps | — | £235 for a full week (3-day camp price on booking) | The Peterborough School | все | да |
| K22 | рождественские | Cambridge Science Centre | Christmas holiday opening: 2-hour family visits | families | — | Cambridge Science Centre | все | да |
| K23 | обе | University of Cambridge Childcare Office | University Holiday Playscheme | Reception – 12 | — | Trumpington Meadows Primary School | дети сотрудников и студентов университета | нет |

Не проверены (сайт закрыт для бота или без дат) — в выпуск не взяты:

- Cambridge Kids Club — holiday playscheme — robots.txt отвечает 403
- Sport at Cambridge — children's athletics camps — robots.txt отвечает 403
- Cambridge United soccer schools — robots.txt отвечает 403
- Cambridge Gymnastics Academy — October half-term camp — сайт отдаёт заглушку (202, без содержимого) — похоже на защиту от ботов
- Multi-Active (Huntingdon & St Ives) — ошибка сертификата TLS
- Kids R Us holiday club — соединение обрывается
- The Football Fun Factory (Kelsey Kerridge) — соединение обрывается
- Stagecoach Cambridge — holiday workshops — дат на странице нет
- Level Up — youth athletic programme — регулярная программа 10–18 лет; дат на эти каникулы на странице нет (были сессии в майские)

Отброшены при проверке:

- Ultimate Activity Cambridge — октябрь 2026 — «not available»
- Kings Camps (The Perse) — нет дат на этой площадке, только лето
- One Leisure St Neots holiday club — на странице только летние даты
- Barracudas Ely — только Пасха и лето
- SuperCamps — в Кембриджшире площадок нет

## Выпуск v4 (1–11 октября)

`issues/issue_2026-10-01_v4_en.md`, `_ru.md` — с блоком «Для редактора»; `_v4_reader_en.html`, `_v4_reader_ru.html` — читательские версии без него (одна колонка «как письмо», светлая и тёмная тема, кликабельные ссылки); ответ модели — `_v4_model.json`.

Пунктов по рубрикам:

- Тема недели: 4
- Главное на выходные 3–4 октября: 4
- Главное на выходные 10–11 октября: 4
- На неделе: концерты, театр, комедия: 5
- Выставки: 4
- Бесплатно: 3
- С детьми: 4
- Каникулы: куда записать ребёнка: 22 ⚠️ больше 6
- Спорт: 2 ⚠️ меньше 3
- За городом (до часа): 6
- По графству: 1 ⚠️ меньше 3
- Новые анонсы: 4
- Успейте купить билеты: 4
- Отменено и перенесено: 1 ⚠️ меньше 3
- Новое в городе: 5
- всего: 73 (цель 25–40)

В «Каникулах»: октябрьские — 16 пунктов (17 программ: The Outdoors Project и его сессии в Milton Country Park — один пункт), рождественские — 5, на все каникулы — 1 (University Holiday Playscheme, только для детей сотрудников и студентов университета; сайт закрыт для бота — с пометкой «подробности на сайте»).
Без «Каникул» в выпуске 51 пунктов — больше цели 30–45: модель заполнила новые рубрики «Выставки» и «За городом» и не сократила остальные; для рассылки стоит убрать 6–8 слабых пунктов (редакторское решение).

## Замер по ИИ-запретам (для решения на этапе 8)

Из 73 пунктов выпуска:
- только из источников с запретом `Claude-User` (Newsquest S116–S119) — **2**: Olly Murs at Newmarket Nights; 12-hour indoor triathlon → пропадут в режиме `claude_user_only`;
- только из источников с запретом ботов обучения/поиска (S003, S004, S010, S092, S093) — **6**: Syd Barrett Exhibition: Life, Art and Cultural Impact; Rob Chapman: Syd Barrett – A Very Irregular Head; Meet the Director + Screening: Have You Got It Yet?; Open Eco Homes; Cambridge South Public Exhibition; The Big Retreat Cambridgeshire 2027;
- в режиме `any_ai_agent` пропадут **9** (всё, что пришло только из этих газет).

Флаг `respect_ai_disallow` = `off` (режимы: off / claude_user_only / any_ai_agent).

## Расход Claude API на этап

| Назначение | Модель | Запросов | $ |
|---|---|---|---|
| issue 2026-10-01_v4 | claude-sonnet-5 | 1 | 0.5858 |
| issue 2026-10-01_v4 add holidays,out_of_town | claude-sonnet-5 | 1 | 0.2733 |
| article_extract_batch | claude-haiku-4-5 | 20 | 0.0342 |
| importance | claude-sonnet-5 | 1 | 0.0074 |
| **итого** | | | **0.9007** |

Выпуск: claude-sonnet-5: 151576 input + 55598 output tokens = $0.8591. Всего за проект: $7.11.
