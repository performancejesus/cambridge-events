"""Этап 6b: аудит пропусков по результатам поиска Keenable.

  python scripts/gap_audit.py extract     # результаты поиска → классификация и пункты (Haiku; сниппеты сайтов
                                          #   с ИИ-запретом в модель не передаются — только заголовок и ссылка)
  python scripts/gap_audit.py match       # пункты → сравнение с базой: что есть, чего нет (search_items.status)
  python scripts/gap_audit.py summary     # сводка пропусков по категориям и доменам (JSON в stdout)

Результаты поиска — кандидаты на проверку, не факты. Сниппеты — недоверенные данные.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import domains, geo  # noqa: E402
from pipeline.db import connect  # noqa: E402
from pipeline.normalize import norm_title, norm_venue, title_similarity  # noqa: E402

MODEL = "claude-haiku-4-5"
PRICE_IN, PRICE_OUT = 1.00 / 1e6, 5.00 / 1e6
TODAY = "2026-09-28"
PROMPT = (ROOT / "prompts" / "search_extract.md").read_text().replace("{today}", TODAY)
SCHEMA = json.loads((ROOT / "prompts" / "search_extract.schema.json").read_text())
BATCH = 12
QUERIES = json.loads((ROOT / "data" / "keenable_queries.json").read_text())

TABLES = """
CREATE TABLE IF NOT EXISTS search_results (
    url        TEXT PRIMARY KEY,
    host       TEXT,
    purposes   TEXT,              -- JSON: gap_audit / kids_providers / newspaper_primary
    queries    TEXT,              -- JSON: запросы, которые нашли страницу
    groups_    TEXT,              -- JSON: группы запросов (categories, towns, openings, …)
    title      TEXT,
    published_at TEXT,
    ai_blocked TEXT,              -- агенты Anthropic, закрытые robots.txt сайта (сниппет в модель не передавался)
    area       TEXT, page_type TEXT, provider TEXT,
    extracted  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS search_items (
    item_id    INTEGER PRIMARY KEY,
    url        TEXT REFERENCES search_results(url),
    kind       TEXT, name TEXT, date_start TEXT, date_end TEXT, time TEXT, venue TEXT, town TEXT, price TEXT,
    category   TEXT, provider TEXT, ages TEXT, holidays TEXT,
    zone       TEXT,              -- по городу (postcodes.io /places) или площадке из справочника
    status     TEXT,              -- in_db | gap | past | out_of_zone | no_date | unclear
    match_id   INTEGER,           -- events.event_id / venue_news.news_id
    match_note TEXT
);
"""


def group_of(query: str) -> str:
    return next((g for g, qs in QUERIES.items() if isinstance(qs, list) and query in qs), "other")


def collect(con) -> int:
    """Уникальные страницы из кэша Keenable → search_results (с запросами и группами)."""
    con.executescript(TABLES)
    rb = domains.robots(con)
    pages: dict[str, dict] = {}
    for q, purpose, resp in con.execute("SELECT query, purpose, response FROM keenable_cache WHERE status=200"):
        for r in json.loads(resp).get("results", []):
            p = pages.setdefault(r["url"], {"r": r, "purposes": set(), "queries": set()})
            p["purposes"].add(purpose)
            p["queries"].add(q)
    for url, p in pages.items():
        h = domains.host(url)
        row = con.execute("SELECT purposes, queries FROM search_results WHERE url=?", (url,)).fetchone()
        purposes = set(json.loads(row[0])) | p["purposes"] if row else p["purposes"]
        queries = set(json.loads(row[1])) | p["queries"] if row else p["queries"]
        if row:
            con.execute("UPDATE search_results SET purposes=?, queries=?, groups_=? WHERE url=?",
                        (json.dumps(sorted(purposes)), json.dumps(sorted(queries)),
                         json.dumps(sorted({group_of(q) for q in queries})), url))
        else:
            con.execute("""INSERT INTO search_results(url, host, purposes, queries, groups_, title, published_at, ai_blocked)
                VALUES (?,?,?,?,?,?,?,?)""", (url, h, json.dumps(sorted(purposes)), json.dumps(sorted(queries)),
                                              json.dumps(sorted({group_of(q) for q in queries})), p["r"]["title"],
                                              p["r"].get("published_at"), (rb.get(h) or {"ai_blocked": ""})["ai_blocked"]))
    con.commit()
    return len(pages)


def snippets(con) -> dict[str, str]:
    """Сниппет страницы — из кэша Keenable (самый длинный из всех запросов)."""
    out: dict[str, str] = {}
    for (resp,) in con.execute("SELECT response FROM keenable_cache WHERE status=200"):
        for r in json.loads(resp).get("results", []):
            s = r.get("snippet") or ""
            if len(s) > len(out.get(r["url"], "")):
                out[r["url"]] = s
    return out


def extract(con, purposes: set[str] | None = None) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["EVENTS_ANTHROPIC_KEY"])
    collect(con)
    snip = snippets(con)
    rows = [r for r in con.execute("SELECT * FROM search_results WHERE extracted=0").fetchall()
            if not purposes or set(json.loads(r["purposes"])) & purposes]
    # ИИ-запрет в robots.txt: текст сайта в модель не передаём — страница учитывается только по заголовку и ссылке
    blocked = [r for r in rows if r["ai_blocked"]]
    for r in blocked:
        con.execute("UPDATE search_results SET extracted=2, page_type='not_sent' WHERE url=?", (r["url"],))
    rows = [r for r in rows if not r["ai_blocked"]]
    batches = [rows[i:i + BATCH] for i in range(0, len(rows), BATCH)]

    def run(batch):
        data = [{"idx": i, "url": r["url"], "title": r["title"], "published_at": r["published_at"],
                 "snippet": snip.get(r["url"], "")[:700]} for i, r in enumerate(batch)]
        msg = client.messages.create(
            model=MODEL, max_tokens=8000, system=PROMPT,
            messages=[{"role": "user", "content": "<search_results>\n" + json.dumps(data, ensure_ascii=False)
                       + "\n</search_results>"}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
        body = next((b.text for b in msg.content if b.type == "text"), "{}") if msg.stop_reason == "end_turn" else "{}"
        return batch, json.loads(body), msg.usage.input_tokens, msg.usage.output_tokens, msg.stop_reason

    tin = tout = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ThreadPoolExecutor(4) as ex:
        for batch, res, i, o, stop in ex.map(run, batches):
            tin, tout = tin + i, tout + o
            con.execute("INSERT INTO llm_usage(called_at, purpose, model, article_id, input_tokens, output_tokens, cost_usd)"
                        " VALUES (?,?,?,?,?,?,?)", (now, "search_extract" + ("" if stop == "end_turn" else f" ({stop})"),
                                                   MODEL, None, i, o, i * PRICE_IN + o * PRICE_OUT))
            for x in res.get("results", []):
                if not 0 <= x["idx"] < len(batch):
                    continue
                url = batch[x["idx"]]["url"]
                con.execute("UPDATE search_results SET area=?, page_type=?, provider=?, extracted=1 WHERE url=?",
                            (x["area"], x["page_type"], x["provider"], url))
                con.execute("DELETE FROM search_items WHERE url=?", (url,))
                for it in x["items"]:
                    con.execute("""INSERT INTO search_items(url, kind, name, date_start, date_end, time, venue, town,
                        price, category, provider, ages, holidays) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (url, it["kind"], it["name"], it["date_start"], it["date_end"], it["time"], it["venue"],
                                 it["town"], it["price"], it["category"], it["provider"], it["ages"],
                                 json.dumps(it["holidays"]) if it["holidays"] else None))
            con.commit()
    return {"pages": len(rows) + len(blocked), "sent_to_model": len(rows), "not_sent_ai_blocked": len(blocked),
            "calls": len(batches), "input_tokens": tin, "output_tokens": tout,
            "cost_usd": round(tin * PRICE_IN + tout * PRICE_OUT, 4)}


