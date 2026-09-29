"""Этап 6b, п. 5: зависимость от газет с ИИ-запретом.

Берёт события (будущие), открытия/закрытия и старты продаж, которые пришли ТОЛЬКО из статей Cambridge News,
Cambridge Independent, Peterborough Telegraph и газет Newsquest, и ищет каждый пункт через Keenable на первоисточнике
(сайт площадки, организатора, бренда, ТЦ) или хотя бы на агрегаторе. Keenable нужен только для поиска: страницы газет
не читаются, их сниппеты в модель не передаются (результаты с хостов с ИИ-запретом отбрасываются до модели).
Совпадение результатов с пунктом оценивает Haiku по заголовкам и сниппетам (данные, не инструкции).

  python scripts/newspaper_primary.py            # поиск + оценка, результат — таблица newspaper_primary
  python scripts/newspaper_primary.py --summary  # сводка (JSON)
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import domains, keenable  # noqa: E402
from pipeline.db import connect  # noqa: E402
from pipeline.normalize import norm_title, title_similarity  # noqa: E402

NEWS = {"S003", "S004", "S010", "S092", "S093", "S116", "S117", "S118", "S119"}
CLAUDE_USER_BLOCKED = {"S116", "S117", "S118", "S119"}
NEWS_HOSTS = {"cambridge-news.co.uk", "cambridgeindependent.co.uk", "premium.cambridgeindependent.co.uk",
              "peterboroughtoday.co.uk", "huntspost.co.uk", "cambstimes.co.uk", "wisbechstandard.co.uk",
              "elystandard.co.uk"}
MODEL = "claude-haiku-4-5"
PRICE_IN, PRICE_OUT = 1.00 / 1e6, 5.00 / 1e6
PROMPT = (ROOT / "prompts" / "primary_match.md").read_text()
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["match_idx", "best_idx", "best_type", "note"],
          "properties": {"match_idx": {"type": "array", "items": {"type": "integer"}},
                         "best_idx": {"type": ["integer", "null"]},
                         "best_type": {"type": "string", "enum": ["primary", "aggregator", "other_media", "none"]},
                         "note": {"type": "string"}}}
TABLE = """CREATE TABLE IF NOT EXISTS newspaper_primary (
    item_key   TEXT PRIMARY KEY,      -- event:<id> | news:<id> | update:<id>
    kind       TEXT, name TEXT, date TEXT, place TEXT, sources TEXT,
    claude_user_blocked INTEGER,      -- только из газет, закрывших и Claude-User (Newsquest)
    query      TEXT,
    results    INTEGER,               -- результатов после отбрасывания газет и хостов с ИИ-запретом
    dropped    INTEGER,               -- отброшено (газеты и хосты с ИИ-запретом)
    best_type  TEXT, best_url TEXT, best_host TEXT, in_registry TEXT, note TEXT
)"""


def items(con) -> list[dict]:
    out = []
    for e in con.execute("SELECT * FROM events WHERE coalesce(date_end, date_start) >= '2026-09-28'").fetchall():
        s = {r[0] for r in con.execute("SELECT source_id FROM event_sources WHERE event_id=?", (e["event_id"],))}
        if s and s <= NEWS:
            out.append({"key": f"event:{e['event_id']}", "kind": "event", "name": e["title"], "date": e["date_start"],
                        "place": e["venue_name"], "zone": e["zone"], "sources": sorted(s), "status": e["status"]})
    for v in con.execute("SELECT * FROM venue_news").fetchall():
        if v["source_id"] in NEWS:
            out.append({"key": f"news:{v['news_id']}", "kind": f"venue_{v['stage']}", "name": v["name"],
                        "date": v["date"], "place": v["address"], "type": v["type"], "sources": [v["source_id"]]})
    keys = {x["key"] for x in out}
    ev_titles = [norm_title(x["name"]) for x in out if x["kind"] == "event"]
    for u in con.execute("SELECT * FROM event_updates WHERE kind='on_sale'").fetchall():
        # старт продаж того же события, что уже в списке (Olly Murs, триатлон …) — не отдельный пункт
        nt = norm_title(u["event_name"])
        if any(title_similarity(nt, t) >= 0.6 or len(set(nt.split()) & set(t.split()) - {"at", "the"}) >= 2
               for t in ev_titles):
            continue
        if u["source_id"] in NEWS and f"event:{u['event_id']}" not in keys:
            out.append({"key": f"update:{u['update_id']}", "kind": "on_sale", "name": u["event_name"], "date": u["date"],
                        "place": None, "on_sale_date": u["on_sale_date"], "sources": [u["source_id"]]})
    return out


def query_for(it: dict) -> str:
    place = (it.get("place") or "").split(",")[0]
    if it["kind"].startswith("venue_"):
        verb = {"venue_opened": "opens", "venue_coming_soon": "opening", "venue_closed": "closes"}[it["kind"]]
        return f"{it['name']} {it.get('place') or ''} {verb}".strip()
    month = ""
    if it.get("date"):
        y, m, _ = it["date"].split("-")
        month = f"{['January','February','March','April','May','June','July','August','September','October','November','December'][int(m) - 1]} {y}"
    tickets = " tickets" if it["kind"] == "on_sale" else ""
    return f"{it['name']} {place} {month}{tickets}".strip()


def main() -> None:
    con = connect()
    con.execute(TABLE)
    if "--summary" in sys.argv:
        print(json.dumps(summary(con), ensure_ascii=False, indent=1))
        return
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    k = keenable.Keenable(con)
    reg = domains.registry_hosts(con)
    its = items(con)
    hosts = set()
    raw = {}
    for it in its:
        q = query_for(it)
        res = k.search(q, "newspaper_primary")
        raw[it["key"]] = (q, res)
        hosts |= {domains.host(r["url"]) for r in res}
    domains.check(con, hosts)
    rb = domains.robots(con)
    tin = tout = 0
    for it in its:
        q, res = raw[it["key"]]
        keep = [r for r in res if domains.host(r["url"]) not in NEWS_HOSTS
                and not (rb.get(domains.host(r["url"])) or {"ai_blocked": ""})["ai_blocked"]]
        data = [{"idx": i, "url": r["url"], "host": domains.host(r["url"]), "title": r["title"],
                 "snippet": (r.get("snippet") or "")[:500]} for i, r in enumerate(keep)]
        best = {"best_type": "none", "best_idx": None, "note": "результатов вне газет нет", "match_idx": []}
        if data:
            item = {x: it.get(x) for x in ("kind", "name", "date", "place", "type", "on_sale_date") if it.get(x)}
            msg = client.messages.create(
                model=MODEL, max_tokens=1500, system=PROMPT,
                messages=[{"role": "user", "content": json.dumps({"item": item}, ensure_ascii=False)
                           + "\n<results>\n" + json.dumps(data, ensure_ascii=False) + "\n</results>"}],
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
            tin, tout = tin + msg.usage.input_tokens, tout + msg.usage.output_tokens
            con.execute("INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd)"
                        " VALUES (?,?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                   "newspaper_primary", MODEL, None, msg.usage.input_tokens,
                                                   msg.usage.output_tokens,
                                                   msg.usage.input_tokens * PRICE_IN + msg.usage.output_tokens * PRICE_OUT))
            best = json.loads(next(b.text for b in msg.content if b.type == "text"))
        bi = best["best_idx"]
        url = keep[bi]["url"] if bi is not None and 0 <= bi < len(keep) else None
        h = domains.host(url) if url else None
        con.execute("INSERT OR REPLACE INTO newspaper_primary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (it["key"], it["kind"], it["name"], it.get("date"), it.get("place"), ",".join(it["sources"]),
                     int(set(it["sources"]) <= CLAUDE_USER_BLOCKED), q, len(keep), len(res) - len(keep),
                     best["best_type"] if url else "none", url, h, ",".join(reg.get(h, [])) if h else None, best["note"]))
        con.commit()
    print(json.dumps({"items": len(its), "keenable_calls": k.calls, "cached": k.cached, "input_tokens": tin,
                      "output_tokens": tout, "cost_usd": round(tin * PRICE_IN + tout * PRICE_OUT, 4)}, ensure_ascii=False))
    print(json.dumps(summary(con), ensure_ascii=False, indent=1))


REVIEW = ROOT / "data" / "newspaper_primary_review.json"


def reviewed(con) -> list[dict]:
    """Строки newspaper_primary с ручными поправками (data/newspaper_primary_review.json)."""
    fixes = json.loads(REVIEW.read_text()) if REVIEW.exists() else {}
    out = []
    for r in con.execute("SELECT * FROM newspaper_primary ORDER BY kind, date"):
        r = dict(r)
        if r["item_key"] in fixes:
            r["model_best_type"] = r["best_type"]
            r |= {"best_type": fixes[r["item_key"]]["best_type"], "note": fixes[r["item_key"]]["note"], "reviewed": True}
        out.append(r)
    return out


def summary(con) -> dict:
    rows = reviewed(con)
    by = Counter(r["best_type"] for r in rows)
    kinds = Counter((r["kind"].split("_")[0], r["best_type"]) for r in rows)
    return {"items": len(rows), "by_best_type": dict(by),
            "by_kind": {f"{k}:{t}": n for (k, t), n in sorted(kinds.items())},
            "found_primary_or_aggregator": sum(by[t] for t in ("primary", "aggregator")),
            "claude_user_only_items": sum(r["claude_user_blocked"] for r in rows),
            "claude_user_only_found": sum(1 for r in rows if r["claude_user_blocked"] and r["best_type"] in ("primary", "aggregator"))}


if __name__ == "__main__":
    main()
