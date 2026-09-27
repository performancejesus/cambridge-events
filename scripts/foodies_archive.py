"""Разовая выгрузка архива Cambridge Foodies за 12 месяцев через /feed/?paged=N.

Редкие запросы (пауза 20 с), остановка на первом 429 (продолжить позже с --start-page).
  python scripts/foodies_archive.py              # только список статей в articles (без ИИ)
  python scripts/foodies_archive.py --extract    # + извлечение через Claude по тексту из фида (нужен ключ)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import FetchError, PoliteClient  # noqa: E402
from collectors.parsers import clean_text  # noqa: E402
from pipeline import extract  # noqa: E402
from pipeline.db import connect  # noqa: E402

FEED = "https://cambridgefoodies.me.uk/feed/?paged={}"


class OneShot(PoliteClient):
    """Без повторов на 429: архив подождёт до следующего раза."""

    def get(self, url):
        if not self.allowed(url):
            raise FetchError(f"robots.txt: {url}")
        r = self._raw_get(url)
        if r.status != 200:
            raise FetchError(f"HTTP {r.status} {url}")
        return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--max-cost", type=float, default=2.0)
    args = ap.parse_args()
    cutoff = (date.today() - timedelta(days=30 * args.months)).isoformat()
    con, http = connect(), OneShot(delay=20.0)
    client = None
    if args.extract:
        from extract_articles import load_dotenv
        load_dotenv()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("Для --extract нужен ANTHROPIC_API_KEY в окружении.")
        import anthropic
        client = anthropic.Anthropic()
    seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = {"pages": 0, "posts": 0, "new": 0, "extracted": 0, "cost_usd": 0.0, "stopped": None}
    page = args.start_page
    while True:
        try:
            fp = feedparser.parse(http.get(FEED.format(page)).content)
        except FetchError as e:
            stats["stopped"] = f"стр. {page}: {e}"
            break
        if not fp.entries:
            stats["stopped"] = f"стр. {page}: записей нет"
            break
        stats["pages"] += 1
        oldest = None
        for e in fp.entries:
            pub = e.get("published_parsed")
            published = datetime(*pub[:6]).isoformat() + "Z" if pub else None
            oldest = min(filter(None, [oldest, published])) if published else oldest
            if published and published[:10] < cutoff:
                continue
            stats["posts"] += 1
            cur = con.execute("""INSERT OR IGNORE INTO articles(source_id, url, title, published, summary, first_seen_at)
                VALUES ('S087',?,?,?,?,?)""", (e.link, clean_text(e.title, 200), published, clean_text(e.get("summary")), seen_at))
            stats["new"] += cur.rowcount
            if client and stats["cost_usd"] < args.max_cost:
                art = con.execute("SELECT * FROM articles WHERE url=?", (e.link,)).fetchone()
                if art["extract_status"] == "pending":
                    html = (e.get("content") or [{}])[0].get("value") or e.get("summary", "")
                    r = extract.process(con, http, client, art, text=extract.strip_html(html)[:extract.MAX_CHARS])
                    stats["cost_usd"] += r["cost"]
                    stats["extracted"] += 1
        con.commit()
        print(f"стр. {page}: {len(fp.entries)} записей, самая старая {oldest}", file=sys.stderr)
        if oldest and oldest[:10] < cutoff:
            stats["stopped"] = f"стр. {page}: дошли до {cutoff}"
            break
        page += 1
    stats["cost_usd"] = round(stats["cost_usd"], 4)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