# --- сравнение с базой ---

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WINDOW_END = "2027-12-31"


def _zone(con, it) -> str | None:
    """Зона пункта: площадка из справочника → город (postcodes.io /places) → None."""
    if it["venue"]:
        row = con.execute("""SELECT v.zone FROM venue_aliases a JOIN venues v USING(venue_id) WHERE a.alias=?""",
                          (norm_venue(it["venue"]),)).fetchone()
        if row and row[0]:
            return row[0]
    town = (it["town"] or "").split(",")[0].strip()
    if not town and it["venue"] and "," in it["venue"]:
        town = it["venue"].split(",")[-1].strip()
    if not town:
        return None
    if town.lower() in ("cambridge", "cambridge city", "cambridge city centre"):
        return "центр"
    try:
        pl = geo.place(con, town)
    except Exception:
        return None
    if not pl:
        return None
    z = geo.zone(pl["lat"], pl["lon"], pl["county"], pl["district"])
    return "до часа" if z == geo.NEIGHBOUR_IF_IMPORTANT else z


def _words(s: str) -> set[str]:
    return {w for w in norm_title(s).split() if len(w) >= 4}


def match_event(con, it) -> tuple[int | None, str]:
    ds = it["date_start"]
    de = it["date_end"] if it["date_end"] and DATE_RE.match(it["date_end"]) else ds
    rows = con.execute("""SELECT event_id, title, norm_title, venue_name, date_start, coalesce(date_end, date_start) de
        FROM events WHERE date_start <= ? AND coalesce(date_end, date_start) >= ?""", (de, ds)).fetchall()
    nt, words = norm_title(it["name"]), _words(it["name"])
    best, best_s = None, 0.0
    for r in rows:
        s = title_similarity(nt, r["norm_title"])
        common = words & _words(r["title"])
        if nt and (nt in r["norm_title"] or r["norm_title"] in nt) and min(len(nt), len(r["norm_title"])) >= 6:
            s = max(s, 0.9)
        if len(common) >= 2 or (len(common) == 1 and len(words) == 1):
            s = max(s, 0.7)
        if s > best_s:
            best, best_s = r, s
    if best and best_s >= 0.6:
        return best["event_id"], f"{best['title']} ({best['date_start']}) sim={best_s:.2f}"
    return None, f"best: {best['title']} sim={best_s:.2f}" if best else "нет событий на эти даты"


