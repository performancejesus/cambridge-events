"""Этап 7g: редакторская разметка выпуска (этап 7f) → таблица editor_ratings.

Запуск: python scripts/load_editor_ratings.py editor_ratings_v13.json [--issue 2026-10-08 --version v13]

Таблица: issue_date, version, cand_id (id кандидата из candidates_<версия>.json: E…, A…, K:…, S:…), event_id (событие базы,
если кандидат — событие), who (кто оценил), rating, comment, rubric (рубрика кандидата или оцениваемая рубрика),
from_eid (оценка перенесена с другого события — например, с v12), kind (item — оценка пункта, rubric — оценка рубрики).
Повторная загрузка того же файла заменяет записи (ключ: выпуск, версия, кандидат, кто, вид, рубрика).

Формат файла разметки допускается гибкий: список записей или объект со списками (`ratings` / `items` / `candidates` /
`events` и `rubrics` / `rubric_ratings`). Поля записи: id | cand_id | candidate_id; who | rater | by | author;
rating | score | grade | value; comment | note | notes; rubric; from_eid | from_event_id. Неизвестные поля — в extra (JSON).
Оценки — не цель формулы важности (уточнение 11.10): они используются как контрольный набор качества.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.db import connect  # noqa: E402

SCHEMA = """CREATE TABLE IF NOT EXISTS editor_ratings (
    issue_date TEXT, version TEXT, cand_id TEXT, event_id INTEGER, who TEXT, rating TEXT, comment TEXT,
    rubric TEXT, from_eid TEXT, kind TEXT DEFAULT 'item', title TEXT, extra TEXT, loaded_at TEXT,
    UNIQUE (issue_date, version, cand_id, who, kind, rubric)
)"""
ID_KEYS = ("id", "cand_id", "candidate_id", "cid")
WHO_KEYS = ("who", "rater", "by", "author", "user")
RATING_KEYS = ("rating", "score", "grade", "value", "interest")
COMMENT_KEYS = ("comment", "note", "notes", "remark")
FROM_KEYS = ("from_eid", "from_event_id", "from_id")
KNOWN = set(ID_KEYS + WHO_KEYS + RATING_KEYS + COMMENT_KEYS + FROM_KEYS + ("rubric", "title", "kind"))


def init(con) -> None:
    con.execute(SCHEMA)


def _first(r: dict, keys) -> object:
    return next((r[k] for k in keys if k in r and r[k] not in (None, "")), None)


def event_of(cid: str | None) -> int | None:
    """E123 / A123 / T-p123 → 123 (событие базы); остальные (K:, S:, P…, V…, F…) — None."""
    m = re.match(r"^(?:E|A|T-p|C)(\d+)$", cid or "")
    return int(m.group(1)) if m else None


def records(data, default_who: str | None) -> list[dict]:
    """Все записи файла: (kind, запись). Оценки рубрик — kind=rubric."""
    out = []

    def add(items, kind, who=None):
        for r in items or []:
            if not isinstance(r, dict):
                continue
            out.append({"kind": r.get("kind") or kind, "who": _first(r, WHO_KEYS) or who or default_who, "raw": r})

    if isinstance(data, list):
        add(data, "item")
        return out
    for k in ("ratings", "items", "candidates", "events", "event_ratings"):
        if isinstance(data.get(k), list):
            add(data[k], "item")
        elif isinstance(data.get(k), dict):   # {"кто": [...]} — оценки по людям
            for who, items in data[k].items():
                add(items, "item", who)
    for k in ("rubrics", "rubric_ratings", "rubric_comments"):
        if isinstance(data.get(k), list):
            add(data[k], "rubric")
        elif isinstance(data.get(k), dict):
            for rub, v in data[k].items():   # {"рубрика": {rating, comment}} или {"рубрика": "комментарий"}
                v = v if isinstance(v, dict) else {"comment": v}
                add([v | {"rubric": rub}], "rubric")
    return out


def load(con, path: Path, issue_date: str, version: str, who: str | None = None) -> dict:
    init(con)
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        issue_date = data.get("issue_date") or issue_date
        version = data.get("version") or version
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = {"item": 0, "rubric": 0, "comments": 0, "skipped": 0}
    for rec in records(data, who):
        r, kind = rec["raw"], rec["kind"]
        cid = _first(r, ID_KEYS)
        if kind == "item" and not cid:
            n["skipped"] += 1
            continue
        rating = _first(r, RATING_KEYS)
        comment = _first(r, COMMENT_KEYS)
        extra = {k: v for k, v in r.items() if k not in KNOWN}
        con.execute("""INSERT INTO editor_ratings(issue_date, version, cand_id, event_id, who, rating, comment, rubric,
            from_eid, kind, title, extra, loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(issue_date, version, cand_id, who, kind, rubric) DO UPDATE SET rating=excluded.rating,
            comment=excluded.comment, from_eid=excluded.from_eid, title=excluded.title, extra=excluded.extra,
            loaded_at=excluded.loaded_at""",
                    # поля ключа без NULL: в SQLite NULL в UNIQUE не конфликтует — повторная загрузка дублировала бы
                    (issue_date, version, str(cid) if cid else "", event_of(str(cid)) if cid else None,
                     rec["who"] or "editor", None if rating is None else str(rating), comment, r.get("rubric") or "",
                     None if _first(r, FROM_KEYS) is None else str(_first(r, FROM_KEYS)), kind, r.get("title"),
                     json.dumps(extra, ensure_ascii=False) if extra else None, now))
        n[kind] += 1
        n["comments"] += bool(comment)
    con.commit()
    n["by_who"] = {w: c for w, c in con.execute("""SELECT who, count(*) FROM editor_ratings WHERE issue_date=? AND version=?
                                                   GROUP BY who""", (issue_date, version))}
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--issue", default="2026-10-08")
    ap.add_argument("--version", default="v13")
    ap.add_argument("--who", help="кто оценил, если в файле не указано")
    a = ap.parse_args()
    print(json.dumps(load(connect(), Path(a.path), a.issue, a.version, a.who), ensure_ascii=False, indent=1))
