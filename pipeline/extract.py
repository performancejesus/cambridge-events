"""Извлечение событий, открытий, отмен и старта продаж из статей через Claude API (Haiku).

Промпт — prompts/article_extract.md, схема ответа — prompts/article_extract.schema.json.
Ключ берётся из окружения (EVENTS_ANTHROPIC_KEY); без ключа работает только оценка стоимости (--dry-run).
Текст статьи в базу не сохраняется — только результат извлечения.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from selectolax.parser import HTMLParser

from collectors.http import Disallowed, FetchError, PoliteClient

from .db import ROOT
from .normalize import norm_title, title_similarity

MODEL = "claude-haiku-4-5"
PRICE_IN, PRICE_OUT = 1.00 / 1e6, 5.00 / 1e6   # $ за токен, Haiku 4.5
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
ARTICLE_SOURCES = {"S002", "S003", "S004", "S005", "S050", "S087", "S092", "S093", "S010"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pending(con: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    q = f"""SELECT * FROM articles WHERE extract_status='pending'
            AND source_id IN ({",".join("?" * len(ARTICLE_SOURCES - NO_LLM_SOURCES))})
            ORDER BY published DESC""" + (f" LIMIT {int(limit)}" if limit else "")
    return con.execute(q, sorted(ARTICLE_SOURCES - NO_LLM_SOURCES)).fetchall()


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


def call_model(client, title: str, published: str | None, text: str) -> tuple[dict, int, int]:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=PROMPT,
        messages=[{"role": "user", "content": f"Publication date: {published or 'unknown'}\nTitle: {title}\n\n{text}"}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if msg.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={msg.stop_reason}")
    body = next(b.text for b in msg.content if b.type == "text")
    return json.loads(body), msg.usage.input_tokens, msg.usage.output_tokens


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


def process(con: sqlite3.Connection, http: PoliteClient, client, art: sqlite3.Row, text: str | None = None,
            text_source: str = "feed") -> dict:
    fallback = f"{art['title']}\n\n{art['summary'] or ''}"
    if not text:
        text, text_source = article_text(http, art["url"], fallback)
    data, tin, tout = call_model(client, art["title"], art["published"], text)
    cost = tin * PRICE_IN + tout * PRICE_OUT
    con.execute("INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?,?,?,?)",
                (now(), "article_extract", MODEL, art["article_id"], tin, tout, cost))
    counts = store(con, art, data)
    useful = data["is_useful"] and any(counts.values())
    con.execute("UPDATE articles SET extract_status=?, extracted_at=?, model=?, result_json=?, text_source=? WHERE article_id=?",
                ("useful" if useful else "empty", now(), MODEL, json.dumps(data, ensure_ascii=False), text_source,
                 art["article_id"]))
    return counts | {"cost": cost}


def keyword_news(con: sqlite3.Connection) -> dict:
    """Заголовки RSS источников без LLM → venue_news «требует проверки»; остальные статьи больше не обрабатываются.

    Заголовки, помеченные по прошлому фильтру, пересматриваются: запись venue_news, которой фильтр больше
    не соответствует, удаляется (так ушли ложные срабатывания на «new»)."""
    n = {"keyword_matched": 0, "keyword_skipped": 0, "keyword_dropped": 0}
    src = ",".join("?" * len(NO_LLM_SOURCES))
    for art in con.execute(f"SELECT * FROM articles WHERE extract_status='keyword' AND source_id IN ({src})",
                           sorted(NO_LLM_SOURCES)).fetchall():
        if not KEYWORD_RE.search(art["title"]):
            con.execute("DELETE FROM venue_news WHERE article_id=? AND source_type='rss_title'", (art["article_id"],))
            con.execute("UPDATE articles SET extract_status='skipped' WHERE article_id=?", (art["article_id"],))
            n["keyword_dropped"] += 1
    q = f"""SELECT * FROM articles WHERE source_id IN ({src}) AND (extract_status='pending'
            OR (extract_status='skipped' AND article_id NOT IN (SELECT article_id FROM venue_news WHERE article_id IS NOT NULL)))"""
    for art in con.execute(q, sorted(NO_LLM_SOURCES)).fetchall():
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


def estimate(con: sqlite3.Connection, n_articles: int | None = None, avg_text_chars: int = 5000) -> dict:
    """Грубая оценка без API: ~4 символа на токен; ответ ~350 токенов."""
    n = n_articles if n_articles is not None else len(pending(con))
    tin = (len(PROMPT) + len(json.dumps(SCHEMA)) + avg_text_chars) / 4 + 150
    tout = 350
    return {"articles": n, "input_tokens_per_article": round(tin), "cost_per_article_usd": round(tin * PRICE_IN + tout * PRICE_OUT, 4),
            "total_usd": round(n * (tin * PRICE_IN + tout * PRICE_OUT), 2)}


def strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", HTMLParser(f"<div>{html}</div>").text(separator=" ")).strip()