def match_other_date(con, it) -> tuple[int | None, str]:
    """То же событие в базе, но на другую дату (даты из сниппетов листингов ненадёжны): сильное совпадение названия
    среди будущих событий в пределах ±120 дней."""
    nt, words = norm_title(it["name"]), _words(it["name"])
    if len(nt) < 6:
        return None, ""
    for r in con.execute("""SELECT event_id, title, norm_title, date_start FROM events
            WHERE date_start BETWEEN date(?, '-120 days') AND date(?, '+120 days')""", (it["date_start"], it["date_start"])):
        common = words & _words(r["title"])
        strong = title_similarity(nt, r["norm_title"]) >= 0.85 or (
            (nt in r["norm_title"] or r["norm_title"] in nt) and min(len(nt), len(r["norm_title"])) >= 10) or (
            len(common) >= 2 and len(common) >= 0.6 * len(words))
        if strong:
            return r["event_id"], f"{r['title']} ({r['date_start']}) — в базе на другую дату"
    return None, ""


def match_news(con, it) -> tuple[int | None, str]:
    nt = norm_title(it["name"])
    best, best_s = None, 0.0
    for r in con.execute("SELECT news_id, name FROM venue_news").fetchall():
        n2 = norm_title(r["name"])
        s = title_similarity(nt, n2)
        if nt and n2 and (nt in n2 or n2 in nt) and min(len(nt), len(n2)) >= 4:
            s = max(s, 0.9)
        if s > best_s:
            best, best_s = r, s
    if best and best_s >= 0.7:
        return best["news_id"], f"{best['name']} sim={best_s:.2f}"
    # магазин уже есть в списке арендаторов ТЦ (Grand Arcade, Lion Yard, Grafton) — база, не новость (этап 3)
    for r in con.execute("SELECT raw_id, title, source_id FROM raw_items WHERE kind='store'").fetchall():
        n2 = norm_title(r["title"])
        if nt and n2 and (nt == n2 or title_similarity(nt, n2) >= 0.9):
            return None, f"в списке арендаторов {r['source_id']}: {r['title']}"
    return None, ""


