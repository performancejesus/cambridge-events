"""Этап 7c (п. 3a): термкарта Cambridge Union на Issuu → кандидаты событий (гость или тема, дата, доступ).

Программа гостей и дебатов клуба выходит не в списке событий cus.org (там только билетные мероприятия), а в termcard —
журнале из картинок на Issuu (issuu.com/thecambridgeunion). Текста в нём нет: страницы распознаёт модель с изображениями,
одним запросом на termcard (правило этапа 8 из брифа). robots.txt: issuu.com разрешает /<издатель>/docs/… для всех
агентов, ИИ-агентов отдельно не закрывает; image.isu.pub отвечает на robots.txt 403 — по RFC 9309 «правил нет».
Запросы — наш честный бот (collectors/http.py), паузы; изображения — в data/cache/issuu/ (не в git).

Найденное — кандидаты (таблица union_termcard), не события: подтверждение — страница события на cus.org или страница
продажи билетов. В выпуск — одной компактной строкой «В Cambridge Union на этой неделе (для членов клуба): …».
"""

from __future__ import annotations

import base64
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .db import ROOT

PROFILE = "https://issuu.com/thecambridgeunion"
CACHE = ROOT / "data" / "cache" / "issuu"
MODELS = {"claude-haiku-4-5": (1e-6, 5e-6), "claude-sonnet-5": (2e-6, 10e-6)}
MODEL = "claude-haiku-4-5"
WIDTH = 900                               # ширина страницы для модели (оригинал 2112 px)
SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS union_termcard (
    doc TEXT, term TEXT, date TEXT, time TEXT, title TEXT, speakers TEXT, kind TEXT, access TEXT, venue TEXT,
    page INTEGER, note TEXT, extracted_at TEXT, confirmed_url TEXT,
    PRIMARY KEY (doc, date, title)
)"""
PROMPT = """These are the pages of a Cambridge Union Society termcard (a printed programme for one university term).
List every dated event of the programme: debates (with the motion), speaker events and "in conversation", panels,
socials, balls, workshops, competitions. For each: date (YYYY-MM-DD; the year is {year} unless the page says otherwise),
time if printed (HH:MM, 24h), title (the motion for a debate, otherwise the event name), speakers (named guests, as
printed, empty list if none), kind (debate / speaker / panel / social / other), access as printed or implied
("members" — members only, the default for chamber events; "open" — open to the public / free for all; "ticketed" —
separate tickets; "unknown"), venue (Chamber, Library, The Orator, …) and the page number. Skip adverts, history
articles and pages without dated events. Use only what is printed; never guess dates."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["term", "events"], "properties": {
    "term": {"type": "string"},
    "events": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                          "required": ["date", "time", "title", "speakers", "kind", "access", "venue", "page"],
                                          "properties": {"date": {"type": "string"}, "time": {"type": ["string", "null"]},
                                                         "title": {"type": "string"},
                                                         "speakers": {"type": "array", "items": {"type": "string"}},
                                                         "kind": {"type": "string", "enum": ["debate", "speaker", "panel", "social", "other"]},
                                                         "access": {"type": "string", "enum": ["members", "open", "ticketed", "unknown"]},
                                                         "venue": {"type": ["string", "null"]}, "page": {"type": "integer"}}}}}}


def init(con) -> None:
    con.execute(SCHEMA_SQL)


def list_docs(http) -> list[dict]:
    """Документы издателя с датой публикации (JSON в странице профиля)."""
    t = http.get(PROFILE).text.replace('\\"', '"')
    out = []
    for m in re.finditer(r'"publishDate":\{"year":(\d+),"month":(\d+),"day":(\d+)\}', t):
        seg = t[max(0, m.start() - 1500):m.start() + 800]
        uri = re.findall(r'"uri":"(thecambridgeunion/docs/[^"]+)"', seg)
        title = re.findall(r'"title":"([^"]+)"', seg)
        if uri:
            out.append({"doc": uri[-1].split("/docs/")[1], "title": title[-1] if title else "",
                        "published": f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"})
    return list({x["doc"]: x for x in out}.values())


def pages(http, doc: str) -> tuple[str, list[Path]]:
    """Скачать страницы документа (кэш на диске); → (id документа Issuu, пути к картинкам)."""
    html = http.get(f"https://issuu.com/thecambridgeunion/docs/{doc}").text
    doc_id = re.search(r"image\.isu\.pub/([0-9a-f-]+)/jpg/page_1", html).group(1)
    n = int(re.search(r'pageCount\\?":(\d+)', html).group(1))
    folder = CACHE / doc
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(1, n + 1):
        p = folder / f"page_{i}.jpg"
        if not p.exists():
            p.write_bytes(http.get(f"https://image.isu.pub/{doc_id}/jpg/page_{i}.jpg").content)
        paths.append(p)
    return doc_id, paths


def _small(p: Path) -> str:
    from PIL import Image
    im = Image.open(p).convert("RGB")
    if im.width > WIDTH:
        im = im.resize((WIDTH, round(im.height * WIDTH / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return base64.standard_b64encode(buf.getvalue()).decode()


def extract(con, client, doc: str, paths: list[Path], year: int, model: str = MODEL) -> tuple[dict, float]:
    """Один запрос с изображениями всех страниц → события termcard; результат — в union_termcard."""
    con.execute(SCHEMA_SQL)
    content = []
    for i, p in enumerate(paths, 1):
        content += [{"type": "text", "text": f"Page {i}"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _small(p)}}]
    content.append({"type": "text", "text": "List the dated events of this termcard."})
    with client.messages.stream(model=model, max_tokens=32000, system=PROMPT.format(year=year),
                                messages=[{"role": "user", "content": content}],
                                output_config={"format": {"type": "json_schema", "schema": SCHEMA}}) as st:
        msg = st.get_final_message()
    cost = msg.usage.input_tokens * MODELS[model][0] + msg.usage.output_tokens * MODELS[model][1]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd) "
                "VALUES (?,?,?,?,?,?,?)", (now, f"union termcard {doc}", model, None, msg.usage.input_tokens,
                                           msg.usage.output_tokens, cost))
    res = json.loads(next(b.text for b in msg.content if b.type == "text"))
    for e in res["events"]:
        con.execute("INSERT OR REPLACE INTO union_termcard VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (doc, res["term"], e["date"], e["time"], e["title"], json.dumps(e["speakers"], ensure_ascii=False),
                     e["kind"], e["access"], e["venue"], e["page"], None, now, None))
    con.commit()
    return res | {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}, cost


def week_line(con, start: str, end: str) -> list[dict]:
    """Кандидаты termcard в окне выпуска: события для членов клуба с названными гостями (для компактной строки)."""
    con.execute(SCHEMA_SQL)
    rows = con.execute("SELECT * FROM union_termcard WHERE date BETWEEN ? AND ? ORDER BY date, time", (start, end)).fetchall()
    return [dict(r) | {"speakers": json.loads(r["speakers"] or "[]")} for r in rows]


MEMBERSHIP_URL = "https://cus.org/membership"
TERMCARD_URL = "https://cus.org/whats-on/termcard"
DAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
DAYS_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MON_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября",
          "декабря"]


