"""Оценка важности будущих событий: importance_score (1–10) и importance_reason.

Сигналы из базы: вместимость площадки (data/venue_capacity.json), верхняя цена билета, число источников, статья
в новостях, sold out, ежегодный флагман (recurring_events). Внешние: Wikipedia (есть ли статья, просмотры за 30 дней;
кэш wiki_cache). Футбол: турнир по метке в календаре клуба ([FA], [LC], [EFLT], без метки — чемпионат), дерби,
соперник из Премьер-лиги. Оценка известности моделью (Claude, кэш fame_cache) — один из сигналов, «неизвестно» = 0.
Итог: base + сумма (вес × сигнал 0..1), не больше 10; веса — data/importance_weights.json.

Решения после этапа 4b: Wikipedia и известность — только за того, кто на сцене (performer); трибьюты, шоу «по мотивам»
и составы с одним известным именем — с потолком; у постановок классики известность пьесы не считается (считается
труппа); бесплатно / цена неизвестна и площадка без вместимости — нейтральный сигнал, а не ноль; у лекций без билетов
вес известности выступающего выше. Пересчёт — только для событий, у которых изменились входные данные (сигнатура).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import hashlib

import httpx

from .db import ROOT

MODEL = "claude-sonnet-5"
PRICE_IN, PRICE_OUT = 2.00 / 1e6, 10.00 / 1e6
PROMPT = (ROOT / "prompts" / "importance.md").read_text()
SCHEMA = json.loads((ROOT / "prompts" / "importance.schema.json").read_text())
WEIGHTS = json.loads((ROOT / "data" / "importance_weights.json").read_text())
CAPACITY = {k: (v["capacity"] if isinstance(v, dict) else v)
            for k, v in json.loads((ROOT / "data" / "venue_capacity.json").read_text()).items()
            if not k.startswith("_") and (v["capacity"] if isinstance(v, dict) else v)}
UA = "CambridgeEventsBot/0.1 (+https://github.com/performancejesus/cambridge-events)"
BATCH = 50
FOOTBALL_SOURCES = {"S018"}
CUP_TAGS = {"FA": "fa_cup", "LC": "league_cup", "EFLT": "efl_trophy"}
CUP_RU = {"league": "чемпионат", "fa_cup": "Кубок Англии", "league_cup": "Кубок лиги", "efl_trophy": "EFL Trophy",
          "friendly": "товарищеский", "charity": "благотворительный"}
DERBY = {"peterborough united"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def future_events(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("""SELECT e.*, v.name AS venue_ref FROM events e LEFT JOIN venues v USING(venue_id)
        WHERE coalesce(e.date_end, e.date_start) >= date('now') AND e.status NOT IN ('past', 'cancelled')
        ORDER BY e.date_start""").fetchall()


# --- модель: известность ---

def rate_with_model(con: sqlite3.Connection, client, events: list[sqlite3.Row]) -> dict:
    """Оценка известности пачками по BATCH событий; уже оценённые (то же название) не отправляются повторно."""
    cached = {r["event_id"]: r["title"] for r in con.execute("SELECT event_id, title FROM fame_cache")}
    todo = [e for e in events if cached.get(e["event_id"]) != e["title"]]
    stats = {"rated": 0, "calls": 0, "cost_usd": 0.0}
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        payload = [{"id": e["event_id"], "title": e["title"], "venue": e["venue_name"], "date": e["date_start"],
                    "summary": _summary(con, e["event_id"])[:700]} for e in batch]
        with client.messages.stream(model=MODEL, max_tokens=32000, system=PROMPT,
                                    messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                                    output_config={"format": {"type": "json_schema", "schema": SCHEMA}, "effort": "low"}) as s:
            msg = s.get_final_message()
        if msg.stop_reason in ("refusal", "max_tokens"):
            raise RuntimeError(f"stop_reason={msg.stop_reason}")
        items = json.loads(next(b.text for b in msg.content if b.type == "text"))["items"]
        cost = msg.usage.input_tokens * PRICE_IN + msg.usage.output_tokens * PRICE_OUT
        con.execute("INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?,?,?,?)",
                    (now(), "importance", MODEL, None, msg.usage.input_tokens, msg.usage.output_tokens, cost))
        titles = {e["event_id"]: e["title"] for e in batch}
        for it in items:
            if it["id"] in titles:
                con.execute("INSERT OR REPLACE INTO fame_cache VALUES (?,?,?,?,?)",
                            (it["id"], titles[it["id"]], json.dumps(it, ensure_ascii=False), MODEL, now()))
                stats["rated"] += 1
        con.commit()
        stats["calls"] += 1
        stats["cost_usd"] += cost
    stats["cost_usd"] = round(stats["cost_usd"], 4)
    return stats


def _summary(con, event_id: int) -> str:
    """Описания всех источников (у склеенных дублей состав может быть только в статье)."""
    rows = con.execute("SELECT summary FROM raw_items WHERE event_id=? AND summary IS NOT NULL", (event_id,)).fetchall()
    uniq = []
    for s in sorted((r["summary"] for r in rows), key=len, reverse=True):
        if not any(s[:80] in u for u in uniq):
            uniq.append(s)
    return " | ".join(u[:200] for u in uniq)


# --- Wikipedia ---

WIKI_PAUSE = 1.0   # Wikimedia: вежливая частота запросов (на пачку без пауз отвечает 429)


def _wiki_get(http: httpx.Client, url: str) -> httpx.Response | None:
    """GET с паузой и одним повтором после 429; None — ответ не получен (в кэш не пишем)."""
    for attempt in range(2):
        time.sleep(WIKI_PAUSE)
        r = http.get(url)
        if r.status_code != 429:
            return r
        time.sleep(min(60, int(r.headers.get("retry-after", "30") or 30)))
    return None


def wiki(con: sqlite3.Connection, title: str, http: httpx.Client) -> sqlite3.Row | None:
    """Статья Wikipedia и просмотры за 30 дней (Wikimedia pageviews). Неоднозначные страницы — «нет статьи».
    В кэш — только определённые ответы (200 / 404): 403 и 429 не означают, что статьи нет."""
    if not title:
        return None
    row = con.execute("SELECT * FROM wiki_cache WHERE title=?", (title,)).fetchone()
    if row:
        return row
    exists, resolved, views = 0, None, None
    r = _wiki_get(http, f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe='')}")
    if r is None or r.status_code not in (200, 404):
        return None
    if r.status_code == 200 and r.json().get("type") == "standard":
        exists, resolved = 1, r.json()["titles"]["canonical"]
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=29)
        pv = _wiki_get(http, "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/"
                       f"{quote(resolved, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        if pv is None or pv.status_code not in (200, 404):
            return None
        views = sum(i["views"] for i in pv.json().get("items", [])) if pv.status_code == 200 else 0
    con.execute("INSERT OR REPLACE INTO wiki_cache VALUES (?,?,?,?,?)", (title, exists, resolved, views, now()))
    con.commit()
    return con.execute("SELECT * FROM wiki_cache WHERE title=?", (title,)).fetchone()


# --- сигналы и формула ---

def _log_scale(x: float, lo: float, hi: float) -> float:
    if x <= lo:
        return 0.0
    return min(1.0, math.log(x / lo) / math.log(hi / lo))


def _price_max(text: str | None) -> float | None:
    vals = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", (text or "").replace(",", ""))]
    return max(vals) if vals else None


def football(e: sqlite3.Row, sources: set[str]) -> dict | None:
    if not sources & FOOTBALL_SOURCES and not re.search(r"\bfootball match\b", e["title"], re.I):
        return None
    tag = re.search(r"\[(\w+)\]\s*$", e["title"])
    comp = CUP_TAGS.get(tag.group(1)) if tag else ("charity" if re.search(r"charity", e["title"], re.I) else "league")
    opponent = re.sub(r"\s*\[.*\]\s*$", "", e["title"].split(" - ", 1)[-1]).strip()
    derby = any(d in opponent.lower() for d in DERBY)
    return {"competition": comp, "opponent": opponent, "derby": derby}


def _signals(con, e) -> dict:
    sources = {r[0] for r in con.execute("SELECT source_id FROM event_sources WHERE event_id=?", (e["event_id"],))}
    has_article = con.execute("SELECT 1 FROM event_sources WHERE event_id=? AND article_id IS NOT NULL",
                              (e["event_id"],)).fetchone() is not None
    rec = con.execute("SELECT name FROM recurring_events WHERE event_id=?", (e["event_id"],)).fetchone()
    return {"sources": sources, "has_article": has_article, "recurring": rec["name"] if rec else None}


def score(con: sqlite3.Connection, e: sqlite3.Row, fame: dict | None, wiki_row) -> tuple[float, str]:
    W = WEIGHTS
    parts: list[tuple[float, str]] = []
    add = lambda pts, text: parts.append((round(pts, 1), text)) if pts >= 0.05 else None
    sig = _signals(con, e)
    sources, has_article = sig["sources"], sig["has_article"]

    cap = CAPACITY.get(e["venue_ref"] or "") or CAPACITY.get(e["venue_name"] or "")
    if cap:
        add(W["capacity"]["points"] * _log_scale(cap, W["capacity"]["min"], W["capacity"]["full_at"]),
            f"{e['venue_ref'] or e['venue_name']} ~{cap} мест")
    else:
        add(W["capacity"]["points"] * W["capacity"]["neutral"], "вместимость неизвестна — нейтрально")
    pmax = _price_max(e["price_text"])
    P = W["price_max"]
    if pmax and (e["price_from"] or 0) > 0:
        add(P["points"] * (P["neutral"] + (1 - P["neutral"]) * min(1.0, pmax / P["full_at"])), f"билеты до £{pmax:g}")
    else:
        add(P["points"] * P["neutral"], "бесплатно — нейтрально" if e["price_from"] == 0 else "цена неизвестна — нейтрально")
    n = len(sources)
    if n > 1:
        add(W["sources"]["points"] * min(1.0, (n - 1) / (W["sources"]["full_at"] - 1)), f"{n} источника" if n < 5 else f"{n} источников")
    if has_article:
        add(W["article"]["points"], "есть статья в новостях")
    if e["status"] == "sold_out":
        add(W["sold_out"]["points"], "билеты распроданы")
    if sig["recurring"]:
        add(W["recurring"]["points"], f"ежегодный флагман ({sig['recurring']})")

    fb = football(e, sources)
    floor = 0.0
    if fb:
        F = W["football"]
        add(F[fb["competition"]], f"футбол: {CUP_RU[fb['competition']]}, соперник {fb['opponent']}")
        if fb["derby"]:
            add(F["derby_bonus"], "дерби с Peterborough United")
        if fame and fame.get("opponent_top_flight"):
            floor = F["top_flight_min_score"]
            parts.append((0.0, "соперник из Премьер-лиги (оценка модели) → не ниже 8"))
    elif fame:
        # известность — того, кто на сцене (performer), а не темы: пьесы, оригинала трибьюта, знаменитости-повода
        draw = fame.get("draw_type")
        who = fame.get("performer") or (fame.get("entity") if draw == "in_person" else "")
        f = fame.get("performer_fame", fame.get("fame") if draw == "in_person" else 0) or 0
        k = 1.0
        if draw in ("tribute_or_themed", "subject_only"):
            cap_f, k = (5, 0.5) if has_article else (3, 0.0)
            f = min(f, cap_f)
            parts.append((0.0, "трибьют / шоу по мотивам / одно известное имя в составе: Wikipedia " +
                          ("вполовину (есть статья в новостях)" if k else "не учитывается") + f", модель не выше {cap_f}"))
        elif draw == "original_work" and fame.get("entity") and fame.get("entity") != who:
            parts.append((0.0, f"постановка: известность «{fame['entity']}» не считается, считается труппа"))
        free_talk = fame.get("entity_type") == "speaker" and not (e["price_from"] or 0) > 0
        mult = W["speaker_talk"]["fame_multiplier"] if free_talk and draw == "in_person" else 1.0
        if mult > 1:
            parts.append((0.0, f"лекция без билетов: известность выступающего × {mult:g}"))
        if k and wiki_row and wiki_row["exists_"] and wiki_row["views_30d"]:
            views = wiki_row["views_30d"]
            add(mult * k * W["wikipedia"]["points"] * _log_scale(views, W["wikipedia"]["min_views"], W["wikipedia"]["full_at_views"]),
                f"Wikipedia «{wiki_row['resolved'].replace('_', ' ')}»: {views:,} просмотров за 30 дней".replace(",", " "))
        if f:
            f = max(1, min(10, f))
            same = who == fame.get("entity")
            add(mult * W["model_fame"]["points"] * (f - 1) / 9,
                f"модель: {who or '—'} {f}/10" + (f" — {fame.get('fame_reason', '')}" if same
                                                  else f" (тема: {fame.get('entity')} — {fame.get('fame_reason', '')})"))
        else:
            parts.append((0.0, f"модель: {who or 'исполнитель'} неизвестен — {fame.get('fame_reason', '')}"))

    total = max(floor, min(10.0, W["base"] + sum(p for p, _ in parts)))
    reason = "; ".join(f"{t} (+{p:g})" if p else t for p, t in sorted(parts, key=lambda x: -x[0])) or "сигналов нет"
    return round(total, 1), reason


def signature(con, e, fame: dict | None) -> str:
    """Входные данные оценки: изменились — пересчитать (рабочий режим: не вся база каждый раз)."""
    sig = _signals(con, e)
    blob = json.dumps([e["title"], e["venue_id"], e["venue_name"], e["price_text"], e["price_from"], e["status"],
                       sorted(sig["sources"]), sig["has_article"], sig["recurring"], fame, WEIGHTS,
                       sorted(CAPACITY.items())], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def run(con: sqlite3.Connection, client=None, full: bool = False) -> dict:
    """Рабочий режим: модель — только для новых событий и событий с изменившимся названием (кэш fame_cache),
    формула — только там, где изменилась сигнатура входных данных. full=True — пересчитать всё."""
    events = future_events(con)
    stats = rate_with_model(con, client, events) if client else {}
    fames = {r["event_id"]: json.loads(r["result"]) for r in con.execute("SELECT * FROM fame_cache")}
    scored = 0
    # HTTP/2: по HTTP/1.1 Wikimedia отвечает 403 этому клиенту
    with httpx.Client(timeout=30, headers={"User-Agent": UA}, follow_redirects=True, http2=True) as http:
        for e in events:
            fame = fames.get(e["event_id"])
            sig = signature(con, e, fame)
            if not full and e["importance_sig"] == sig and e["importance_score"] is not None:
                continue
            title = fame and (fame.get("performer_wikipedia_title") if "performer_wikipedia_title" in fame
                              else fame.get("wikipedia_title"))
            w = wiki(con, title, http) if title else None
            s, reason = score(con, e, fame, w)
            con.execute("UPDATE events SET importance_score=?, importance_reason=?, importance_sig=? WHERE event_id=?",
                        (s, reason, sig, e["event_id"]))
            scored += 1
    con.commit()
    stats["scored"] = scored
    stats["unchanged"] = len(events) - scored
    stats["wiki_articles"] = con.execute("SELECT count(*) FROM wiki_cache WHERE exists_=1").fetchone()[0]
    return stats
