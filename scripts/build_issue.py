"""Этап 4: черновик выпуска — issue_<дата>_en.md и issue_<дата>_ru.md в issues/.

Кандидаты берутся из events.db (pipeline/issue.py), отбор и тексты — Claude (Sonnet), промпт prompts/issue.md,
схема ответа prompts/issue.schema.json. Ключ — EVENTS_ANTHROPIC_KEY.

  python scripts/build_issue.py --issue 2026-10-01 --start 2026-09-28 --end 2026-10-11 --weekend 2026-10-03
  python scripts/build_issue.py ... --dry-run     # только пулы кандидатов и оценка объёма, без API
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import issue  # noqa: E402
from pipeline.db import connect  # noqa: E402

MODEL = "claude-sonnet-5"
PRICE_IN, PRICE_OUT = 2.00 / 1e6, 10.00 / 1e6   # $ за токен, Sonnet 5
PROMPT = (ROOT / "prompts" / "issue.md").read_text()
SCHEMA = json.loads((ROOT / "prompts" / "issue.schema.json").read_text())
PREFIX_RUBRICS = {"E": {"weekend", "free", "kids", "sport", "out_of_town", "county"},
                  "A": {"new_announcements", "tickets"}, "T": {"tickets"}, "C": {"cancelled"}, "V": {"new_in_town"}}


def call_model(client, payload: dict) -> tuple[dict, int, int]:
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}, "effort": "high"},
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={msg.stop_reason}")
    body = next(b.text for b in msg.content if b.type == "text")
    return json.loads(body), msg.usage.input_tokens, msg.usage.output_tokens


def fits(rubric: str, c: dict, w: issue.Window) -> bool:
    """Выходные — событие идёт в субботу или воскресенье; «за городом» и «по графству» — по зоне."""
    if rubric == "weekend":
        return any(issue.d(s) <= w.weekend[1] and issue.d(e) >= w.weekend[0] for s, e, _ in c["dates"])
    if rubric == "out_of_town":
        return c.get("zone") in issue.OUT_OF_TOWN
    if rubric == "county":
        return c.get("zone") == "Кембриджшир, дальше часа"
    return True


NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _nums(text: str) -> set[float]:
    text = re.sub(r"(\d),(\d{2})\b", r"\1.\2", text or "")   # «£38,50» в русском тексте
    return {round(float(x), 2) for x in NUM_RE.findall(text.replace(",", ""))}


def check_price(it: dict, c: dict) -> tuple[str, str] | None:
    """Цифры цены в тексте модели должны быть в данных (price_text, price_from, summary); иначе — цена из базы."""
    known = _nums(c.get("price_text")) | _nums(c.get("summary")) | _nums(c.get("note"))
    if c.get("price_from") is not None:
        known.add(round(float(c["price_from"]), 2))
    known |= {round(x) for x in known}
    wrong = {x for x in _nums(it["price_en"]) | _nums(it["price_ru"]) if x not in known}
    if not wrong or c["kind"] == "venue_news":
        return None
    en, ru = issue.price_from_data(c)
    it["price_en"], it["price_ru"] = en, ru
    return (f"“{it['title_en']}”: price in the model text did not match the data ({sorted(wrong)}) — replaced with “{en}”",
            f"«{it['title_ru']}»: цена в тексте модели не совпала с данными ({sorted(wrong)}) — заменена на «{ru}»")


HOMOGLYPHS = str.maketrans("aeopcxyAEOPCXHBKMT", "аеорсхуАЕОРСХНВКМТ")
MIXED_RE = re.compile(r"\b(?=\w*[а-яё])(?=\w*[a-z])\w+\b", re.I)
LATIN_RE = re.compile(r"\b[a-z]{4,}\b")


def check_russian(result: dict, pools: issue.Pools) -> list[tuple[str, str]]:
    """Русский текст: латинские буквы-двойники внутри русских слов («Ирландa») — исправить; латинские слова
    в нижнем регистре, которых нет в данных кандидатов («afishas»), — показать редактору."""
    notes = []
    known = " ".join(json.dumps(c, ensure_ascii=False) for c in pools.candidates.values()).lower()
    fields = [(result, "intro_ru")] + [(it, f) for sec in result["sections"] for it in sec["items"]
                                       for f in ("title_ru", "where_ru", "price_ru", "blurb_ru")]
    for obj, f in fields:
        for word in MIXED_RE.findall(obj[f]):
            fixed = word.translate(HOMOGLYPHS)
            if re.fullmatch(r"[а-яё]+", fixed, re.I):
                obj[f] = obj[f].replace(word, fixed)
                notes.append((f"Russian text: Latin letters inside the word «{fixed}» — fixed",
                              f"русский текст: латинские буквы в слове «{fixed}» — исправлено"))
        for word in LATIN_RE.findall(obj[f]):
            if word not in known:
                notes.append((f"Russian text: the Latin word «{word}» is not in the source data — check the wording",
                              f"русский текст: латинское слово «{word}» не из данных — проверить формулировку"))
    return notes


def validate(result: dict, pools: issue.Pools, w: issue.Window) -> list[tuple[str, str]]:
    """Убирает неизвестные и повторные id, пункты не в своей рубрике; возвращает замечания (en, ru)."""
    notes, used, used_events = [], set(), set()
    for sec in result["sections"]:
        kept = []
        for it in sec["items"]:
            ids = [i for i in it["ids"] if i in pools.candidates]
            bad = [i for i in it["ids"] if i not in pools.candidates]
            if bad:
                notes.append((f"unknown candidate ids {bad} in the model output — removed",
                              f"модель сослалась на несуществующие id {bad} — убраны"))
            # первым — кандидат, чей тип подходит рубрике (при объединении дублей модель может поставить другой)
            ids.sort(key=lambda i: sec["rubric"] not in PREFIX_RUBRICS.get(i[0], set()))
            prefix = ids[0][0] if ids else ""
            events = {e for i in ids for e in pools.candidates[i]["event_ids"]}
            if not ids or any(i in used for i in ids) or events & used_events:
                notes.append((f"“{it['title_en']}”: empty or repeated item — removed",
                              f"«{it['title_ru']}»: пустой или повторный пункт — убран"))
                continue
            if sec["rubric"] not in PREFIX_RUBRICS.get(prefix, set()) or not fits(sec["rubric"], pools.candidates[ids[0]], w):
                notes.append((f"“{it['title_en']}” ({ids[0]}) does not fit rubric {sec['rubric']} — removed",
                              f"«{it['title_ru']}» ({ids[0]}) не подходит для рубрики {sec['rubric']} — убран"))
                continue
            fixed = check_price(it, pools.candidates[ids[0]])
            if fixed:
                notes.append(fixed)
            used.update(ids)
            used_events.update(events)
            kept.append(it | {"ids": ids})
        sec["items"] = kept
    return notes


def editor_block(result: dict, pools: issue.Pools, w: issue.Window, fix_notes: list[tuple[str, str]],
                 review: list[tuple[str, str]], usage: dict) -> dict:
    """Служебный блок: заметки модели + то, что видно из базы (дубли, непроверенные статусы, что не попало)."""
    chosen = {i: sec["rubric"] for sec in result["sections"] for it in sec["items"] for i in it["ids"]}
    merged = {tuple(it["ids"]) for sec in result["sections"] for it in sec["items"] if len(it["ids"]) > 1}
    counts = Counter({sec["rubric"]: len(sec["items"]) for sec in result["sections"]})
    total = sum(counts.values())

    dups_en, dups_ru = [], []
    for a, b, titles in pools.duplicates:
        was = any(a in m and b in m for m in merged)
        dups_en.append(f"{titles} ({a}, {b}) — " + ("merged into one item" if was else "not merged, check"))
        dups_ru.append(f"{titles} ({a}, {b}) — " + ("объединены в один пункт" if was else "не объединены, проверить"))

    unv_en, unv_ru = [], []
    for cid, rub in chosen.items():
        c = pools.candidates[cid]
        t = c["title"]
        if c.get("status") == "scheduled (no ticket data)":
            unv_en.append(f"{t} ({cid}): no ticket-sale data from ADC / Cambridge United — status to be checked at stage 5")
            unv_ru.append(f"{t} ({cid}): нет данных о продаже (ADC / Cambridge United) — статус уточнится на этапе 5")
        if c.get("address_unknown"):
            unv_en.append(f"{t} ({cid}): only the city is known, zone «центр» assumed (address_unknown)")
            unv_ru.append(f"{t} ({cid}): известен только город, зона «центр» условно (address_unknown)")
        if c.get("source_type") == "article" and c["kind"] != "venue_news" and len(c.get("sources", [])) == 1:
            unv_en.append(f"{t} ({cid}): found only in a news article, not in a listings source")
            unv_ru.append(f"{t} ({cid}): есть только в статье, в афишах не найдено")
        if c["kind"] == "venue_news" and c.get("date_basis") == "publication_date":
            unv_en.append(f"{t} ({cid}): opening date = article date (the article gives no exact date)")
            unv_ru.append(f"{t} ({cid}): дата открытия = дата статьи (точной даты в статье нет)")
        if c["kind"] == "venue_news" and not c.get("date"):
            unv_en.append(f"{t} ({cid}): opening date unknown (article published {c.get('published') or '?'})")
            unv_ru.append(f"{t} ({cid}): дата открытия неизвестна (статья от {c.get('published') or '?'})")
    if pools.unverified_news:
        unv_en.append(f"Cambridge BID: {pools.unverified_news} headline(s) matched the opening/closing keywords without LLM — not used, need a manual check")
        unv_ru.append(f"Cambridge BID: заголовков по ключевым словам без LLM — {pools.unverified_news}; в выпуск не взяты, нужна ручная проверка")

    out_en, out_ru = [], []
    reasons_en = {"лекции talks.cam с «Title to be confirmed»": "talks.cam lectures with “Title to be confirmed”",
                  "нет площадки или адреса": "no venue or address", "зона не определена (нет postcode)":
                  "zone unknown (no postcode)", "вне зоны": "out of zone"}
    for why, titles in pools.excluded.items():
        ex = "; ".join(titles[:4]) + (" …" if len(titles) > 4 else "")
        out_en.append(f"{reasons_en.get(why, why)}: {len(titles)} ({ex})")
        out_ru.append(f"{why}: {len(titles)} ({ex})")
    if pools.sold_out:
        out_en.append(f"sold out: {len(pools.sold_out)} ({'; '.join(pools.sold_out)})")
        out_ru.append(f"билеты распроданы: {len(pools.sold_out)} ({'; '.join(pools.sold_out)})")
    left = [c for cid, c in pools.candidates.items() if cid not in chosen]
    by_kind = Counter(c["kind"] for c in left)
    kinds_ru = {"event": "событий в окне", "announcement": "анонсов", "tickets": "стартов продаж",
                "cancellation": "отмен", "venue_news": "записей «новое в городе»"}
    out_en.append("candidates not chosen by the model: " + ", ".join(f"{k} — {v}" for k, v in by_kind.items()))
    out_ru.append("кандидатов не выбрано моделью: " + ", ".join(f"{kinds_ru[k]} — {v}" for k, v in by_kind.items()))
    out_en.append("no general “weekdays” rubric in the brief: weekday concerts and shows at the Corn Exchange and "
                  "elsewhere get in only via the rubrics above")
    out_ru.append("в брифе нет общей рубрики «на неделе»: концерты и спектакли в будни попадают только через рубрики выше")

    cnt_en, cnt_ru = [], []
    for rub in issue.RUBRICS:
        n = counts.get(rub, 0)
        flag = "" if 3 <= n <= 6 else (" ⚠️ below 3" if n < 3 else " ⚠️ above 6")
        flag_ru = "" if 3 <= n <= 6 else (" ⚠️ меньше 3" if n < 3 else " ⚠️ больше 6")
        cnt_en.append(f"{issue.RUBRIC_TITLES['en'][rub].split(':')[0]}: {n}{flag}")
        cnt_ru.append(f"{issue.RUBRIC_TITLES['ru'][rub].split(':')[0]}: {n}{flag_ru}")
    cnt_en.append(f"total: {total} (target 25–40)")
    cnt_ru.append(f"всего: {total} (цель 25–40)")

    cost = (f"{MODEL}: {usage['input_tokens']} input + {usage['output_tokens']} output tokens = "
            f"${usage['cost_usd']:.4f}")
    fixes_en = [f"output check: {en}" for en, _ in fix_notes]
    fixes_ru = [f"проверка ответа: {ru}" for _, ru in fix_notes]
    fixes_en += [f"review: {en}" for en, _ in review]
    fixes_ru += [f"ревью: {ru}" for _, ru in review]
    return {
        "en": [("Doubtful items and model notes", result["editor_notes_en"] + fixes_en),
               ("Possible duplicates the pipeline did not merge", dups_en),
               ("Unverified status", unv_en),
               ("What didn't make it and why", out_en),
               ("Items per rubric", cnt_en),
               ("Claude API cost of this draft", [cost])],
        "ru": [("Сомнительные пункты и заметки модели", result["editor_notes_ru"] + fixes_ru),
               ("Возможные дубли, которые не склеились", dups_ru),
               ("Непроверенный статус", unv_ru),
               ("Что не попало и почему", out_ru),
               ("Пунктов по рубрикам", cnt_ru),
               ("Расход Claude API на черновик", [cost])],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--weekend", required=True, help="суббота выходных «главного на выходные»")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-json", help="не вызывать API, взять сохранённый ответ модели")
    args = ap.parse_args()
    sat = date.fromisoformat(args.weekend)
    w = issue.Window(date.fromisoformat(args.issue), date.fromisoformat(args.start), date.fromisoformat(args.end),
                     (sat, sat + timedelta(days=1)))
    con = connect()
    pools = issue.build_pools(con, w)
    payload = {"issue_date": args.issue, "period": [args.start, args.end],
               "weekend": [w.weekend[0].isoformat(), w.weekend[1].isoformat()],
               "candidates": issue.model_view(pools)}
    out_dir = ROOT / "issues"
    out_dir.mkdir(exist_ok=True)
    kinds = Counter(c["kind"] for c in pools.candidates.values())
    print(json.dumps({"candidates": kinds, "excluded": {k: len(v) for k, v in pools.excluded.items()},
                      "duplicates": len(pools.duplicates), "payload_chars": len(json.dumps(payload, ensure_ascii=False))},
                     ensure_ascii=False), file=sys.stderr)
    if args.dry_run:
        return
    raw_path = out_dir / f"issue_{args.issue}_model.json"
    if args.from_json:
        saved = json.loads(Path(args.from_json).read_text())
        result, usage = saved["result"], saved["usage"]
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
        result, tin, tout = call_model(client, payload)
        cost = tin * PRICE_IN + tout * PRICE_OUT
        usage = {"input_tokens": tin, "output_tokens": tout, "cost_usd": cost}
        con.execute("""INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd)
            VALUES (?,?,?,?,?,?,?)""", (datetime.now(timezone.utc).isoformat(timespec="seconds"), f"issue {args.issue}",
                                        MODEL, None, tin, tout, cost))
        con.commit()
        raw_path.write_text(json.dumps({"result": result, "usage": usage}, ensure_ascii=False, indent=1))
    fix_notes = validate(result, pools, w) + check_russian(result, pools)
    # ручные правки и заметки ревью, записанные в сохранённый ответ модели (issues/issue_<дата>_model.json)
    review = [tuple(x) for x in result.get("manual_fixes", []) + result.get("review_notes", [])]
    editor = editor_block(result, pools, w, fix_notes, review, usage)
    for lang in ("en", "ru"):
        path = out_dir / f"issue_{args.issue}_{lang}.md"
        path.write_text(issue.render(result, pools, w, lang, editor))
        print(path.relative_to(ROOT))
    counts = {sec["rubric"]: len(sec["items"]) for sec in result["sections"]}
    print(json.dumps({"items": counts, "total": sum(counts.values()), "cost_usd": round(usage["cost_usd"], 4)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
