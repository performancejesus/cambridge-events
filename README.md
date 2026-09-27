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