def match(con) -> dict:
    con.executescript(TABLES)
    st = Counter()
    for it in con.execute("""SELECT i.*, s.area FROM search_items i JOIN search_results s USING(url)""").fetchall():
        zone = _zone(con, it)
        status, mid, note = None, None, ""
        if it["area"] != "in_area":
            status = "unclear"
        elif it["kind"] == "programme":
            status = "programme"
        elif zone in (None,) and it["kind"] == "event":
            status = "unclear"
        elif zone == geo.OUT_OF_ZONE:
            status = "out_of_zone"
        elif it["kind"] in ("event", "cancellation"):
            if not it["date_start"] or not DATE_RE.match(it["date_start"]):
                status = "no_date"
            elif it["date_start"] < TODAY and (it["date_end"] or it["date_start"]) < TODAY:
                status = "past"
            else:
                mid, note = match_event(con, it)
                status = "in_db" if mid else "gap"
                if not mid:
                    mid, note2 = match_other_date(con, it)
                    if mid:
                        status, note = "in_db_other_date", note2
        elif it["kind"] in ("opening", "closure"):
            mid, note = match_news(con, it)
            status = "in_db" if mid else ("in_store_list" if note.startswith("в списке") else "gap")
        con.execute("UPDATE search_items SET zone=?, status=?, match_id=?, match_note=? WHERE item_id=?",
                    (zone, status, mid, note, it["item_id"]))
        st[(it["kind"], status)] += 1
    con.commit()
    return {f"{k}:{s}": n for (k, s), n in sorted(st.items())}


# --- пропуски: склейка одинаковых пунктов и проверка на странице ---

