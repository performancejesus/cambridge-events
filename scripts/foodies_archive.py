"""Выгрузка архива Cambridge Foodies за 12 месяцев через /feed/?paged=N — не больше одной страницы в день.

Номер следующей страницы и дата последнего запуска хранятся в events.db (таблица state, ключ foodies_archive);
повторный запуск в тот же день ничего не запрашивает. На 429 страница не засчитывается — завтра та же.
Когда самая старая запись страницы старше 12 месяцев, выгрузка помечается завершённой.
  python scripts/foodies_archive.py              # одна страница: статьи в articles (извлечение — extract_articles.py)
  python scripts/foodies_archive.py --extract    # + извлечение через Claude по тексту из фида (нужен ключ)
  python scripts/foodies_archive.py --status     # только показать состояние
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
STATE_KEY = "foodies_archive"


class OneShot(PoliteClient):
    """Без повторов на 429: архив подождёт до следующего раза."""

    def get(self, url):
        if not self.allowed(url):
            raise FetchError(f"robots.txt: {url}")
        r = self._raw_get(url)
        if r.status != 200:
            raise FetchError(f"HTTP {r.status} {url}")
        return r


def load_state(con) -> dict:
    row = con.execute("SELECT value FROM state WHERE key=?", (STATE_KEY,)).fetchone()
    return json.loads(row[0]) if row else {"next_page": 2, "last_run": None, "done": False}


def save_state(con, st: dict) -> None:
    con.execute("INSERT OR REPLACE INTO state(key, value) VALUES (?,?)", (STATE_KEY, json.dumps(st)))
    con.commit()


def one_page(con, http, client, page: int, cutoff: str, max_cost: float, seen_at: str, stats: dict, st: dict) -> str:
    """Одна страница архива → articles (и извлечение, если есть client). Обновляет stats и st, возвращает итог."""
    try:
        fp = feedparser.parse(http.get(FEED.format(page)).content)
    except FetchError as e:
        return f"стр. {page}: {e} — повтор завтра"
    if not fp.entries:
        st["done"] = True
        return f"стр. {page}: записей нет — архив закончился"
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
        if client and stats["cost_usd"] < max_cost:
            art = con.execute("SELECT * FROM articles WHERE url=?", (e.link,)).fetchone()
            if art["extract_status"] == "pending":
                html = (e.get("content") or [{}])[0].get("value") or e.get("summary", "")
                r = extract.process(con, http, client, art, text=extract.strip_html(html)[:extract.MAX_CHARS])
                stats["cost_usd"] += r["cost"]
                stats["extracted"] += 1
    con.commit()
    st["next_page"] = page + 1
    result = f"стр. {page}: {len(fp.entries)} записей, самая старая {oldest}"
    if oldest and oldest[:10] < cutoff:
        st["done"] = True
        result += f" — дошли до {cutoff}, архив выгружен"
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--start-page", type=int, help="переопределить номер следующей страницы")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--max-cost", type=float, default=2.0)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    cutoff = (date.today() - timedelta(days=30 * args.months)).isoformat()
    con = connect()
    st = load_state(con)
    if args.start_page:
        st["next_page"] = args.start_page
    if args.status or st["done"] or st["last_run"] == date.today().isoformat():
        why = "готово" if st["done"] else ("сегодня уже запускали — следующая страница завтра" if not args.status else "состояние")
        print(json.dumps(st | {"note": why}, ensure_ascii=False))
        return
    http = OneShot(delay=20.0)
    client = None
    if args.extract:
        from extract_articles import load_dotenv
        load_dotenv()
        if not os.environ.get("EVENTS_ANTHROPIC_KEY"):
            sys.exit("Для --extract нужен EVENTS_ANTHROPIC_KEY в окружении.")
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = {"page": st["next_page"], "posts": 0, "new": 0, "extracted": 0, "cost_usd": 0.0, "result": None}
    page = st["next_page"]
    st["last_run"] = date.today().isoformat()  # попытка засчитывается и при 429: не чаще раза в день
    stats["result"] = one_page(con, http, client, page, cutoff, args.max_cost, seen_at, stats, st)
    save_state(con, st)
    stats["cost_usd"] = round(stats["cost_usd"], 4)
    stats["state"] = st
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
