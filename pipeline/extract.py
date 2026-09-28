"""Извлечение событий, открытий, отмен и старта продаж из статей через Claude API (Haiku).

Промпт — prompts/article_extract.md, схема ответа — prompts/article_extract.schema.json.
Ключ берётся из окружения (EVENTS_ANTHROPIC_KEY); без ключа работает только оценка стоимости (--dry-run).
Текст статьи в базу не сохраняется — только результат извлечения.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone

from selectolax.parser import HTMLParser

from collectors.http import Disallowed, FetchError, PoliteClient

from . import ai_policy
from .db import ROOT
from .normalize import norm_title, title_similarity

MODEL = "claude-haiku-4-5"
PRICE_IN, PRICE_OUT = 1.00 / 1e6, 5.00 / 1e6   # $ за токен, Haiku 4.5
BATCH_DISCOUNT = 0.5                            # Message Batches API — половина цены
PROMPT = (ROOT / "prompts" / "article_extract.md").read_text()
SCHEMA = json.loads((ROOT / "prompts" / "article_extract.schema.json").read_text())
MAX_CHARS = 8000
# Источники, чьи статьи не передаём в модель (robots.txt сайта закрыт для ИИ-краулеров — уважаем волю владельца).
# Для них — только фильтр заголовков RSS по ключевым словам (keyword_news), без LLM.
NO_LLM_SOURCES = {"S097"}
# Поле tickets из ответа модели → raw_items.status (см. ingest._status: on_sale / announced / scheduled).
TICKET_STATUS = {"on_sale": "on_sale", "not_yet_on_sale": "tickets_expected", "not_required": "no_tickets"}
# Cambridge BID: слово «new» слишком общее (решение после этапа 3, часть 2) — только явные открытия/закрытия.
KEYWORD_RE = re.compile(r"\b(now open|coming soon|opening|opens|closing|closes|closed)\b", re.I)
KEYWORD_STAGE = {"coming soon": "coming_soon", "closing": "closed", "closes": "closed", "closed": "closed"}
ADDRESS_HINT = re.compile(r"\d|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b|\b(Road|Street|Lane|Square|Parade|Place)\b")
# Источники статей для извлечения.
ARTICLE_SOURCES = {"S002", "S003", "S004", "S005", "S050", "S087", "S092", "S093", "S010",
                   "S116", "S117", "S118", "S119"}
# Газеты Newsquest (решение после этапа 5): до модели — дедупликация между газетами и предфильтр по словам.
NEWSQUEST = {"S116", "S117", "S118", "S119"}
PREFILTER_RE = re.compile(
    r"\b(events?|festivals?|fairs?|f[eê]tes?|concerts?|gigs?|shows?|opening|opens|opened|reopen\w*|closing|closes|"
    r"closure|markets?|tickets?|cancel(?:led|s)?|postponed|exhibitions?|theatre|pantomime|panto|musical|comedy|"
    r"comedian|perform\w*|headline\w*|tour|screenings?|carnival|parade|fireworks|halloween|christmas|switch-on|"
    r"open day|fun day|family day|workshops?|restaurant|caf[eé]s?|pubs?|bar|shop|store|takeaway|bakery|venue|"
    r"attraction|visits?|stages?|staged|host\w*|returns|charity sale|to open|set to open|will open|welcomes?|"
    r"half[- ]term|trails?|fun run|triathlon)\b", re.I)
# Криминал, суды, аварии, продажа домов — в заголовке такой статьи событие почти никогда не главное.
PREFILTER_NEG_RE = re.compile(
    r"\b(court|jailed|sentenced|charged|arrested|police|crash|collision|died|death|killed|murder|assault\w*|"
    r"stabb\w*|burglary|fraud|scam|missing|inquest|drugs?|banned|paedophile|indecent|recall|for sale|"
    r"on the market|asking prices?|smash|steal|stole|theft)\b", re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pending(con: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    """Статьи, ждущие модель; Newsquest — только прошедшие дедупликацию и предфильтр (model='prefilter')."""
    llm = sorted(ARTICLE_SOURCES - ai_policy.no_llm_sources(con, NO_LLM_SOURCES))
    q = f"""SELECT * FROM articles WHERE extract_status='pending'
            AND source_id IN ({",".join("?" * len(llm))})
            AND (source_id NOT IN ({",".join("?" * len(NEWSQUEST))}) OR model='prefilter')
            ORDER BY published DESC""" + (f" LIMIT {int(limit)}" if limit else "")
    return con.execute(q, llm + sorted(NEWSQUEST)).fetchall()


def article_text(http: PoliteClient, url: str, fallback: str) -> tuple[str, str]:
    """(текст, откуда): абзацы <article> со страницы — 'page'; при запрете robots.txt или ошибке — анонс из RSS ('rss').

    Короткие строки берутся, если похожи на адрес (номер дома, postcode, Road/Street): адрес заведения часто
    стоит отдельной строкой в конце статьи."""
    try:
        tree = HTMLParser(http.get(url).text)
    except (Disallowed, FetchError):
        return fallback, "rss"
    root = tree.css_first("article") or tree.body
    paras = [p.text(separator=" ", strip=True) for p in (root.css("p, li") if root else [])]
    text = "\n".join(p for p in paras if len(p) > 40 or (len(p) > 5 and ADDRESS_HINT.search(p)))
    return (text[:MAX_CHARS], "page") if text else (fallback, "rss")


def request_params(title: str, published: str | None, text: str) -> dict:
    return dict(model=MODEL, max_tokens=4000, system=PROMPT,
                messages=[{"role": "user", "content": f"Publication date: {published or 'unknown'}\nTitle: {title}\n\n{text}"}],
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}})


def parse_message(msg) -> dict:
    if msg.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={msg.stop_reason}")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def call_model(client, title: str, published: str | None, text: str) -> tuple[dict, int, int]:
    msg = client.messages.create(**request_params(title, published, text))
    return parse_message(msg), msg.usage.input_tokens, msg.usage.output_tokens


def _find_event(con, name: str, date: str) -> int | None:
    nt = norm_title(name)
    rows = con.execute("SELECT event_id, norm_title FROM events WHERE date_start=?", (date,)).fetchall() if date else \
        con.execute("SELECT event_id, norm_title FROM events WHERE date_start >= date('now')").fetchall()
    best = max(rows, key=lambda r: title_similarity(nt, r["norm_title"]), default=None)
    return best["event_id"] if best and title_similarity(nt, best["norm_title"]) >= 0.8 else None


def store(con: sqlite3.Connection, art: sqlite3.Row, data: dict) -> dict:
    """Результат модели → raw_items (события пройдут общую дедупликацию), venue_news, event_updates."""
    seen, n = now(), {"events": 0, "venue_news": 0, "updates": 0}
    for i, e in enumerate(data["events"]):
        if not e["date_start"]:
            continue
        start = f"{e['date_start']}T{e['time_start']}" if e["time_start"] else e["date_start"]
        price = "Free" if e["is_free"] == "yes" and not e["price_text"] else (e["price_text"] or None)
        status = TICKET_STATUS.get(e.get("tickets", "unknown"))
        con.execute("""INSERT OR IGNORE INTO raw_items(source_id, item_key, kind, title, url, start, "end", all_day,
            venue, address, postcode, price, status, summary, first_seen_at, last_seen_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (art["source_id"], f"article:{art['article_id']}:{i}", "event", e["name"], art["url"], start,
                     e["date_end"] or None, int(not e["time_start"]), e["venue"] or None, e["address"] or None,
                     e["postcode"] or None, price, status, e["summary_ru"], seen, seen))
        n["events"] += 1
    for v in data["venue_news"]:
        if not v["name"].strip():
            continue
        # дата только полная (YYYY-MM-DD) и только с основанием: «2025» → «2025-01-01» не выдумываем
        date = v["date"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v["date"] or "") and v.get("date_basis") != "unknown" else ""
        date_basis = v.get("date_basis") if date else None
        cur = con.execute("""INSERT OR IGNORE INTO venue_news(name, type, address, postcode, stage, date, date_basis,
            source_id, source_type, url, article_id, note, first_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (v["name"], v["type"], v["address"] or None, v["postcode"] or None, v["stage"], date or None,
                           date_basis, art["source_id"], "article", art["url"], art["article_id"], v["note_ru"], seen))
        n["venue_news"] += cur.rowcount
    for c in data["cancellations"]:
        con.execute("""INSERT INTO event_updates(kind, event_name, date, new_date, event_id, article_id, source_id, url,
            first_seen_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (c["kind"], c["event_name"], c["original_date"] or None, c["new_date"] or None,
                     _find_event(con, c["event_name"], c["original_date"]), art["article_id"], art["source_id"], art["url"], seen))
        n["updates"] += 1
    for t in data["ticket_sales"]:
        eid = _find_event(con, t["event_name"], t["event_date"])
        con.execute("""INSERT INTO event_updates(kind, event_name, date, on_sale_date, event_id, article_id, source_id,
            url, first_seen_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    ("on_sale", t["event_name"], t["event_date"] or None, t["on_sale_date"] or None, eid,
                     art["article_id"], art["source_id"], art["url"], seen))
        if eid and t["on_sale_date"]:
            con.execute("UPDATE events SET on_sale_date=coalesce(on_sale_date, ?) WHERE event_id=?", (t["on_sale_date"], eid))
        n["updates"] += 1
    return n


def finish(con: sqlite3.Connection, art: sqlite3.Row, data: dict, tin: int, tout: int, text_source: str,
           batch: bool = False) -> dict:
    """Ответ модели → база и llm_usage. Batch API — половина цены."""
    cost = (tin * PRICE_IN + tout * PRICE_OUT) * (BATCH_DISCOUNT if batch else 1)
    con.execute("INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?,?,?,?)",
                (now(), "article_extract_batch" if batch else "article_extract", MODEL, art["article_id"], tin, tout, cost))
    counts = store(con, art, data)
    useful = data["is_useful"] and any(counts.values())
    con.execute("UPDATE articles SET extract_status=?, extracted_at=?, model=?, result_json=?, text_source=? WHERE article_id=?",
                ("useful" if useful else "empty", now(), MODEL, json.dumps(data, ensure_ascii=False), text_source,
                 art["article_id"]))
    return counts | {"cost": cost}


def process(con: sqlite3.Connection, http: PoliteClient, client, art: sqlite3.Row, text: str | None = None,
            text_source: str = "feed") -> dict:
    fallback = f"{art['title']}\n\n{art['summary'] or ''}"
    if not text:
        text, text_source = article_text(http, art["url"], fallback)
    data, tin, tout = call_model(client, art["title"], art["published"], text)
    return finish(con, art, data, tin, tout, text_source)


def process_batch(con: sqlite3.Connection, http: PoliteClient, client, arts: list[sqlite3.Row],
                  wait_seconds: int = 3600, poll: int = 30) -> dict:
    """Те же статьи через Message Batches API (−50 %): тексты собираются заранее, пакет отправляется одним
    запросом, результат забирается, когда пакет обработан (обычно минуты). Не дождались — статьи остаются pending,
    номер пакета — в llm_batches, результат заберёт следующий запуск (collect_batches)."""
    texts = {}
    for art in arts:
        texts[art["article_id"]] = article_text(http, art["url"], f"{art['title']}\n\n{art['summary'] or ''}")
    requests = [{"custom_id": f"art-{a['article_id']}",
                 "params": request_params(a["title"], a["published"], texts[a["article_id"]][0])} for a in arts]
    batch = client.messages.batches.create(requests=requests)
    con.execute("INSERT INTO llm_batches(batch_id, created_at, purpose, items, text_sources) VALUES (?,?,?,?,?)",
                (batch.id, now(), "article_extract", len(arts),
                 json.dumps({str(k): v[1] for k, v in texts.items()})))
    con.commit()
    deadline = time.monotonic() + wait_seconds
    while client.messages.batches.retrieve(batch.id).processing_status != "ended" and time.monotonic() < deadline:
        time.sleep(poll)
    return collect_batches(con, client)


def collect_batches(con: sqlite3.Connection, client) -> dict:
    """Результаты завершённых пакетов, ещё не забранных (llm_batches.collected_at IS NULL)."""
    totals = {"articles": 0, "events": 0, "venue_news": 0, "updates": 0, "errors": 0, "cost": 0.0, "batches_waiting": 0}
    for b in con.execute("SELECT * FROM llm_batches WHERE collected_at IS NULL").fetchall():
        if client.messages.batches.retrieve(b["batch_id"]).processing_status != "ended":
            totals["batches_waiting"] += 1
            continue
        sources = json.loads(b["text_sources"])
        for r in client.messages.batches.results(b["batch_id"]):
            aid = int(r.custom_id.split("-", 1)[1])
            art = con.execute("SELECT * FROM articles WHERE article_id=?", (aid,)).fetchone()
            try:
                if r.result.type != "succeeded":
                    raise RuntimeError(f"batch result: {r.result.type}")
                msg = r.result.message
                c = finish(con, art, parse_message(msg), msg.usage.input_tokens, msg.usage.output_tokens,
                           sources.get(str(aid), "page"), batch=True)
            except (RuntimeError, json.JSONDecodeError) as e:
                con.execute("UPDATE articles SET extract_status='error', result_json=? WHERE article_id=?",
                            (json.dumps({"error": str(e)[:300]}), aid))
                totals["errors"] += 1
                continue
            totals["articles"] += 1
            for k, v in c.items():
                totals[k] += v
        con.execute("UPDATE llm_batches SET collected_at=? WHERE batch_id=?", (now(), b["batch_id"]))
        con.commit()
    return totals


def keyword_news(con: sqlite3.Connection) -> dict:
    """Заголовки RSS источников без LLM → venue_news «требует проверки»; остальные статьи больше не обрабатываются.

    Заголовки, помеченные по прошлому фильтру, пересматриваются: запись venue_news, которой фильтр больше
    не соответствует, удаляется (так ушли ложные срабатывания на «new»)."""
    n = {"keyword_matched": 0, "keyword_skipped": 0, "keyword_dropped": 0}
    no_llm = sorted(ai_policy.no_llm_sources(con, NO_LLM_SOURCES))   # BID + ИИ-запрет при respect_ai_disallow
    src = ",".join("?" * len(no_llm))
    for art in con.execute(f"SELECT * FROM articles WHERE extract_status='keyword' AND source_id IN ({src})",
                           no_llm).fetchall():
        if not KEYWORD_RE.search(art["title"]):
            con.execute("DELETE FROM venue_news WHERE article_id=? AND source_type='rss_title'", (art["article_id"],))
            con.execute("UPDATE articles SET extract_status='skipped' WHERE article_id=?", (art["article_id"],))
            n["keyword_dropped"] += 1
    q = f"""SELECT * FROM articles WHERE source_id IN ({src}) AND (extract_status='pending'
            OR (extract_status='skipped' AND article_id NOT IN (SELECT article_id FROM venue_news WHERE article_id IS NOT NULL)))"""
    for art in con.execute(q, no_llm).fetchall():
        m = KEYWORD_RE.search(art["title"])
        if not m and art["extract_status"] == "skipped":
            continue
        if m:
            stage = KEYWORD_STAGE.get(m.group(1).lower(), "opened")
            con.execute("""INSERT OR IGNORE INTO venue_news(name, type, stage, date, source_id, source_type, url,
                article_id, note, first_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (art["title"], "другое", stage, (art["published"] or "")[:10] or None, art["source_id"],
                         "rss_title", art["url"], art["article_id"],
                         f"требует проверки: заголовок RSS без LLM (слово «{m.group(1)}»)", now()))
        con.execute("UPDATE articles SET extract_status=?, extracted_at=?, model=NULL WHERE article_id=?",
                    ("keyword" if m else "skipped", now(), art["article_id"]))
        n["keyword_matched" if m else "keyword_skipped"] += 1
    return n


def newsquest_key(url: str, title: str) -> tuple[str, str]:
    """(номер материала или slug из URL, нормализованный заголовок): /news/26586199.olly-murs-…/ → 26586199."""
    last = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    num, _, slug = last.partition(".")
    return (num if num.isdigit() else slug or last), norm_title(title)


def newsquest_prefilter(con: sqlite3.Connection) -> dict:
    """Новые статьи Newsquest до модели: 1) дубль уже виденного материала (тот же номер/slug в URL или тот же
    нормализованный заголовок в любой из четырёх газет) → duplicate; 2) нет ключевого слова в заголовке и анонсе
    или криминал/суд/авария в заголовке → filtered. Остальные остаются pending и идут в модель."""
    src = sorted(NEWSQUEST)
    q = ",".join("?" * len(src))
    keys, titles = {}, {}
    for a in con.execute(f"""SELECT article_id, url, title FROM articles WHERE source_id IN ({q})
            AND NOT (extract_status='pending' AND model IS NULL) ORDER BY article_id""", src):
        k, t = newsquest_key(a["url"], a["title"])
        keys.setdefault(k, a["article_id"])
        titles.setdefault(t, a["article_id"])
    n = {"newsquest_new": 0, "newsquest_duplicate": 0, "newsquest_filtered": 0, "newsquest_to_model": 0,
         "newsquest_refiltered": 0}
    # отсеянные прошлым списком слов пересматриваются: список расширяется (так вернулись «Gruffalo and Peppa Pig»)
    for a in con.execute(f"""SELECT * FROM articles WHERE source_id IN ({q}) AND extract_status='filtered'
            AND result_json LIKE '%нет ключевых слов%'""", src).fetchall():
        if PREFILTER_RE.search(f"{a['title']} {a['summary'] or ''}") and not PREFILTER_NEG_RE.search(a["title"]):
            con.execute("UPDATE articles SET extract_status='pending', model='prefilter', result_json=NULL WHERE article_id=?",
                        (a["article_id"],))
            n["newsquest_refiltered"] += 1
    for a in con.execute(f"""SELECT * FROM articles WHERE source_id IN ({q}) AND extract_status='pending'
            AND model IS NULL ORDER BY article_id""", src).fetchall():
        n["newsquest_new"] += 1
        k, t = newsquest_key(a["url"], a["title"])
        first = keys.get(k) or titles.get(t)
        if first:
            status, note = "duplicate", {"duplicate_of": first}
        elif not PREFILTER_RE.search(f"{a['title']} {a['summary'] or ''}"):
            status, note = "filtered", {"prefilter": "нет ключевых слов"}
        elif m := PREFILTER_NEG_RE.search(a["title"]):
            status, note = "filtered", {"prefilter": f"в заголовке «{m.group(1)}»"}
        else:
            status, note = None, None
        keys.setdefault(k, a["article_id"])
        titles.setdefault(t, a["article_id"])
        if status:
            con.execute("UPDATE articles SET extract_status=?, extracted_at=?, result_json=? WHERE article_id=?",
                        (status, now(), json.dumps(note, ensure_ascii=False), a["article_id"]))
            n[f"newsquest_{status}"] += 1
        else:
            # отметка «прошла предфильтр»: pending с model='prefilter' — ждёт модель, повторно не фильтруется
            con.execute("UPDATE articles SET model='prefilter' WHERE article_id=?", (a["article_id"],))
            n["newsquest_to_model"] += 1
    return n


def estimate(con: sqlite3.Connection, n_articles: int | None = None, avg_text_chars: int = 5000) -> dict:
    """Грубая оценка без API: ~4 символа на токен; ответ ~350 токенов."""
    n = n_articles if n_articles is not None else len(pending(con))
    tin = (len(PROMPT) + len(json.dumps(SCHEMA)) + avg_text_chars) / 4 + 150
    tout = 350
    return {"articles": n, "input_tokens_per_article": round(tin), "cost_per_article_usd": round(tin * PRICE_IN + tout * PRICE_OUT, 4),
            "total_usd": round(n * (tin * PRICE_IN + tout * PRICE_OUT), 2)}


def strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", HTMLParser(f"<div>{html}</div>").text(separator=" ")).strip()
