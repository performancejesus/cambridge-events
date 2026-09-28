"""Этап 4 / 4b: черновик выпуска — issue_<дата>[_<версия>]_en.md и _ru.md в issues/.

Кандидаты берутся из events.db (pipeline/issue.py), отбор и тексты — Claude (Sonnet), промпт prompts/issue.md,
схема ответа prompts/issue.schema.json (рубрики — по выходным периода). Ключ — EVENTS_ANTHROPIC_KEY.

  python scripts/build_issue.py --issue 2026-10-01 --version v3     # период: дата отправки … +10 дней
  python scripts/build_issue.py --issue 2026-10-01 --start 2026-10-01 --end 2026-10-11 --version v3
  python scripts/build_issue.py ... --dry-run     # только пулы кандидатов и оценка объёма, без API
  python scripts/build_issue.py ... --from-json issues/issue_2026-10-01_v2_model.json   # перерисовать без API
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
EVENT_RUBRICS = {"theme", "weekdays", "exhibitions", "free", "kids", "sport", "out_of_town", "county"}
PREFIX_RUBRICS = {"E": EVENT_RUBRICS, "A": {"new_announcements", "tickets", "theme"}, "T": {"tickets", "theme"},
                  "C": {"cancelled"}, "V": {"new_in_town"}, "K": {"holidays"}}


def allowed(prefix: str, rubric: str) -> bool:
    return rubric in PREFIX_RUBRICS.get(prefix, set()) or (prefix == "E" and rubric.startswith("weekend_"))


def schema_for(w: issue.Window) -> dict:
    s = json.loads(json.dumps(SCHEMA))
    s["properties"]["sections"]["items"]["properties"]["rubric"]["enum"] = w.rubrics()
    return s


MAX_TOKENS = 128000
# Группы рубрик для генерации частями (решение после этапа 4b: обрезанный ответ стоил $0.73)
PART_GROUPS = [lambda w: ["theme"] + [r for r in w.rubrics() if r.startswith("weekend_")] + ["weekdays"],
               lambda w: ["exhibitions", "free", "kids", "holidays", "sport", "out_of_town", "county"],
               lambda w: ["new_announcements", "tickets", "cancelled", "new_in_town"]]
TOKENS_PER_ITEM = 450         # видимый ответ на пункт: два языка, место, цена, факты из знаний модели
THINKING_FACTOR = 4           # запас на рассуждения модели (effort medium)


def expected_output(n_items: int = 40) -> int:
    return (n_items * TOKENS_PER_ITEM + 3000) * THINKING_FACTOR


def generate(client, payload: dict, w: issue.Window, pools: issue.Pools, con, purpose: str) -> tuple[dict, int, int]:
    """Один вызов, если ожидаемый ответ с запасом помещается в MAX_TOKENS; иначе (или после обрыва по лимиту) —
    по группам рубрик: каждая часть видит только своих кандидатов и id событий, уже занятых другими частями."""
    if expected_output() < 0.8 * MAX_TOKENS:
        try:
            return call_model(client, payload, schema_for(w), con, purpose)
        except RuntimeError as e:
            if "max_tokens" not in str(e):
                raise
            print("ответ обрезан — генерирую по частям", file=sys.stderr)
    merged = {"sections": [], "editor_notes_en": [], "editor_notes_ru": []}
    tin = tout = 0
    used: list[int] = []
    for n, group in enumerate(PART_GROUPS):
        rubrics = group(w)
        prefixes = {pre for pre in PREFIX_RUBRICS if any(allowed(pre, r) for r in rubrics)}
        part = payload | {"rubrics": rubrics, "write_intro": n == 0, "already_used": used,
                          "candidates": [c for c in payload["candidates"] if c["id"][0] in prefixes
                                         and not set(pools.candidates[c["id"]]["event_ids"]) & set(used)]}
        schema = schema_for(w)
        schema["properties"]["sections"]["items"]["properties"]["rubric"]["enum"] = rubrics
        res, i, o = call_model(client, part, schema, con, f"{purpose} part {n + 1}")
        tin, tout = tin + i, tout + o
        if n == 0:
            merged |= {k: v for k, v in res.items() if k.startswith(("intro_", "theme_"))}
        merged["sections"] += res["sections"]
        merged["editor_notes_en"] += res["editor_notes_en"]
        merged["editor_notes_ru"] += res["editor_notes_ru"]
        used += [e for sec in res["sections"] for it in sec["items"] for cid in it["ids"]
                 if cid in pools.candidates for e in pools.candidates[cid]["event_ids"]]
    return merged, tin, tout


def call_model(client, payload: dict, schema: dict, con, purpose: str) -> tuple[dict, int, int]:
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "medium"},
    ) as stream:
        msg = stream.get_final_message()
    # расход записываем и тогда, когда ответ непригоден (обрезан или отказ)
    tin, tout = msg.usage.input_tokens, msg.usage.output_tokens
    con.execute("""INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd)
        VALUES (?,?,?,?,?,?,?)""", (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    purpose + ("" if msg.stop_reason == "end_turn" else f" ({msg.stop_reason})"),
                                    MODEL, None, tin, tout, tin * PRICE_IN + tout * PRICE_OUT))
    con.commit()
    if msg.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={msg.stop_reason}")
    body = next(b.text for b in msg.content if b.type == "text")
    return json.loads(body), msg.usage.input_tokens, msg.usage.output_tokens


def fits(rubric: str, c: dict, w: issue.Window) -> bool:
    """Выходные — событие в эти выходные и оценка ≥ 7; «На неделе» — есть день пн–пт; «С детьми» и «Бесплатно» —
    по тегам из данных; «за городом» и «по графству» — по зоне."""
    imp = c.get("importance") or 0
    if rubric.startswith("weekend_"):
        # правки по v3: длительные выставки — не сюда; «Кембриджшир, дальше часа» — только от 8
        if c.get("long_running") or (c.get("zone") == issue.geo_COUNTY_FAR and imp < issue.COUNTY_WEEKEND_MIN):
            return False
        return rubric in c.get("on_weekends", []) and imp >= issue.WEEKEND_MIN
    if rubric == "weekdays":
        return bool(c.get("on_weekdays"))
    if rubric == "exhibitions":
        return bool(c.get("long_running"))
    if rubric == "holidays":
        return c.get("kind") == "programme"
    if rubric == "kids":
        return bool(c.get("kids_tag"))
    if rubric == "free":
        return bool(c.get("free_tag"))
    if rubric == "out_of_town":   # правки по v3: не ниже 4, без распродаж и барахолок
        return c.get("zone") in issue.OUT_OF_TOWN and imp >= issue.OUT_OF_TOWN_MIN and not c.get("sale")
    if rubric == "county":
        return c.get("zone") == issue.geo_COUNTY_FAR and imp >= issue.OUT_OF_TOWN_MIN and not c.get("sale")
    return True


NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _nums(text: str) -> set[float]:
    text = re.sub(r"(\d),(\d{2})\b", r"\1.\2", text or "")   # «£38,50» в русском тексте
    return {round(float(x), 2) for x in NUM_RE.findall(text.replace(",", ""))}


def check_price(it: dict, cands: list[dict]) -> tuple[str, str] | None:
    """Цифры цены в тексте модели должны быть в данных любого из кандидатов пункта (price_text, price_from, summary);
    иначе — цена из данных (правки по v3: значение из данных, а не «цена не указана», если оно есть у любого id)."""
    c = cands[0]
    known = set()
    for x in cands:
        known |= _nums(x.get("price_text")) | _nums(x.get("summary")) | _nums(x.get("note"))
        if x.get("price_from") is not None:
            known.add(round(float(x["price_from"]), 2))
    known |= {round(x) for x in known}
    wrong = {x for x in _nums(it["price_en"]) | _nums(it["price_ru"]) if x not in known}
    if not wrong or c["kind"] == "venue_news":
        return None
    priced = next((x for x in cands if x.get("price_text") or x.get("price_from") is not None), c)
    en, ru = issue.price_from_data(priced)
    it["price_en"], it["price_ru"] = en, ru
    return (f"“{it['title_en']}”: price in the model text did not match the data ({sorted(wrong)}) — replaced with “{en}”",
            f"«{it['title_ru']}»: цена в тексте модели не совпала с данными ({sorted(wrong)}) — заменена на «{ru}»")


HOMOGLYPHS = str.maketrans("aeopcxyAEOPCXHBKMT", "аеорсхуАЕОРСХНВКМТ")
TO_LATIN = str.maketrans("аеорсхуАЕОРСХНВКМТ", "aeopcxyAEOPCXHBKMT")
MIXED_RE = re.compile(r"\b(?=\w*[а-яё])(?=\w*[a-z])\w+\b", re.I)
LATIN_RE = re.compile(r"\b[a-z]{4,}\b")
CYRILLIC_RE = re.compile(r"\b\w*[а-яё]\w*\b", re.I)


def check_alphabets(result: dict, pools: issue.Pools) -> list[tuple[str, str]]:
    """Смешанные алфавиты в обе стороны (правки по v2). Русский текст: латинские буквы-двойники внутри русских слов
    («Ирландa») — исправить; остальные смешанные слова («морris») — редактору; латинские слова в нижнем регистре,
    которых нет в данных кандидатов («afishas»), — редактору. Английский текст: кириллица внутри слов — двойники
    исправить, остальное — редактору."""
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
            else:
                notes.append((f"Russian text: mixed Cyrillic and Latin in «{word}» — rewrite the word",
                              f"русский текст: кириллица и латиница в одном слове «{word}» — переписать слово"))
        for word in LATIN_RE.findall(obj[f]):
            if word not in known:
                notes.append((f"Russian text: the Latin word «{word}» is not in the source data — check the wording",
                              f"русский текст: латинское слово «{word}» не из данных — проверить формулировку"))
    fields = [(result, "intro_en"), (result, "theme_title_en"), (result, "theme_intro_en")] + \
        [(it, f) for sec in result["sections"] for it in sec["items"] for f in ("title_en", "where_en", "price_en", "blurb_en")]
    for obj, f in fields:
        for word in CYRILLIC_RE.findall(obj.get(f) or ""):
            fixed = word.translate(TO_LATIN)
            if re.fullmatch(r"[a-z]+", fixed, re.I) and re.search(r"[a-z]", word, re.I):
                obj[f] = obj[f].replace(word, fixed)
                notes.append((f"English text: Cyrillic letters inside the word “{fixed}” — fixed",
                              f"английский текст: кириллические буквы в слове «{fixed}» — исправлено"))
            else:
                notes.append((f"English text: Cyrillic in “{word}” — rewrite",
                              f"английский текст: кириллица в «{word}» — переписать"))
    return notes


# «Greggs (coming soon)» при строке «Скоро откроется» — статус уже в метаданных пункта (правки по v2)
STATUS_IN_TITLE_RE = re.compile(
    r"\s*(?:[(\[]\s*(?:coming soon|opening soon|now open|newly opened|just opened|opened|opens?|opening|closing|closed|"
    r"closes|скоро открыти\w*|скоро откро\w*|открыти\w*|открыл\w*|открыва\w*|откро\w*|закрыти\w*|закрыл\w*|"
    r"закрыва\w*|закро\w*)\b[^)\]]*[)\]]|\s+[—–-]\s+(?:coming soon|now open|opening soon|closed|скоро открытие|"
    r"скоро откроется|открылось|открылся|открылась|закрылось|закрылся|закрылась))\s*$", re.I)


def strip_status(result: dict, pools: issue.Pools) -> list[tuple[str, str]]:
    """Статус открытия/закрытия в названии пункта «Новое в городе» — убрать: он уже стоит в строке с датой."""
    notes = []
    for sec in result["sections"]:
        for it in sec["items"]:
            if pools.candidates[it["ids"][0]]["kind"] != "venue_news":
                continue
            for lang in ("en", "ru"):
                t = it[f"title_{lang}"]
                clean = STATUS_IN_TITLE_RE.sub("", t).strip()
                if clean and clean != t:
                    it[f"title_{lang}"] = clean
                    notes.append((f"“{t}”: status removed from the title (it is in the date line)",
                                  f"«{t}»: статус убран из названия (он есть в строке с датой)"))
    return notes


def apply_links(result: dict, pools: issue.Pools) -> list[tuple[str, str]]:
    """Связанные события (data/issue_links.json) — один пункт: если модель дала их отдельными пунктами,
    второй вливается в первый; если взяла только одно — второе добавляется в тот же пункт."""
    notes = []
    for ids, label in pools.links:
        holders = [(sec, it) for sec in result["sections"] for it in sec["items"] if set(it["ids"]) & set(ids)]
        if not holders:
            continue
        sec0, first = holders[0]
        for sec, it in holders[1:]:
            sec["items"].remove(it)
        missing = [i for i in ids if i not in first["ids"]]
        if len(holders) > 1 or missing:
            first["ids"] += missing
            notes.append((f"“{first['title_en']}”: linked events {ids} ({label}) put into one item — check the title and text",
                          f"«{first['title_ru']}»: связанные события {ids} ({label}) сведены в один пункт — проверить название и текст"))
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
            ids.sort(key=lambda i: not allowed(i[0], sec["rubric"]))
            prefix = ids[0][0] if ids else ""
            events = {e for i in ids for e in pools.candidates[i]["event_ids"]}
            if not ids or any(i in used for i in ids) or events & used_events:
                notes.append((f"“{it['title_en']}”: empty or repeated item — removed",
                              f"«{it['title_ru']}»: пустой или повторный пункт — убран"))
                continue
            if not allowed(prefix, sec["rubric"]) or not fits(sec["rubric"], pools.candidates[ids[0]], w):
                notes.append((f"“{it['title_en']}” ({ids[0]}) does not fit rubric {sec['rubric']} — removed",
                              f"«{it['title_ru']}» ({ids[0]}) не подходит для рубрики {sec['rubric']} — убран"))
                continue
            fixed = check_price(it, [pools.candidates[i] for i in ids])
            if fixed:
                notes.append(fixed)
            used.update(ids)
            used_events.update(events)
            kept.append(it | {"ids": ids})
        sec["items"] = kept
        if sec["rubric"].startswith("weekend_") and len(kept) > issue.WEEKEND_MAX:
            kept.sort(key=lambda it: -issue.importance_of(pools, it))
            for it in kept[issue.WEEKEND_MAX:]:
                notes.append((f"“{it['title_en']}”: more than {issue.WEEKEND_MAX} items for the weekend — removed",
                              f"«{it['title_ru']}»: на выходные больше {issue.WEEKEND_MAX} пунктов — убран"))
            sec["items"] = kept[:issue.WEEKEND_MAX]
        # «Тема недели» держится на событии с оценкой ≥ 7
        if sec["rubric"] == "theme" and kept and max(issue.importance_of(pools, it) for it in kept) < issue.HEADLINE_MIN:
            notes.append(("theme of the week has no event with importance ≥ 7 — section removed",
                          "в «Теме недели» нет события с оценкой ≥ 7 — блок убран"))
            sec["items"] = []
    # события ≥ 7 на выходных обязаны быть в «Главном» или в «Теме недели»
    placed = {e for sec in result["sections"] if sec["rubric"] == "theme" or sec["rubric"].startswith("weekend_")
              for it in sec["items"] for i in it["ids"] for e in pools.candidates[i]["event_ids"]}
    for cid, c in pools.candidates.items():
        if c["kind"] == "event" and c.get("on_weekends") and (c.get("importance") or 0) >= issue.HEADLINE_MIN \
                and any(fits(r, c, w) for r in c["on_weekends"]) and not set(c["event_ids"]) & placed:
            notes.append((f"“{c['title']}” ({cid}, {c['importance']:g}) is on a weekend with importance ≥ 7 but not in “The weekend”",
                          f"«{c['title']}» ({cid}, {c['importance']:g}) — на выходных, оценка ≥ 7, но не в «Главном»"))
    # правки по v3: состав (performer из оценки известности) должен дойти до текста пункта
    for sec in result["sections"]:
        for it in sec["items"]:
            names = {pools.candidates[i].get("performer") for i in it["ids"]} - {None, ""}
            text = f"{it['title_en']} {it['blurb_en']}".lower()
            for name in names:
                if name.lower() not in text:
                    notes.append((f"“{it['title_en']}”: the performer from the data ({name}) is not named in the text",
                                  f"«{it['title_ru']}»: исполнитель из данных ({name}) не назван в тексте"))
    return notes


CLAUDE_USER_BLOCKED = {"S116", "S117", "S118", "S119"}          # Newsquest: закрыт и Claude-User
TRAINING_BLOCKED = {"S003", "S004", "S010", "S092", "S093"}     # закрыты боты обучения/поиска, Claude-User открыт


def ai_measure(result: dict, pools: issue.Pools) -> dict:
    """Замер для решения об ИИ-запретах (бриф, открытый вопрос): сколько пунктов выпуска пришло ТОЛЬКО из источников
    с запретом Claude-User и сколько — только из источников с запретом ботов обучения/поиска; что исчезло бы
    в режимах claude_user_only и any_ai_agent."""
    only_cu, only_train, lost_any = [], [], []
    for sec in result["sections"]:
        for it in sec["items"]:
            srcs = set()
            for i in it["ids"]:
                srcs |= set(pools.candidates[i].get("sources") or [])
            if not srcs:
                continue
            if srcs <= CLAUDE_USER_BLOCKED:
                only_cu.append(it["title_en"])
            elif srcs <= TRAINING_BLOCKED:
                only_train.append(it["title_en"])
            if srcs <= CLAUDE_USER_BLOCKED | TRAINING_BLOCKED:
                lost_any.append(it["title_en"])
    return {"only_claude_user_blocked": only_cu, "only_training_blocked": only_train, "lost_any_ai_agent": lost_any}


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
            unv_en.append(f"{t} ({cid}): no ticket-sale data (ADC / Cambridge United / Peterborough United) — the source does not publish a status")
            unv_ru.append(f"{t} ({cid}): нет данных о продаже (ADC / Cambridge United / Peterborough United) — статус у источника не публикуется")
        if c.get("address_unknown"):
            unv_en.append(f"{t} ({cid}): no postcode — zone «центр» assumed from the city (address_unknown)")
            unv_ru.append(f"{t} ({cid}): нет postcode — зона «центр» условно, по городу (address_unknown)")
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
        unv_en.append(f"{pools.unverified_news} RSS headline(s) from sources processed without the model matched the opening/closing keywords — not used, need a manual check")
        unv_ru.append(f"заголовков RSS по ключевым словам из источников без модели — {pools.unverified_news}; в выпуск не взяты, нужна ручная проверка")

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
    for rub in w.rubrics():
        we = w.weekend_of(rub)
        if we and counts.get(rub, 0) < 3:
            best = sorted((c for c in pools.candidates.values() if c["kind"] == "event" and rub in c.get("on_weekends", [])),
                          key=lambda c: -(c.get("importance") or 0))[:5]
            lst = "; ".join(f"{c['title']} — {c.get('importance') or 0:g}" for c in best)
            out_en.append(f"{issue.rubric_title(rub, w, 'en')}: fewer than 3 events with importance ≥ 7; best of that weekend: {lst}")
            out_ru.append(f"{issue.rubric_title(rub, w, 'ru')}: меньше трёх событий с оценкой ≥ 7; лучшие в эти выходные: {lst}")
    for sec in result["sections"]:
        for it in sec["items"]:
            if issue.importance_of(pools, it) >= issue.LONG_BLURB_MIN and len(re.findall(r"[.!?](\s|$)", it["blurb_en"])) < 2:
                fix_notes.append((f"“{it['title_en']}”: importance ≥ 8 but the description is one sentence (the brief asks for 2–3)",
                                  f"«{it['title_ru']}»: оценка ≥ 8, а описание в одно предложение (по брифу — 2–3)"))

    cnt_en, cnt_ru = [], []
    for rub in w.rubrics():
        n = counts.get(rub, 0)
        flag = "" if 3 <= n <= 6 else (" ⚠️ below 3" if n < 3 else " ⚠️ above 6")
        flag_ru = "" if 3 <= n <= 6 else (" ⚠️ меньше 3" if n < 3 else " ⚠️ больше 6")
        label_en = "Theme of the week" if rub == "theme" else issue.rubric_title(rub, w, "en")
        label_ru = "Тема недели" if rub == "theme" else issue.rubric_title(rub, w, "ru")
        cnt_en.append(f"{label_en}: {n}{flag}")
        cnt_ru.append(f"{label_ru}: {n}{flag_ru}")
    cnt_en.append(f"total: {total} (target 25–40)")
    cnt_ru.append(f"всего: {total} (цель 25–40)")

    cost = (f"{MODEL}: {usage['input_tokens']} input + {usage['output_tokens']} output tokens = "
            f"${usage['cost_usd']:.4f}")
    know_en, know_ru, imp_en, imp_ru = [], [], [], []
    for sec in result["sections"]:
        for it in sorted(sec["items"], key=lambda it: -issue.importance_of(pools, it)):
            know_en += [f"{it['title_en']}: {k}" for k in it.get("knowledge_en", [])]
            know_ru += [f"{it['title_ru']}: {k}" for k in it.get("knowledge_ru", [])]
            c = pools.candidates[it["ids"][0]]
            score = issue.importance_of(pools, it)
            if c["kind"] != "venue_news" and score:
                imp_en.append(f"{score:g} — {it['title_en']} [{sec['rubric']}]: {c.get('importance_reason') or ''}")
                imp_ru.append(f"{score:g} — {it['title_ru']} [{sec['rubric']}]: {c.get('importance_reason') or ''}")
    fixes_en = [f"output check: {en}" for en, _ in fix_notes]
    fixes_ru = [f"проверка ответа: {ru}" for _, ru in fix_notes]
    fixes_en += [f"review: {en}" for en, _ in review]
    fixes_ru += [f"ревью: {ru}" for _, ru in review]
    return {
        "en": [("Doubtful items and model notes", result["editor_notes_en"] + fixes_en),
               ("Possible duplicates the pipeline did not merge", dups_en),
               ("Facts from the model's general knowledge (check)", know_en),
               ("Unverified status", unv_en),
               ("What didn't make it and why", out_en),
               ("Items per rubric", cnt_en),
               ("Importance of the chosen items (score — reason)", imp_en),
               ("Claude API cost of this draft", [cost])],
        "ru": [("Сомнительные пункты и заметки модели", result["editor_notes_ru"] + fixes_ru),
               ("Возможные дубли, которые не склеились", dups_ru),
               ("Факты из знаний модели (проверить)", know_ru),
               ("Непроверенный статус", unv_ru),
               ("Что не попало и почему", out_ru),
               ("Пунктов по рубрикам", cnt_ru),
               ("Важность выбранных пунктов (оценка — причины)", imp_ru),
               ("Расход Claude API на черновик", [cost])],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", required=True)
    ap.add_argument("--start", help="по умолчанию — дата отправки (раньше нельзя: события уже прошли)")
    ap.add_argument("--end", help=f"по умолчанию — дата отправки + {issue.WINDOW_DAYS} дней")
    ap.add_argument("--version", default="", help="суффикс файлов: v2 → issue_<дата>_v2_en.md")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-json", help="не вызывать API, взять сохранённый ответ модели")
    args = ap.parse_args()
    sent = date.fromisoformat(args.issue)
    w = issue.Window(sent, date.fromisoformat(args.start) if args.start else sent,
                     date.fromisoformat(args.end) if args.end else sent + timedelta(days=issue.WINDOW_DAYS))
    stem = f"issue_{args.issue}" + (f"_{args.version}" if args.version else "")
    con = connect()
    pools = issue.build_pools(con, w)
    payload = {"issue_date": args.issue, "period": [w.start.isoformat(), w.end.isoformat()],
               "weekends": {f"weekend_{i + 1}": [a.isoformat(), b.isoformat()] for i, (a, b) in enumerate(w.weekends)},
               "rubrics": w.rubrics(),
               "candidates": issue.model_view(pools)}
    out_dir = ROOT / "issues"
    out_dir.mkdir(exist_ok=True)
    kinds = Counter(c["kind"] for c in pools.candidates.values())
    print(json.dumps({"candidates": kinds, "excluded": {k: len(v) for k, v in pools.excluded.items()},
                      "duplicates": len(pools.duplicates), "payload_chars": len(json.dumps(payload, ensure_ascii=False))},
                     ensure_ascii=False), file=sys.stderr)
    if args.dry_run:
        return
    raw_path = out_dir / f"{stem}_model.json"
    if args.from_json:
        saved = json.loads(Path(args.from_json).read_text())
        result, usage = saved["result"], saved["usage"]
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
        result, tin, tout = generate(client, payload, w, pools, con, f"issue {stem[6:]}")
        usage = {"input_tokens": tin, "output_tokens": tout, "cost_usd": tin * PRICE_IN + tout * PRICE_OUT}
        raw_path.write_text(json.dumps({"result": result, "usage": usage}, ensure_ascii=False, indent=1))
    fix_notes = apply_links(result, pools) + validate(result, pools, w) \
        + strip_status(result, pools) + check_alphabets(result, pools)
    # ручные правки и заметки ревью, записанные в сохранённый ответ модели (issues/issue_<дата>_model.json)
    review = [tuple(x) for x in result.get("manual_fixes", []) + result.get("review_notes", [])]
    editor = editor_block(result, pools, w, fix_notes, review, usage)
    m = ai_measure(result, pools)
    measure = {"en": [f"only from sources that block Claude-User (Newsquest S116–S119; lost in claude_user_only): {len(m['only_claude_user_blocked'])}"
                      + (f" — {'; '.join(m['only_claude_user_blocked'])}" if m['only_claude_user_blocked'] else ""),
                      f"only from sources that block training/search bots (S003, S004, S010, S092, S093): {len(m['only_training_blocked'])}"
                      + (f" — {'; '.join(m['only_training_blocked'])}" if m['only_training_blocked'] else ""),
                      f"lost in any_ai_agent mode (only from any of these sources): {len(m['lost_any_ai_agent'])}"],
               "ru": [f"только из источников с запретом Claude-User (Newsquest S116–S119; пропадут в режиме claude_user_only): {len(m['only_claude_user_blocked'])}"
                      + (f" — {'; '.join(m['only_claude_user_blocked'])}" if m['only_claude_user_blocked'] else ""),
                      f"только из источников с запретом ботов обучения/поиска (S003, S004, S010, S092, S093): {len(m['only_training_blocked'])}"
                      + (f" — {'; '.join(m['only_training_blocked'])}" if m['only_training_blocked'] else ""),
                      f"пропадут в режиме any_ai_agent (только из любого из этих источников): {len(m['lost_any_ai_agent'])}"]}
    kd = json.loads((ROOT / "data" / "kids_programmes.json").read_text())
    unv = [f"{p['provider']} — {p['title']}: {p.get('note', '')}" for p in kd["programmes"] if not p.get("verified")]
    unv += [f"{n}: {why}" for n, _, why in kd["not_verified"]]
    editor["en"].insert(-1, ("AI disallow in robots.txt: what this issue would lose", measure["en"]))
    editor["ru"].insert(-1, ("ИИ-запреты в robots.txt: что пропало бы из выпуска", measure["ru"]))
    editor["en"].insert(-1, ("Holiday programmes not verified on the provider site", unv))
    editor["ru"].insert(-1, ("Детские программы, не проверенные на сайте провайдера", unv))
    (out_dir / f"{stem}_ai_measure.json").write_text(json.dumps(m, ensure_ascii=False, indent=1))
    for lang in ("en", "ru"):
        path = out_dir / f"{stem}_{lang}.md"
        path.write_text(issue.render(result, pools, w, lang, editor))
        print(path.relative_to(ROOT))
        reader = out_dir / f"{stem}_reader_{lang}.html"   # читательская версия без блока «Для редактора»
        reader.write_text(issue.render_reader_html(result, pools, w, lang))
        print(reader.relative_to(ROOT))
    counts = {sec["rubric"]: len(sec["items"]) for sec in result["sections"]}
    print(json.dumps({"items": counts, "total": sum(counts.values()), "cost_usd": round(usage["cost_usd"], 4)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
