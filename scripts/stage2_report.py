"""Этап 2: отчёт по прогону коллекторов и поиск контрольных событий → docs/stage2_report.md."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CONTROLS = ROOT / "data" / "control_events.json"
REPORT = ROOT / "docs" / "stage2_report.md"
NOTES = ROOT / "docs" / "stage2_notes.md"  # ручные проверки — дописываются в отчёт как есть
TODAY = date.today().isoformat()


def load_events() -> list[dict]:
    out = []
    for f in sorted(RAW.glob("S*.json")):
        out += json.loads(f.read_text())
    return out


def when(e: dict) -> str:
    return (e.get("start") or e.get("published") or "")[:10]


def esc(t) -> str:
    return str(t).replace("|", "\\|").replace("\n", " ")


def main() -> None:
    run = {k: v for k, v in json.loads((RAW / "_run.json").read_text()).items() if not k.startswith("_")}
    events = load_events()
    lines = [f"# Этап 2 — прогон коллекторов ({TODAY})", "",
             "Сырые события: `data/raw/<ID>_<модуль>.json`, сводка прогона: `data/raw/_run.json`.", "",
             "## Сколько дал каждый источник", "",
             "| ID | Источник | Статус | События | из них будущих | Записи фидов | Запросов | Секунд | Примечание |",
             "|---|---|---|---|---|---|---|---|---|"]
    by_src = Counter()
    fut_src = Counter()
    for e in events:
        if e["kind"] == "event":
            by_src[e["source_id"]] += 1
            if when(e) >= TODAY or (e.get("end") or "")[:10] >= TODAY:
                fut_src[e["source_id"]] += 1
    for sid, r in run.items():
        note = r.get("error", "")
        if r.get("stats"):
            note = ", ".join(f"{k}: {v}" for k, v in r["stats"].items())
        lines.append(f"| {sid} | {esc(r['name'])} | {'ok' if r['ok'] else '**упал**'} | {r.get('events', '—')} | "
                     f"{fut_src.get(sid, 0) if r['ok'] else '—'} | {r.get('articles', '—')} | {r['requests']} | "
                     f"{r['seconds']} | {esc(note)} |")
    ok_events = sum(r.get("events", 0) for r in run.values())
    ok_articles = sum(r.get("articles", 0) for r in run.values())
    lines += ["", f"Итого: {ok_events} событий и {ok_articles} записей фидов; "
                  f"упало коллекторов: {sum(not r['ok'] for r in run.values())} из {len(run)}.", ""]

    lines += ["## Контрольные события", "", "| ID | Событие | Когда | Найдено | Где |", "|---|---|---|---|---|"]
    for c in json.loads(CONTROLS.read_text()):
        if c.get("source"):
            hits = [e for e in events if e["source_id"] == c["source"] and e["kind"] == "event"]
            fut = [e for e in hits if when(e) >= TODAY]
            lists = Counter(cat for e in fut for cat in e["categories"] if cat.startswith("talks.cam"))
            found = f"да — {len(fut)} будущих"
            where = "; ".join(f"{k.split(': ', 1)[1]}: {v}" for k, v in lists.most_common())
        else:
            rx = re.compile("|".join(re.escape(p) for p in c["patterns"]), re.I)
            hits = [e for e in events if rx.search(e["title"] or "") or rx.search(e.get("summary") or "")]
            if c["id"] == "C1":  # матчи: только фид домашних матчей, будущие
                fut = [e for e in hits if e["source_id"] == "S018" and when(e) >= TODAY]
                found = f"да — {len(fut)} будущих домашних" if fut else "нет"
                where = "S018: " + ", ".join(f"{when(e)} {e['title'].replace('Cambridge United FC - ', '')}" for e in sorted(fut, key=when)[:4]) + (" …" if len(fut) > 4 else "")
            else:
                near = []
                if c.get("require"):  # совпало слово, но не то событие (другой город / площадка)
                    rq = re.compile("|".join(re.escape(p) for p in c["require"]), re.I)
                    text = lambda e: " ".join(filter(None, (e["title"], e.get("summary"), e.get("venue"), e.get("address"))))  # noqa: E731
                    near = [e for e in hits if not rq.search(text(e))]
                    hits = [e for e in hits if rq.search(text(e))]
                found = f"да — {len(hits)}" if hits else "**нет**"
                fmt = lambda e: f"{e['source_id']} {e['kind']} {when(e)}: {esc(e['title'][:90])}"  # noqa: E731
                where = "<br>".join(fmt(e) for e in sorted(hits, key=when)[:6]) or "—"
                if near:
                    where += "<br>похожие, но не то: " + "; ".join(fmt(e) for e in sorted(near, key=when)[:4])
        lines.append(f"| {c['id']} | {esc(c['name'])} | {esc(c['when'])} | {found} | {where} |")

    lines += ["", "## Заполненность полей (только события)", "",
              "| ID | Событий | start | venue | postcode | url | price | status |", "|---|---|---|---|---|---|---|---|"]
    for sid in run:
        ev = [e for e in events if e["source_id"] == sid and e["kind"] == "event"]
        if ev:
            pct = lambda k: f"{round(100 * sum(1 for e in ev if e.get(k)) / len(ev))}%"  # noqa: E731
            lines.append(f"| {sid} | {len(ev)} | " + " | ".join(pct(k) for k in ("start", "venue", "postcode", "url", "price", "status")) + " |")
    if NOTES.exists():
        lines += ["", NOTES.read_text().strip()]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"Отчёт: {REPORT}")


if __name__ == "__main__":
    main()
