# Этап 2 — прогон коллекторов (2026-09-27)

Сырые события: `data/raw/<ID>_<модуль>.json`, сводка прогона: `data/raw/_run.json`.

## Сколько дал каждый источник

| ID | Источник | Статус | События | из них будущих | Записи фидов | Запросов | Секунд | Примечание |
|---|---|---|---|---|---|---|---|---|
| S005 | Cambridge 105 | ok | 22 | 22 | 30 | 3 | 8.7 |  |
| S047 | talks.cam | ok | 62 | 62 | 0 | 6 | 53.9 |  |
| S042 | ADC Theatre (Camdram) | ok | 28 | 28 | 0 | 2 | 3.4 |  |
| S018 | Cambridge United (fixtur.es) | ok | 188 | 21 | 0 | 2 | 3.1 |  |
| S032 | Cambridge Beer Festival | ok | 2 | 2 | 0 | 2 | 3.6 |  |
| S003 | Cambridge Independent | ok | 0 | 0 | 20 | 2 | 3.0 |  |
| S004 | Cambridge News | ok | 0 | 0 | 35 | 3 | 5.0 |  |
| S002 | What's On In Cambridge | ok | 0 | 0 | 10 | 2 | 7.1 |  |
| S087 | The Cambridge Foodies | ok | 0 | 0 | 10 | 2 | 3.7 |  |
| S050 | Fitzwilliam Museum | ok | 0 | 0 | 20 | 2 | 3.2 |  |
| S038 | Mill Road Winter Fair | ok | 1 | 1 | 0 | 3 | 7.0 |  |
| S006 | Ents24 | ok | 37 | 37 | 0 | 2 | 3.8 |  |
| S007 | Skiddle | ok | 49 | 49 | 0 | 2 | 2.4 |  |
| S021 | Newmarket Racecourses | ok | 14 | 14 | 0 | 2 | 3.1 |  |
| S011 | Cambridge Corn Exchange | ok | 74 | 74 | 0 | 80 | 217.0 | links: 74, fetch_errors: 0, no_jsonld: 0 |
| S033 | Strawberry Fair | ok | 1 | 0 | 0 | 2 | 3.1 |  |
| S072 | Cambridge City Events | ok | 4 | 4 | 0 | 7 | 17.9 | links: 4, fetch_errors: 0, no_jsonld: 0 |
| S008 | Eventbrite | ok | 99 | 99 | 0 | 6 | 19.3 |  |
| S091 | Cambridge Live Tickets | ok | 93 | 93 | 0 | 99 | 260.8 | links: 93, fetch_errors: 0, no_jsonld: 0 |

Итого: 674 событий и 125 записей фидов; упало коллекторов: 0 из 19.

## Контрольные события

| ID | Событие | Когда | Найдено | Где |
|---|---|---|---|---|
| C1 | Домашние матчи Cambridge United | весь сезон | да — 21 будущих домашних | S018: 2026-10-06 Northampton Town FC [EFLT], 2026-10-10 Blackpool FC, 2026-10-20 Wycombe Wanderers FC, 2026-10-24 Plymouth Argyle … |
| C2 | Mill Road Winter Fair | 2026-12-05 | да — 1 | S038 event 2026-12-05: Mill Road Winter Fair 2026 |
| C3 | Town and Gown 10k | октябрь 2026 | **нет** | — |
| C4 | Whittlesea Straw Bear Festival | январь 2027 | **нет** | — |
| C5 | Thriplow Daffodil Weekend | март 2027 | **нет** | — |
| C6 | Публичные лекции talks.cam | постоянно | да — 62 будущих | CamTalks: 55; Featured talks: 15; Major Public Lectures in Cambridge: 8; Darwin College Lecture Series: 8; Cabinet of Natural History: 7 |
| C7 | Открытия на Mill Road: Catte Latte, Hungarian Soul | уже прошли (архив) | **нет** | — |
| C8 | Cambridge Oktoberfest, Jesus Green | 2026-09-25 – 2026-09-26 | **нет** | —<br>похожие, но не то: S007 event 2026-10-17: Oktoberfest Newmarket 2026; S007 event 2026-10-24: Oktoberfest Bishop's Stortford 2026 |

## Заполненность полей (только события)

| ID | Событий | start | venue | postcode | url | price | status |
|---|---|---|---|---|---|---|---|
| S005 | 22 | 100% | 100% | 91% | 100% | 82% | 0% |
| S047 | 62 | 100% | 71% | 6% | 100% | 0% | 0% |
| S042 | 28 | 100% | 100% | 100% | 100% | 0% | 0% |
| S018 | 188 | 100% | 100% | 100% | 100% | 0% | 100% |
| S032 | 2 | 100% | 100% | 100% | 100% | 0% | 0% |
| S038 | 1 | 100% | 100% | 0% | 100% | 0% | 0% |
| S006 | 37 | 100% | 100% | 100% | 100% | 49% | 100% |
| S007 | 49 | 100% | 100% | 100% | 100% | 88% | 100% |
| S021 | 14 | 100% | 100% | 0% | 100% | 50% | 0% |
| S011 | 74 | 100% | 96% | 96% | 100% | 0% | 100% |
| S033 | 1 | 100% | 100% | 0% | 100% | 0% | 100% |
| S072 | 4 | 100% | 25% | 25% | 100% | 0% | 100% |
| S008 | 99 | 100% | 100% | 95% | 100% | 0% | 0% |
| S091 | 93 | 100% | 99% | 98% | 100% | 0% | 100% |

## Ручные проверки и выводы по контрольным событиям

- **C3 Town and Gown 10k** — ни в новостях Cambridge News (35 записей), ни в Cambridge 105 (22 события + 30 новостей) сейчас не упоминается. Новостной фид отдаёт только последние записи, так что упоминание появится ближе к дате или уже ушло из фида. Сайт townandgown10k.com закрыт Cloudflare, обходить его не стали.
- **C4 Straw Bear (январь 2027), C5 Thriplow (март 2027)** — до событий 3–6 месяцев, афиши Cambridge 105 и других источников их пока не содержат. Не баг коллекторов; перепроверить в декабре и феврале.
- **C7 Catte Latte, Hungarian Soul** — в текущем RSS Foodies (10 последних постов) их нет. Архив доступен через фид поиска WordPress (`/?s=<запрос>&feed=rss2`, robots.txt разрешает): при ручной проверке нашлись обе статьи, «Hungarian Soul – Mill Road's first Hungarian café» — 29.07.2026. Для «новое в городе» в архиве нужна разовая выгрузка архива (`/feed/?paged=N`) с редкими запросами.
- **C8 Cambridge Oktoberfest** (25–26.09.2026) — прошёл за день до прогона. Билеты продавал Cambridge Live Tickets (S091), но страница события уже 404 и из списка удалена. Коллектор поймал бы его при запуске до 26.09. Вывод для этапа 3: хранить историю событий в базе, а не только текущий срез. В DesignMyNight раздел событий закрыт в robots.txt.
- **C2 Mill Road Winter Fair** — RSS ярмарки пуст. Дата (5.12.2026, 10:30–16:30) берётся строкой с главной страницы — добавлено в коллектор S038.
