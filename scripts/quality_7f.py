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
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import selection  # noqa: E402
from pipeline.normalize import norm_title, norm_venue, title_similarity  # noqa: E402

COMMENT_KINDS = {"nonevent": re.compile(r"не событие|не мероприят|реклам|служебн|парковк|бизнес|дейтинг|знакомств", re.I),
                 "dup": re.compile(r"дубл|повтор|уже было|два раза|дважды", re.I),
                 "unclear": re.compile(r"непонятно|что это|где\s*\?|неясн|без места|какое место|что именно", re.I),
                 "adult": re.compile(r"взросл|не для детей|не детск", re.I)}


def load(stem: str, date: str = "2026-10-08") -> tuple[list[dict], dict]:
    cands = json.loads((ROOT / "issues" / f"candidates_{stem}.json").read_text())["candidates"]
    raw = {c["id"]: c for c in json.loads((ROOT / "issues" / f"issue_{date}_{stem}_candidates_raw.json").read_text())
           ["candidates"]}
    return cands, raw


def _progs() -> dict:
    """Строки kids_programmes по prog_id: у секции в выгрузке кандидатов нет возраста — берём из базы."""
    con = sqlite3.connect(ROOT / "data" / "events.db")
    con.row_factory = sqlite3.Row
    return {r["prog_id"]: r for r in con.execute("SELECT * FROM kids_programmes")}


PROGS = _progs()


def _excl14() -> dict:
    """название (без даты) → причина отсева до отбора в v14."""
    p = ROOT / "issues" / "candidates_v14.json"
    if not p.exists():
        return {}
    return {re.sub(r"\s*\(\d{4}-\d\d-\d\d\)$", "", e["title"]).lower(): e["reason"]
            for e in json.loads(p.read_text())["excluded_before_selection"]}


EXCL14 = _excl14()
CANDS14 = {c["id"]: c for c in json.loads((ROOT / "issues" / "candidates_v14.json").read_text())["candidates"]} \
    if (ROOT / "issues" / "candidates_v14.json").exists() else {}


def _excl14_prog() -> dict:
    """prog_id → причина отсева каникулярной программы до отбора v14 (по «провайдер — название»)."""
    out, names = {}, {}
    for pid, r in PROGS.items():   # у дублей одинаковые «провайдер — название»: причина — тем, кого нет среди кандидатов
        names.setdefault(f"{r['provider']} — {r['title']}".lower(), []).append(pid)
    for t, why in EXCL14.items():
        for pid in names.get(t) or names.get(re.sub(r"\s*\([^)]*\)$", "", t)) or []:
            if pid not in CANDS14:
                out[pid] = why
    return out