def line_item(con, start, end, fee: str | None = None) -> tuple[dict | None, list[tuple[str, str]]]:
    """Компактная строка «В Cambridge Union на этой неделе (для членов клуба): …» из termcard (не из Varsity: статья —
    только кандидат). Гости и дебаты с названными участниками; события «open» — обычными пунктами через cus.org, здесь
    только пометка редактору."""
    from datetime import date as _d
    init(con)
    rows = [r for r in week_line(con, start.isoformat(), end.isoformat()) if not r["doc"].startswith("varsity:")]
    notes = []
    var = con.execute("SELECT count(*) FROM union_termcard WHERE doc LIKE 'varsity:%' AND date BETWEEN ? AND ?",
                      (start.isoformat(), end.isoformat())).fetchone()[0]
    if var:
        notes.append((f"Cambridge Union: {var} candidate(s) from Varsity in the window — not confirmed by the termcard",
                      f"Cambridge Union: кандидатов из статей Varsity в окне — {var}; termcard их ещё не подтвердила"))
    if not rows:
        docs = con.execute("SELECT DISTINCT term FROM union_termcard WHERE doc NOT LIKE 'varsity:%'").fetchall()
        notes.append(("Cambridge Union: no termcard for this term yet (Issuu) — no line",
                      "Cambridge Union: termcard на этот триместр ещё не вышла (Issuu; разобраны: "
                      + ", ".join(sorted(r[0] for r in docs)) + ") — строки нет"))
        return None, notes
    parts_en, parts_ru = [], []
    for r in rows:
        if r["kind"] not in ("debate", "speaker", "panel") or not [s for s in r["speakers"] if "student" not in s.lower()
                                                                   and "announced" not in s.lower() and s != "TBA"]:
            continue
        if r["access"] == "open":   # модель по картинкам отмечает «open» щедро (проба Lent 2026: 20 из 41) — в строке
            # остаётся, а полным пунктом событие выйдет, только когда cus.org подтвердит «Open To The Public»
            notes.append((f"Cambridge Union: “{r['title']}” ({r['date']}) may be open to the public (termcard) — check cus.org",
                          f"Cambridge Union: «{r['title']}» ({r['date']}) по termcard, возможно, открыто для всех — "
                          "проверить на cus.org; полным пунктом — после подтверждения"))
        d = _d.fromisoformat(r["date"])
        names = [s for s in r["speakers"] if "student" not in s.lower() and "announced" not in s.lower() and s != "TBA"][:3]
        who = ", ".join(names)
        if r["kind"] == "debate":
            parts_en.append(f"debate “{r['title']}” with {who} ({DAYS_EN[d.weekday()]} {d.day})")
            parts_ru.append(f"дебаты «{r['title']}» — {who} ({DAYS_RU[d.weekday()]}, {d.day} {MON_RU[d.month - 1]})")
        else:
            parts_en.append(f"{who} ({DAYS_EN[d.weekday()]} {d.day})")
            parts_ru.append(f"{who} ({DAYS_RU[d.weekday()]}, {d.day} {MON_RU[d.month - 1]})")
    if not parts_ru:
        return None, notes
    fee_en = f"membership {fee} a year" if fee else "membership"
    fee_ru = f"членство — {fee} в год" if fee else "членство"
    return {"ids": [], "union": True,   # id кандидата U1 назначает build_issue "auto": True, "url": TERMCARD_URL,
            "title_en": "At the Cambridge Union (members only): " + "; ".join(parts_en),
            "title_ru": "В Cambridge Union на этой неделе (для членов клуба): " + "; ".join(parts_ru),
            "meta_en": f"{fee_en} · termcard", "meta_ru": f"{fee_ru} · программа триместра (termcard)",
            "where_en": "", "where_ru": "", "price_en": "", "price_ru": "", "blurb_en": "", "blurb_ru": "",
            "knowledge_en": [], "knowledge_ru": []}, notes
