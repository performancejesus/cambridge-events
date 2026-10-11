"""Этап 7g, п. 4: проверка правил на разметке v13 — по качеству, а не по оценкам вкуса.

«До» — кандидаты v13 как они были (issues/candidates_v13.json + _candidates_raw.json); «после» — те же кандидаты,
пропущенные через правила 7g (pipeline/selection.py, склейка дублей, детская рубрика). Показатели:
- доля не-событий (служебные страницы, школы, бизнес, коворкинг, приём, дейтинг) и частых регулярных;
- доля дублей (одна площадка + дата + похожее название или одна страница);
- доля неясных пунктов (расплывчатый заголовок без страницы с фактами; секции без площадки или возраста);
- взрослое в детском;
- детские и музейные пункты в «Главном» (v13 → v14).
Если загружена разметка (таблица editor_ratings, scripts/load_editor_ratings.py), то же — по комментариям редактора:
сколько пунктов, помеченных «не событие», «дубль», «непонятно что это» / «где?», «взрослое», осталось после правил.

Запуск: python scripts/quality_7f.py [--v14 issues/issue_2026-10-15_v14_final.json] → data/quality_7f.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import selection  # noqa: E402
from pipeline.normalize import norm_title, norm_venue, title_similarity  # noqa: E402

COMMENT_KINDS = {"nonevent": re.compile(r"не событие|не мероприят|реклам|служебн|парковк|бизнес|дейтинг|знакомств", re.I),
                 "dup": re.compile(r"дубл|повтор|уже было|два раза|дважды", re.I),
                 "unclear": re.compile(r"непонятно|что это|где\s*\?|неясн|без места|какое место|что именно", re.I),
                 "adult": re.compile(r"взросл|не для детей|не детск", re.I)}


def load(stem: str) -> tuple[list[dict], dict]:
    cands = json.loads((ROOT / "issues" / f"candidates_{stem}.json").read_text())["candidates"]
    raw = {c["id"]: c for c in json.loads((ROOT / "issues" / f"issue_2026-10-08_{stem}_candidates_raw.json").read_text())
           ["candidates"]}
    return cands, raw


def classify(c: dict, r: dict) -> set[str]:
    """Что в кандидате не так по правилам 7g (без учёта оценок редактора)."""
    out = set()
    title = c.get("title") or ""
    if selection.nonevent_reason(title, None, r.get("venue")):
        out.add("nonevent")
    if selection.REGULAR_RE.search(title) or re.search(r"\bparkrun\b", title, re.I) or (
            c.get("kind") == "event" and set(c.get("sources") or []) == {"S055"}):
        out.add("regular")
    if c.get("kind") == "event" and selection.vague({"title": title}) and len((r.get("summary") or "").split()) < 25:
        out.add("unclear")
    if c.get("kind") == "section":
        # строка секции: провайдер — «Провайдер — название»; площадка и возраст — из строки «дата · место · цена»
        prov, _, t = title.partition(" — ")
        why = selection.section_reason({"provider": prov, "title": t or title, "venue": r.get("venue"),
                                        "ages": c.get("when_where_price"), "category": None})
        if why and why.startswith("нужно дополнить"):
            out.add("unclear")
        if why and why.startswith("взрослое"):
            out.add("adult_in_kids")
        if why and why.startswith("продлёнка"):
            out.add("wraparound")
    if c.get("rubric") in ("С детьми",) and c.get("kind") == "event" and selection.adult(title):
        out.add("adult_in_kids")
    return out


def duplicates(cands: list[dict], raw: dict) -> set[str]:
    """Кандидаты-дубли (второй и далее в группе): одна дата и площадка + похожее название, или одна ссылка + похожее."""
    rows = []
    for c in cands:
        if c.get("kind") not in ("event", "announcement", "tickets", "venue_news", "course", "programme"):
            continue
        r = raw.get(c["id"], {})
        venue = norm_venue(r.get("venue") or "")
        t = norm_title(c.get("title") or "")
        # слова площадки в названии («… at Cambridge Central Library») не делают события похожими
        t = " ".join(w for w in t.split() if w not in set(venue.split()) | {"at", "cambridge"})
        rows.append((c["id"], t, (r.get("when") or "")[:20], venue, c.get("url"), c.get("kind")))
    dup = set()
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if b[0] in dup or not a[1] or not b[1]:
                continue
            sim = title_similarity(a[1], b[1])
            same_place = a[2] == b[2] and a[3] and a[3] == b[3]
            if a[5] == "venue_news" and b[5] == "venue_news":
                if selection.norm_place(a[1]) == selection.norm_place(b[1]):
                    dup.add(b[0])
            elif (same_place and (sim >= 0.6 or (min(len(a[1]), len(b[1])) >= 6 and (a[1] in b[1] or b[1] in a[1]))))\
                    or (a[4] and a[4] == b[4] and sim >= 0.8):
                dup.add(b[0])
    return dup


def weekend_mix(final_path: Path, cands_by_id: dict | None = None) -> dict:
    """Детские и музейные пункты в «Главном на выходные» выпуска (по тэгам кандидатов v14 или по признакам v13)."""
    from pipeline import event_types
    d = json.loads(final_path.read_text())
    out = {"items": 0, "kids": 0, "museum": 0}
    for sec in d["sections"]:
        if not sec["rubric"].startswith("weekend_"):
            continue
        for it in sec["items"]:
            out["items"] += 1
            c = (cands_by_id or {}).get(it["ids"][0]) if it.get("ids") else None
            cat = (c or {}).get("category") or event_types.category({"title": it.get("title_en") or "",
                                                                     "kind": "event"})
            if c and c.get("tags"):
                cat = event_types.category({"kind": "event"}, c["tags"])
            out["kids"] += cat == "kids"
            out["museum"] += cat == "museum"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--v14", default=str(ROOT / "issues" / "issue_2026-10-15_v14_final.json"))
    a = ap.parse_args()
    cands, raw = load("v13")
    issue_ids = {c["id"] for c in cands if c.get("in_issue") == "да"}
    flags = {c["id"]: classify(c, raw.get(c["id"], {})) for c in cands}
    dups = duplicates(cands, raw)
    for i in dups:
        flags.setdefault(i, set()).add("dup")
    n_all, n_in = len(cands), len(issue_ids)

    def share(kind: str, pool: set[str] | None = None) -> dict:
        ids = [i for i, f in flags.items() if kind in f and (pool is None or i in pool)]
        return {"n": len(ids), "examples": [next(c["title"] for c in cands if c["id"] == i)[:70] for i in ids[:6]]}

    before = {k: share(k) for k in ("nonevent", "regular", "dup", "unclear", "adult_in_kids", "wraparound")}
    before_in = {k: share(k, issue_ids) for k in before}
    # «после»: правила 7g отсекают все эти виды до отбора (кроме дублей — остаётся одна запись группы)
    res = {"candidates": n_all, "in_issue": n_in, "before_all": before, "before_in_issue": before_in,
           "after_rule": {"nonevent": 0, "regular": 0, "dup": 0, "unclear": 0, "adult_in_kids": 0, "wraparound": 0},
           "note": "после правил 7g эти кандидаты не доходят до отбора: не-события и регулярные — selection, дубли — "
                   "merge_duplicates (остаётся одна запись), неясные — vague_reason и section_reason, взрослое — "
                   "section_reason / fits(kids)"}
    v13_final = ROOT / "issues" / "issue_2026-10-08_v13_final.json"
    res["weekend_v13"] = weekend_mix(v13_final)
    p14 = Path(a.v14)
    if p14.exists():
        c14 = {c["id"]: c for c in json.loads((ROOT / "issues" / "candidates_v14.json").read_text())["candidates"]} \
            if (ROOT / "issues" / "candidates_v14.json").exists() else None
        res["weekend_v14"] = weekend_mix(p14, c14)
    # разметка редактора (если загружена)
    con = sqlite3.connect(ROOT / "data" / "events.db")
    con.row_factory = sqlite3.Row
    have = con.execute("SELECT name FROM sqlite_master WHERE name='editor_ratings'").fetchone()
    rows = con.execute("SELECT * FROM editor_ratings WHERE version='v13' AND kind='item' AND comment IS NOT NULL").fetchall() \
        if have else []
    if rows:
        by = {}
        for r in rows:
            for k, rx in COMMENT_KINDS.items():
                if rx.search(r["comment"] or ""):
                    by.setdefault(k, []).append(r["cand_id"])
        res["editor_comments"] = {}
        for k, ids in by.items():
            caught = [i for i in ids if flags.get(i, set()) & ({"nonevent", "regular"} if k == "nonevent" else
                                                               {"unclear"} if k == "unclear" else
                                                               {"adult_in_kids", "wraparound"} if k == "adult" else {k})]
            res["editor_comments"][k] = {"marked": len(ids), "caught_by_rules": len(caught),
                                         "left": [i for i in ids if i not in caught][:20]}
    else:
        res["editor_comments"] = None
    (ROOT / "data" / "quality_7f.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k not in ("before_all", "before_in_issue")}, ensure_ascii=False, indent=1))
    print({k: v["n"] for k, v in before.items()}, {k: v["n"] for k, v in before_in.items()})


if __name__ == "__main__":
    main()
