"""Этап 3: извлечение из новых статей через Claude API (Haiku). Ключ — EVENTS_ANTHROPIC_KEY в окружении.

Запуск: python scripts/extract_articles.py --dry-run        # оценка стоимости, без API
        python scripts/extract_articles.py --max-cost 2.00  # обработка с потолком расходов, $
        python scripts/extract_articles.py --rerun-venue-news --max-cost 0.50
            # повторно: статьи, чьи записи venue_news без номера дома/postcode или без даты
            # (их venue_news и event_updates заменяются новым результатом); --articles 30,44 — только эти статьи
После обработки: python scripts/update_db.py --no-load  (события из статей проходят общую дедупликацию)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import PoliteClient  # noqa: E402
from pipeline import extract  # noqa: E402
from pipeline.db import connect  # noqa: E402


def load_dotenv() -> None:
    """KEY=VALUE из .env (файл в .gitignore); переменные окружения важнее."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def rerun_articles(con) -> list:
    """Статьи из LLM-источников, у чьих записей venue_news нет полного адреса (номер дома или postcode) или даты."""
    rows = con.execute("""SELECT article_id, address, postcode, date FROM venue_news
        WHERE source_type='article' AND article_id IS NOT NULL""").fetchall()
    ids = sorted({r["article_id"] for r in rows
                  if not r["date"] or not (r["postcode"] or re.search(r"\d", r["address"] or ""))})
    return [con.execute("SELECT * FROM articles WHERE article_id=?", (i,)).fetchone() for i in ids]


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-cost", type=float, default=2.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--rerun-venue-news", action="store_true")
    ap.add_argument("--articles", help="с --rerun-venue-news: только эти article_id через запятую")
    args = ap.parse_args()
    con = connect()
    if args.dry_run or not os.environ.get("EVENTS_ANTHROPIC_KEY"):
        if not args.dry_run:
            print("EVENTS_ANTHROPIC_KEY не задан — только оценка стоимости.", file=sys.stderr)
        print(json.dumps(extract.estimate(con, len(extract.pending(con, args.limit))), ensure_ascii=False, indent=1))
        return
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    http = PoliteClient()
    spent, totals = 0.0, {"articles": 0, "events": 0, "venue_news": 0, "updates": 0, "errors": 0}
    if args.rerun_venue_news and args.articles:
        todo = [con.execute("SELECT * FROM articles WHERE article_id=?", (int(i),)).fetchone() for i in args.articles.split(",")]
    elif args.rerun_venue_news:
        todo = rerun_articles(con)[:args.limit]
    else:
        todo = extract.pending(con, args.limit)
    for art in todo:
        if spent >= args.max_cost:
            print(f"Потолок ${args.max_cost} достигнут, остановка.", file=sys.stderr)
            break
        if args.rerun_venue_news:
            con.execute("DELETE FROM venue_news WHERE article_id=? AND source_type='article'", (art["article_id"],))
            con.execute("DELETE FROM event_updates WHERE article_id=?", (art["article_id"],))
        try:
            r = extract.process(con, http, client, art)
        except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as e:
            if args.rerun_venue_news:  # старые записи остаются как были
                con.rollback()
                totals["errors"] += 1
                continue
            con.execute("UPDATE articles SET extract_status='error', result_json=? WHERE article_id=?",
                        (json.dumps({"error": str(e)[:300]}), art["article_id"]))
            totals["errors"] += 1
            continue
        finally:
            con.commit()
        spent += r.pop("cost")
        totals["articles"] += 1
        for k, v in r.items():
            totals[k] += v
    http.close()
    print(json.dumps(totals | {"cost_usd": round(spent, 4)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