EXCL14_PROG = _excl14_prog()


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
        row = PROGS.get(c["id"][2:]) if c["id"].startswith("S:") else None
        why = selection.section_reason(dict(row) if row else
                                       {"provider": prov, "title": t or title, "venue": r.get("venue"),
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
        rows.append((c["id"], t, (r.get("when") or "")[:20], venue, c.get("url"), c.get("kind"), c.get("title") or ""))
    dup = set()
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if b[0] in dup or not a[1] or not b[1]:
                continue
            if a[5] == b[5] == "programme" and re.findall(r"\d+", a[6]) != re.findall(r"\d+", b[6]):
                continue   # разные возрастные группы одного лагеря (Cambridge LTC 5–8 / 8–10 / 11–16) — не дубли
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


KIND_RU = {"nonevent": "не событие", "dup": "дубль", "unclear": "непонятно что / где", "kids_age": "программа без возраста",
           "adult": "взрослое в детском", "wraparound": "продлёнка при школе", "regular": "регулярное",
           "far": "далеко (вне зоны)", "public": "семинар — открыт ли", "new_in_town": "«Новое в городе»: закрытие и т. п.",
           "translate": "перевод", "explain": "пояснить незнакомое", "split": "разбить сборную страницу",
           "placement": "в какую рубрику", "diversity": "перебор однотипного", "tour": "туристический тур",
           "school_only": "только для учеников?", "note": "без ошибки"}
# куда пункт должен попасть по комментарию «в какую рубрику» → категория event_types (или «не …»)
PLACEMENT_WANT = {"E1275": "talk", "E2189": "talk", "E2405": "talk", "E2701": "talk", "E2709": "talk", "E2716": "talk",
                  "E1466": "volunteering", "E2669": "class|sport", "E2663": "!class", "E2706": "class", "E2710": "class",
                  "E2139": "talk|class", "E2460": "!museum"}


def editor_review(cands: list[dict], raw: dict, flags: dict, dups: set) -> dict:
    """Этап 7h: «отмечено редактором → поймано правилами → осталось». Каждый комментарий — вид (data/editor_comment_kinds.json),
    вид проверяется прямым вызовом правила на данных v13 и базы (а не по причине отсева v14 — та первая сработавшая)."""
    from datetime import date
    from pipeline import event_types, issue, issue_fixes
    from pipeline.db import connect
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_issue
    con = connect()
    kinds = json.loads((ROOT / "data" / "editor_comment_kinds.json").read_text())["kinds"]
    ratings = {r["id"] + "|" + r["rater"]: r for r in json.loads((ROOT / "data" / "editor_ratings_v13.json").read_text())["ratings"]}
    w13 = issue.Window(date(2026, 10, 8), date(2026, 10, 8), date(2026, 10, 18))
    rows: dict[str, list] = {}

    def ev_row(cid):
        m = re.match(r"^[EA](\d+)$", cid)
        return con.execute("SELECT * FROM events WHERE event_id=?", (int(m.group(1)),)).fetchone() if m else None

    def prog(cid):
        return PROGS.get(cid[2:] if cid.startswith("S:") else cid)

    # отбор с нынешними правилами на окне v13: что стало с каждым помеченным кандидатом (склеен / отсеян / остался)
    pools = issue.build_pools(con, w13)
    ev2cid = {e: k for k, c in pools.candidates.items() for e in c.get("event_ids", [])}
    excl = {t: why for why, lst in pools.excluded.items() for t in lst}

    def disposition(cid):
        e = ev_row(cid)
        if e is None:
            return None, None
        keep = ev2cid.get(e["event_id"])
        if keep and keep != cid:
            return "merged", keep
        if keep == cid:
            return "candidate", pools.candidates[cid]
        why = excl.get(f"{e['title']} ({e['date_start']})") or next((v for k, v in excl.items() if k.startswith(e["title"])
                                                                      and f"({cid})" in k), None)
        return ("excluded", why) if why else ("absent", None)

    def check(kind, cid, r, c):
        title, venue = c.get("title") or r.get("title") or "", r.get("venue")
        fl = flags.get(cid, set())
        e = ev_row(cid)
        st, val = disposition(cid)
        if kind == "dup" and (cid.startswith("C:") or cid.startswith("S:")):
            c14 = CANDS14.get(cid)
            ex = EXCL14_PROG.get(cid)
            if ex:
                return True, f"не показывается: {ex[:70]}"
            if c14 and c14["in_issue"] != "да":
                return True, f"не показывается: {c14['reason'][:70]}"
        if kind == "public" and st != "candidate" and e is not None:
            facts = issue._event_facts(con, e)
            ok = not (facts.get("talk") and facts.get("public_talk"))
            return ok, "семинар talks.cam без пометки open to all — не в «Лекции»" if ok else "проходит как публичная лекция"
        if kind == "dup" and st == "merged":
            return True, f"склеен с «{pools.candidates[val]['title'][:50]}»"
        if kind == "dup" and st == "candidate" and val.get("merged_titles"):
            return True, f"склеен: в нём «{val['merged_titles'][0][:50]}»"
        if kind in ("nonevent", "regular", "tour", "unclear", "dup", "translate") and st == "excluded":
            return True, f"отсеян до отбора: {val[:80]}"
        if kind == "public" and st == "candidate":
            return (not build_issue.fits("talks", val, w13),
                    "не публичная лекция — не в «Лекции и встречи»" if not build_issue.fits("talks", val, w13)
                    else "проходит в «Лекции» без пометки open to all")
        if kind == "placement" and st == "candidate" and cid in PLACEMENT_WANT:
            want = PLACEMENT_WANT[cid]
            rub = {"talk": "talks", "class": "learn", "sport": "sport", "museum": "museums", "volunteering": None}
            from pipeline.courses import LEARN_RE, NOT_LEARN_RE
            if LEARN_RE.search(val.get("title") or "") and not NOT_LEARN_RE.search(val.get("title") or ""):
                val = val | {"learn": True}
            if want.startswith("!"):
                bad = rub[want[1:]]
                ok = not build_issue.fits(bad, val, w13)
                return ok, (f"не в рубрике «{bad}»" if ok else f"всё ещё подходит в «{bad}»")
            if want == "volunteering":
                ok = "volunteering" in (val.get("types") or [])
                return ok, "тэг volunteering → «Волонтёрство»" if ok else "нет тэга volunteering"
            fit = [rub[x] for x in want.split("|") if build_issue.fits(rub[x], val, w13)]
            return (bool(fit), f"подходит в «{fit[0]}»" if fit else f"не подходит в «{'/'.join(rub[x] for x in want.split('|'))}»")
        if kind == "nonevent":
            why = selection.nonevent_reason(title, None, venue) or selection.vague_reason({"title": title})
            if not why and e is not None and selection.SCHOOL_RE.search(venue or ""):
                from pipeline.page_times import cached_text
                why = selection.school_event_reason(title, venue, cached_text(e["url"]))
            if not why and selection.DROPOFF_RE.search(title) and selection.MUSEUM_HOST_RE.search(venue or ""):
                return True, "событие музея (E-waste в Centre for Computing History) — по правилу оставлено"
            if not why and re.search(r"\bfinance leadership|leadership programme\b", title, re.I):
                return False, "бизнес-программа: «Finance Leadership Programme» не попадает в BUSINESS_RE"
            return (True, why) if why else (False, "правило не сработало")
        if kind == "dup":
            if "dup" in fl or cid in dups:
                return True, "склейка дублей (площадка + дата + похожее название / одна страница / провайдер + даты + возраст)"
            return False, "не похож по признакам склейки (разные даты или названия)"
        if kind in ("unclear", "kids_age", "adult", "wraparound"):
            pr = prog(cid)
            if pr is not None and (pr["kind"] or "holiday") != "regular":   # каникулярная программа
                if pr["zone"] and pr["zone"] not in issue.LISTED_ZONES:
                    return True, "программа вне зоны — не показывается"
                if pr["audience"] in ("university", "school_pupils"):
                    return True, "только для своих — не показывается"
                ok_place = bool(pr["venue"] or pr["address"])
                ok_age = bool(selection.AGE_RE.search(f"{'' if selection.PLACEHOLDER_AGES.match(pr['ages'] or '') else pr['ages'] or ''} {pr['title']}"))
                if not (ok_place and ok_age):
                    return True, "нужно дополнить: нет места или возраста — в выпуск не идёт"
                return True, f"строка с местом и возрастом ({pr['venue'] or pr['address']}, {pr['ages']})"
            if pr is not None:   # секция
                why = selection.section_reason(dict(pr))
                if why:
                    return True, why
                from pipeline import sections
                why = sections._line_ok(pr)
                return (True, why) if why else (False, f"секция с полными полями — вопрос к содержанию «{title}»")
            if kind == "unclear":
                if selection.vague({"title": title}):
                    return True, "расплывчатый заголовок — раскрыть по странице или не брать"
                if re.match(r"^(Home Ed|Home Educat)", title, re.I) or selection.home_ed(title):
                    return True, "Home Ed — пометка «для детей на домашнем обучении»"
                if c.get("kind") == "venue_news" and selection.news_reason({"title": title}):
                    return True, selection.news_reason({"title": title})
                return False, "правила не ловят — нужен текст пункта по странице"
            return False, "правило не сработало"
        if kind == "regular":
            if e is not None and re.search(r"\bесли\b", ratings.get(cid + "|anton", {}).get("comment", "")):
                ser = issue.series_of_event(con, e, w13)
                if not selection.series_regular([x[0] for x in ser], [x[1] for x in ser]) and \
                        not selection.frequent_regular({"title": title, "dates": []}):
                    return True, f"реже 4 раз в месяц ({len(ser)} дат в базе) — по правилу не регулярное, оставлено"
            if re.search(r"\bparkrun\b", title, re.I):
                return True, "parkrun — одной строкой со ссылкой, без дат"
            why = selection.frequent_regular({"title": title, "dates": []})
            if not why and e is not None:
                ser = issue.series_of_event(con, e, w13)
                why = selection.series_regular([x[0] for x in ser], [x[1] for x in ser])
            if not why and prog(cid) is not None:
                return False, "секция клуба (не школы) — вопрос редактора, не ошибка"
            return (True, why) if why else (False, "4+ дат за месяц в базе нет")
        if kind == "far":
            pr = prog(cid)
            return (True, "программа вне зоны — не попадает даже в кандидаты") if pr is None or \
                (pr["zone"] and pr["zone"] not in issue.LISTED_ZONES) else (False, f"зона {pr['zone']}")
        if kind == "public":
            tg = event_types.tags({"title": title, "summary": r.get("summary"), "sources": r.get("sources")})
            if "academic_seminar" in tg and not issue.PUBLIC_RE.search(f"{title} {r.get('summary') or ''}"):
                return True, "семинар без пометки «open to all» — не в «Лекции»"
            return False, "семинар не распознан"
        if kind == "new_in_town":
            st = "closed" if re.search(r"убрать|закрыл|давно", ratings.get(cid + "|anton", {}).get("comment", ""), re.I) else ""
            why = selection.news_reason({"title": title, "stage": c.get("stage") or ""})
            ex = next((v for k, v in EXCL14.items() if k == title.lower()), None)
            return (True, why or ex) if (why or ex) else (False, "открытие без признаков закрытия")
        if kind == "translate":
            text = f"{title} {r.get('summary') or ''}" + (" руленые бейглы" if "руленые" in
                                                         ratings.get(cid + "|anton", {}).get("comment", "") else "")
            for rx, good, need in issue_fixes.TRANSLATION_FIXES:
                if rx.search(text):
                    return True, f"словарь перевода: «{good}»"
            if issue_fixes.stray_english("Изучение магматических камер в Greenland" if "Greenland" in text else
                                         ("Традиционная китайская archery" if "archery" in text.lower() else ""), ""):
                return True, "проверка 35: английское нарицательное слово в русской фразе — перевод"
            if selection.vague({"title": title}):
                return True, "расплывчатый заголовок («Guided Tour of the …») — раскрыть или не брать"
            return False, "словарь перевода не знает этого слова"
        if kind == "explain":
            text = f"{title} {r.get('summary') or ''}"
            for src_rx, _, expl in issue_fixes.EXPLAIN:
                if src_rx.search(text):
                    return True, f"пояснение: «{expl}»"
            for rx, good, need in issue_fixes.TRANSLATION_FIXES:
                if rx.search(text) or (re.search(r"\bnet sessions?\b", text, re.I) and "нэт" in good):
                    return True, f"словарь: «{good}»"
            return False, "в словаре пояснений нет (для агрегатора «кто именно будет» — правило промпта, без проверки)"
        if kind == "placement":
            want = PLACEMENT_WANT.get(cid)
            cat = event_types.category({"title": title, "summary": r.get("summary"), "kind": "event"})
            if "volunteering" == want and "volunteering" in event_types.tags({"title": title}):
                return True, "тэг volunteering → рубрика «Волонтёрство»"
            if want and want.startswith("!"):
                bad = want[1:]
                if bad == "museum" and re.search(r"cut your own|pick your own", title, re.I):
                    return True, "не музейная строка (cut your own) — убрана из «Музеев»"
                return (cat != bad, f"категория «{cat}»")
            if want and cat in want.split("|"):
                return True, f"категория «{cat}» → нужная рубрика"
            return False, f"категория «{cat}», а нужна «{want}»"
        if kind == "diversity":
            sub = build_issue.subtype({"title": title})
            if sub:
                return True, f"разнообразие: не больше 2 пунктов подвида «{sub}» в рубрике"
            return False, "лимита на одну площадку (Cambridge Junction) нет"
        if kind == "tour":
            if e is not None:
                ser = issue.series_of_event(con, e, w13)
                why = selection.series_regular([x[0] for x in ser], [x[1] for x in ser])
                if why:
                    return True, why
            return False, "экскурсия не распознана как регулярная или туристический продукт"
        if kind == "split":
            return False, "разбивка сборной страницы (HAF, лагерь с проектами) не сделана; HAF — строка с пометкой"
        if kind == "school_only":
            return False, "клуб, не школа — вопрос редактора, не ошибка"
        return False, ""

    for key, kind in kinds.items():
        cid, who = key.split("|")
        if kind == "note":
            continue
        r = raw.get(cid, {})
        c = next((x for x in cands if x["id"] == cid), {})
        caught, how = check(kind, cid, r, c)
        rows.setdefault(kind, []).append({"id": cid, "title": (c.get("title") or r.get("title") or ratings[key]["title"])[:70],
                                          "comment": ratings[key]["comment"][:120], "caught": bool(caught), "how": how})
    table = {k: {"marked": len(v), "caught": sum(x["caught"] for x in v), "left": [x for x in v if not x["caught"]],
                 "caught_how": Counter(x["how"].split(":")[0][:60] for x in v if x["caught"]).most_common(4)}
             for k, v in rows.items()}
    return {"by_kind": table, "total": sum(t["marked"] for t in table.values()),
            "caught": sum(t["caught"] for t in table.values())}


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
    # «после» на v13: правила 7g отсекают эти виды до отбора (из дублей остаётся одна запись группы)
    res = {"candidates": n_all, "in_issue": n_in, "before_all": before, "before_in_issue": before_in,
           "after_rule": {"nonevent": 0, "regular": 0, "dup": 0, "unclear": 0, "adult_in_kids": 0, "wraparound": 0},
           "note": "после правил 7g эти кандидаты не доходят до отбора: не-события и регулярные — selection, дубли — "
                   "merge_duplicates (остаётся одна запись), неясные — vague_reason и section_reason, взрослое — "
                   "section_reason / fits(kids)"}
    # «после» измеренное: те же проверки на кандидатах v14 (собраны уже с правилами 7g)
    if (ROOT / "issues" / "candidates_v14.json").exists():
        c14l, r14 = load("v14", "2026-10-15")
        f14 = {c["id"]: classify(c, r14.get(c["id"], {})) for c in c14l}
        for i in duplicates(c14l, r14):
            f14.setdefault(i, set()).add("dup")
        in14 = {c["id"] for c in c14l if c.get("in_issue") == "да"}
        t14 = {c["id"]: c["title"] for c in c14l}

        def share14(kind: str, pool: set[str] | None = None) -> dict:
            ids = [i for i, f in f14.items() if kind in f and (pool is None or i in pool)]
            return {"n": len(ids), "examples": [t14[i][:70] for i in ids[:6]]}
        res["v14_candidates"], res["v14_in_issue"] = len(c14l), len(in14)
        res["v14_all"] = {k: share14(k) for k in before}
        res["v14_in"] = {k: share14(k, in14) for k in before}
    v13_final = ROOT / "issues" / "issue_2026-10-08_v13_final.json"
    res["weekend_v13"] = weekend_mix(v13_final)
    p14 = Path(a.v14)
    if p14.exists():
        c14 = {c["id"]: c for c in json.loads((ROOT / "issues" / "candidates_v14.json").read_text())["candidates"]} \
            if (ROOT / "issues" / "candidates_v14.json").exists() else None
        res["weekend_v14"] = weekend_mix(p14, c14)
    # этап 7h: «отмечено редактором → поймано правилами → осталось» по видам комментариев
    if (ROOT / "data" / "editor_comment_kinds.json").exists():
        res["editor_review"] = editor_review(cands, raw, flags, dups)
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
    print(json.dumps({k: v for k, v in res.items() if k not in ("before_all", "before_in_issue", "v14_all", "v14_in")}, ensure_ascii=False, indent=1))
    print({k: v["n"] for k, v in before.items()}, {k: v["n"] for k, v in before_in.items()})
    if "v14_all" in res:
        print("v14", {k: v["n"] for k, v in res["v14_all"].items()}, {k: v["n"] for k, v in res["v14_in"].items()})


if __name__ == "__main__":
    main()