GAPS = """
CREATE TABLE IF NOT EXISTS search_gaps (
    gap_id     INTEGER PRIMARY KEY,
    kind       TEXT, name TEXT, date_start TEXT, date_end TEXT, time TEXT, venue TEXT, town TEXT, zone TEXT,
    category   TEXT, price TEXT,
    item_ids   TEXT,              -- JSON search_items
    urls       TEXT, hosts TEXT, groups_ TEXT,
    verify     TEXT,              -- verified | name_only | not_found | disallowed | fetch_error | skipped
    verify_url TEXT, verify_note TEXT
);
"""
LISTED = {"центр", "до 30 мин", "до часа", "Кембриджшир, дальше часа"}
# агрегаторы и листинги-зеркала: для проверки сначала пробуем другие страницы (первоисточник)
AGGREGATORS = {"allevents.in", "happeningnext.com", "stayhappening.com", "eventslist.co.uk", "dovetailevents.co.uk",
               "concerts50.com", "timeforgig.com", "eventworld.co", "shazam.com", "songkick.com", "bandsintown.com",
               "festscanner.com", "trip.com", "runningeventsnearme.com", "findarace.com", "timeoutdoors.com",
               "runabc.co.uk", "boxofficehero.com", "concert-diary.com", "share.google", "buff.ly", "enjoy.ly",
               "2nite.uk.net", "vibehawk.app", "wherecanwego.com", "library.live", "jorlio.com", "fatsoma.com"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def date_patterns(ds: str) -> re.Pattern:
    d = date.fromisoformat(ds)
    m, ab = MONTHS[d.month - 1], MONTHS[d.month - 1][:3]
    day = rf"0?{d.day}(?:st|nd|rd|th)?"
    return re.compile(rf"\b{day}\s+(?:of\s+)?(?:{m}|{ab}\.?)\b|\b(?:{m}|{ab}\.?)\s+{day}\b|"
                      rf"\b0?{d.day}[/.]0?{d.month}[/.](?:{d.year}|{d.year % 100})\b|{ds}", re.I)


def cluster(con) -> int:
    """Одинаковые пункты из разных страниц → один пропуск (события: название + дата; открытия: название)."""
    con.executescript(GAPS)
    con.execute("DELETE FROM search_gaps")
    rows = con.execute("""SELECT i.*, s.host, s.groups_ FROM search_items i JOIN search_results s USING(url)
        WHERE i.status='gap' ORDER BY i.date_start, i.item_id""").fetchall()
    groups: list[dict] = []
    for r in rows:
        nt = norm_title(r["name"])
        g = next((g for g in groups if g["kind"] == r["kind"] and (g["date_start"] == r["date_start"] or r["kind"] != "event")
                  and (title_similarity(nt, g["nt"]) >= 0.8 or (len(nt) >= 6 and (nt in g["nt"] or g["nt"] in nt)))), None)
        if not g:
            g = {"kind": r["kind"], "nt": nt, "rows": [], "date_start": r["date_start"]}
            groups.append(g)
        g["rows"].append(r)
    for g in groups:
        rs = g["rows"]
        best = max(rs, key=lambda r: sum(bool(r[k]) for k in ("venue", "town", "time", "price", "date_end")))
        urls = list(dict.fromkeys(r["url"] for r in rs))
        hosts = list(dict.fromkeys(r["host"] for r in rs))
        grp = sorted({x for r in rs for x in json.loads(r["groups_"])})
        con.execute("""INSERT INTO search_gaps(kind, name, date_start, date_end, time, venue, town, zone, category, price,
            item_ids, urls, hosts, groups_) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (g["kind"], best["name"], best["date_start"], best["date_end"], best["time"], best["venue"],
                     best["town"], best["zone"], best["category"], best["price"],
                     json.dumps([r["item_id"] for r in rs]), json.dumps(urls), json.dumps(hosts), json.dumps(grp)))
    con.commit()
    return len(groups)


PAGE_CACHE = ROOT / "data" / "cache" / "pages"      # тексты страниц для проверки (не в git)


def page_text(http, url: str) -> str:
    """Текст страницы (без HTML) из кэша или через вежливый клиент; исключения клиента пробрасываются."""
    import hashlib
    from pipeline.extract import strip_html
    PAGE_CACHE.mkdir(parents=True, exist_ok=True)
    f = PAGE_CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if f.exists():
        return f.read_text()
    text = strip_html(http.get(url).text).lower()
    f.write_text(text)
    return text


def page_clean(http, url: str) -> str:
    """Читаемый текст страницы без script/style/nav (для описания находки, не для проверки дат)."""
    import hashlib
    from selectolax.parser import HTMLParser
    PAGE_CACHE.mkdir(parents=True, exist_ok=True)
    f = PAGE_CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".clean.txt")
    if f.exists():
        return f.read_text()
    tree = HTMLParser(http.get(url).text)
    tree.strip_tags(["script", "style", "noscript", "svg", "nav", "header", "footer", "form"])
    text = re.sub(r"\s+", " ", (tree.body or tree.root).text(separator=" ")).strip()
    f.write_text(text)
    return text


def cached(url: str) -> bool:
    import hashlib
    return (PAGE_CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".txt")).exists()


DATE_ANY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(\d{4}))?"
                      r"|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?"
                      r"|\b(20\d\d)-(\d\d)-(\d\d)", re.I)
MON = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}


def _as_date(m: re.Match, year: int) -> date | None:
    try:
        if m.group(1):
            return date(int(m.group(3) or year), MON[m.group(2).lower()[:3]], int(m.group(1)))
        if m.group(4):
            return date(int(m.group(6) or year), MON[m.group(4).lower()[:3]], int(m.group(5)))
        return date(int(m.group(7)), int(m.group(8)), int(m.group(9)))
    except ValueError:
        return None


def near(text: str, words: list[str], target: str, before: int = 150, after: int = 250) -> bool:
    """Дата, ближайшая к названию, — нужная. У листингов на странице много дат подряд, и «дата где-то рядом» мало:
    у каждого вхождения названия берём ближайшую дату (до 150 символов до и 250 после) и сравниваем с целевой."""
    want = date.fromisoformat(target)
    key = max(words, key=len)
    for m in re.finditer(re.escape(key), text):
        lo = max(0, m.start() - before)
        best, dist = None, None
        for x in DATE_ANY.finditer(text, lo, m.end() + after):
            dd = x.start() - m.end() if x.start() >= m.end() else m.start() - x.end()
            dd = max(dd, 0) * (1 if x.start() >= m.end() else 1.5)   # дата после названия — чаще его
            if dist is None or dd < dist:
                best, dist = _as_date(x, want.year), dd
        if best == want:
            return True
    return False


def verify(con, until: str = "2026-12-31", redo: bool = False) -> dict:
    """Пропуск подтверждается, если на странице (robots.txt уважается, без модели) есть название, а для события —
    и дата рядом с названием. Проверяем события в зоне до `until` и все открытия/закрытия."""
    import collectors.http as ch
    from collectors.http import Disallowed, FetchError, PoliteClient
    ch.BACKOFF = (10,)          # проверочный проход: после 429 один короткий повтор, дальше хост пропускаем
    http = PoliteClient()
    st = Counter()
    busy: set[str] = set()      # хосты, ответившие 429/503 — в этом проходе больше не запрашиваем
    rows = con.execute("SELECT * FROM search_gaps" + ("" if redo else " WHERE verify IS NULL")).fetchall()
    for g in rows:
        if g["kind"] == "event" and (g["zone"] not in LISTED or (g["date_start"] or "9999") > until):
            con.execute("UPDATE search_gaps SET verify='skipped' WHERE gap_id=?", (g["gap_id"],))
            st["skipped"] += 1
            continue
        urls = sorted(json.loads(g["urls"]), key=lambda u: domains.host(u) in AGGREGATORS)
        words = sorted(_words(g["name"]))
        pat = date_patterns(g["date_start"]) if g["kind"] == "event" and g["date_start"] else None
        result, vurl, note = "not_found", None, ""
        for u in urls[:3]:
            if domains.host(u) in busy and not cached(u):
                result, note = ("fetch_error" if result in ("not_found", "disallowed") else result), f"{domains.host(u)}: 429, пропущен"
                continue
            try:
                text = page_text(http, u)
            except FetchError as e:
                if " 429 " in str(e) or " 503 " in str(e):
                    busy.add(domains.host(u))
                result, note = ("fetch_error" if result in ("not_found", "disallowed") else result), str(e)[:80]
                continue
            except Disallowed:
                result, note = ("disallowed" if result == "not_found" else result), f"robots.txt: {domains.host(u)}"
                continue
            except (FetchError, Exception) as e:  # noqa: BLE001 — сеть, TLS, 403 от защиты
                result, note = ("fetch_error" if result in ("not_found", "disallowed") else result), str(e)[:80]
                continue
            found = [w for w in words if w in text]
            name_ok = bool(words) and len(found) >= max(1, round(0.6 * len(words)))
            if not name_ok:
                result, note = ("not_found" if result in ("not_found", "disallowed", "fetch_error") else result), \
                    f"{domains.host(u)}: названия нет на странице"
                continue
            if pat is None or near(text, found, g["date_start"]):
                result, vurl, note = "verified", u, domains.host(u)
                break
            result, vurl, note = "name_only", u, f"{domains.host(u)}: название есть, даты {g['date_start']} рядом нет"
        con.execute("UPDATE search_gaps SET verify=?, verify_url=?, verify_note=? WHERE gap_id=?",
                    (result, vurl, note, g["gap_id"]))
        con.commit()
        st[result] += 1
    http.close()
    return dict(st)


def main() -> None:
    con = connect()
    con.executescript(TABLES)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if cmd == "extract":
        purposes = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
        print(json.dumps(extract(con, purposes), ensure_ascii=False, indent=1))
    elif cmd == "match":
        print(json.dumps(match(con), ensure_ascii=False, indent=1))
        print(json.dumps({"gap_clusters": cluster(con)}, ensure_ascii=False))
    elif cmd == "verify":
        print(json.dumps(verify(con, redo="--redo" in sys.argv), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
