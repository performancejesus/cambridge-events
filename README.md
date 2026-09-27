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
- Скрипт соблюдает robots.txt, делает паузу 2 с между запросами к одному хосту и представляется как `CambridgeEventsBot/0.1`.
