"""Этап 7b, раздел брифа «В кино» — где идёт, оценка и описание (без ключа TMDB).

Где идёт — только подтверждённое:
  - Light Cinema Cambridge (S157): расписание на ~2 недели — открытый JSON мини-гида
    cambridge.thelight.co.uk/resource/services/miniguide/data.ashx (без токена и входа; robots.txt разрешает всё;
    параметр d — метка кэша). Фильмы и event cinema (NT Live, концерты, мюзиклы) с датами сеансов;
  - Arts Picturehouse (S045): «Now Playing» и спецпоказы со страницы кинотеатра (коллектор этапа 6c);
  - Vue — закрыт, не обходим; для крупных релизов без подтверждения кинотеатра — «в широком прокате» (фильм есть в
    календаре крупных релизов mediamole.co.uk, куда попадают только широкие релизы).
Оценка важности фильма (0–10, своя шкала, не смешивается с событиями):
  - популярность: просмотры статьи Wikipedia за 30 дней (Wikimedia pageviews; 1 тыс. → 0, 300 тыс. → 5 баллов);
  - широкий прокат (+2) / идёт в двух кинотеатрах (+1) / ограниченный (0);
  - местный повод (+2): показ с Q&A, фестиваль, премьера, event cinema (трансляция спектакля или концерта);
  - повторный прокат (юбилей, реставрация): −1 (если это не местный повод).
  Отзывы критиков — только из открытых API: без ключа TMDB таких нет (Rotten Tomatoes, Metacritic не парсим).
Описание: краткое содержание статьи Wikipedia (REST page/summary: жанр, режиссёр, актёры) — факт для модели;
пересказ, а не копия. Нет статьи — модель пишет из своих знаний, пометка в «Факты из знаний модели (проверить)».
"""

from __future__ import annotations

import html as htmllib
import json
import math
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

LIGHT = "https://cambridge.thelight.co.uk"
LIGHT_DATA = LIGHT + "/resource/services/miniguide/data.ashx?d={stamp}"
LIGHT_VENUE = ("The Light Cinema Cambridge", "Cambridge Leisure Park, Clifton Way, Cambridge", "CB1 7DY")
SCHEMA = """
CREATE TABLE IF NOT EXISTS cinema_showings (
    cinema TEXT, norm TEXT, title TEXT, kind TEXT,     -- film | event_cinema | special
    first_date TEXT, last_date TEXT, days INTEGER, first_time TEXT, cert TEXT, runtime TEXT, url TEXT, checked_at TEXT,
    PRIMARY KEY (cinema, norm)
);
CREATE TABLE IF NOT EXISTS film_info (
    norm TEXT PRIMARY KEY, title TEXT, wiki_title TEXT, description TEXT, extract TEXT, views_30d INTEGER,
    fetched_at TEXT
);
"""
EVENT_TYPES = {3: "event_cinema", 4: "event_cinema"}     # ProgrammeTypes мини-гида: 3 Event Cinema, 4 Live on Stage
SPECIAL_RE = re.compile(r"\b(q ?& ?a|premiere|preview|festival|live|introduced by|in person|director'?s? talk)\b", re.I)
RERELEASE_RE = re.compile(r"\((?:[^)]*\b(?:restoration|anniversary|re-?release|4k|remaster\w*)\b[^)]*)\)", re.I)
VERSION_RE = re.compile(r"\s*\((?:dubbed|subbed|subtitled|imax|3d|2d|[a-z]+ (?:language|version)|mandarin|telugu|tamil|"
                        r"malayalam|hindi|punjabi|korean|japanese|cantonese)\)", re.I)
WIKI_PAUSE = 1.0


def init(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def norm(t: str) -> str:
    t = htmllib.unescape(t)
    t = VERSION_RE.sub("", RERELEASE_RE.sub("", t)).lower().replace("’", "'")
    t = re.sub(r"\s*\+\s*(recorded )?q ?& ?a.*$", "", t)
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"^(disney'?s|the) ", "", t)).strip()


# --- Light ---

def light_schedule(http, base: str = LIGHT) -> list[dict]:
    """Расписание Light (по умолчанию Cambridge; этап 7d — и Light Wisbech): [{title, kind, dates, cert, runtime, url}]."""
    stamp = datetime.now().strftime("%Y%m%d%H00")
    s = http.get(base.rstrip("/") + f"/resource/services/miniguide/data.ashx?d={stamp}").text
    data = json.loads(s[s.index("{"):s.rstrip().rstrip(";").rindex("}") + 1])
    out = []
    for f in data.get("Schedule", []):
        dates = []
        for dd in f.get("Dates") or []:
            k = dd["Key"]
            times = sorted(x.get("Sort") or "" for x in dd.get("Sessions") or [])
            t = times[0] if times and re.fullmatch(r"\d{4}", times[0]) else None
            dates.append((f"{k[:4]}-{k[4:6]}-{k[6:]}", f"{t[:2]}:{t[2:]}" if t else None))
        title = htmllib.unescape(f.get("Title") or "").strip()
        kind = EVENT_TYPES.get(f.get("ProgrammeType"), "special" if SPECIAL_RE.search(title) else "film")
        out.append({"title": title, "kind": kind, "dates": dates, "cert": f.get("Cert"), "runtime": f.get("Runtime"),
                    "url": base.rstrip("/") + (f.get("Url") or "")})
    return out


def refresh(con: sqlite3.Connection, http) -> dict:
    """Кинотеатры → cinema_showings: Light (мини-гид), Arts Picturehouse (записи S045 последнего прогона)."""
    init(con)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = {"light": 0, "picturehouse": 0}
    try:
        light = light_schedule(http)
    except Exception as e:  # noqa: BLE001 — мини-гид недоступен: остаются данные прошлой проверки
        stats["light_error"] = f"{type(e).__name__}: {str(e)[:80]}"
        light = []
    if light:
        con.execute("DELETE FROM cinema_showings WHERE cinema='Light'")
    for f in light:
        if not f["dates"]:
            continue
        con.execute("INSERT OR REPLACE INTO cinema_showings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("Light", norm(f["title"]), f["title"], f["kind"], f["dates"][0][0], f["dates"][-1][0],
                     len(f["dates"]), f["dates"][0][1], f["cert"], f["runtime"], f["url"], now))
        stats["light"] += 1
    rows = con.execute("""SELECT title, start, "end", url, categories, last_seen_at FROM raw_items WHERE source_id='S045'
        AND last_seen_at = (SELECT max(last_seen_at) FROM raw_items WHERE source_id='S045')""").fetchall()
    if rows:
        con.execute("DELETE FROM cinema_showings WHERE cinema='Arts Picturehouse'")
    for r in rows:
        cats = json.loads(r["categories"] or "[]")
        kind = "film" if "now playing" in cats else "special"
        start = (r["start"] or "")[:10]
        con.execute("INSERT OR REPLACE INTO cinema_showings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("Arts Picturehouse", norm(r["title"]), r["title"], kind, start, (r["end"] or r["start"] or "")[:10],
                     None, (r["start"] or "")[11:16] or None, None, None, r["url"], r["last_seen_at"]))
        stats["picturehouse"] += 1
    con.commit()
    return stats


def where(con: sqlite3.Connection, title: str, start: date, end: date) -> list[str]:
    """Кинотеатры, где фильм идёт в окне выпуска (подтверждено расписанием или «Now Playing»)."""
    init(con)
    n = norm(title)
    rows = con.execute("SELECT cinema FROM cinema_showings WHERE norm=? AND first_date <= ? AND last_date >= ?",
                       (n, end.isoformat(), start.isoformat())).fetchall()
    return sorted({r[0] for r in rows}, key=lambda c: c != "Arts Picturehouse")


# --- Wikipedia ---

def _get(client, url: str):
    for _ in range(2):
        time.sleep(WIKI_PAUSE)
        r = client.get(url)
        if r.status_code != 429:
            return r
        time.sleep(min(60, int(r.headers.get("retry-after", "30") or 30)))
    return None


def film_info(con: sqlite3.Connection, title: str, year: int, client) -> dict | None:
    """Статья о фильме: «<Title> (<year> film)» → «<Title> (film)» → «<Title>» (если статья — о фильме).
    Кэш film_info (и отрицательный ответ). В описание — только краткое содержание REST page/summary."""
    init(con)
    n = norm(title)
    row = con.execute("SELECT * FROM film_info WHERE norm=?", (n,)).fetchone()
    if row:
        return dict(row) if row["wiki_title"] else None
    base = re.sub(r"\s+", " ", VERSION_RE.sub("", RERELEASE_RE.sub("", htmllib.unescape(title)))).strip()
    base = re.sub(r"\s*\+\s*(recorded )?q ?& ?a.*$", "", base, flags=re.I)
    found = None
    # повторный прокат: «(25th Anniversary)» → фильм 2001 года; реставрация без юбилея — статья не о новом фильме
    reissue = bool(RERELEASE_RE.search(htmllib.unescape(title)))
    ann = re.search(r"(\d+)(?:st|nd|rd|th)?[ -]*(?:year )?anniversary", title, re.I)
    expected = year - int(ann.group(1)) if ann else None
    if expected:
        cands = [f"{base} ({expected} film)", f"{base} (film)", base]
    elif reissue:
        cands = [f"{base} (film)", base]
    else:
        cands = [f"{base} ({year} film)", f"{base} ({year - 1} film)", f"{base} (film)", base]
    # повторный прокат («The Others», 2001) и неоднозначные названия — поиск Wikipedia: первая статья о фильме
    sr = _get(client, "https://en.wikipedia.org/w/rest.php/v1/search/page?limit=5&q=" + quote(f"{base} film"))
    if sr is not None and sr.status_code == 200:
        cands += [p["title"] for p in sr.json().get("pages", [])
                  if re.search(r"\bfilm\b", p.get("description") or "", re.I)
                  and norm(re.sub(r"\s*\(.*?\)\s*$", "", p["title"])) == norm(base)][:2]
    for cand in cands:
        r = _get(client, "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(cand.replace(" ", "_"), safe=""))
        if r is None:
            return None     # 429 дважды: не кэшируем
        if r.status_code != 200 or r.json().get("type") != "standard":
            continue
        j = r.json()
        text = f"{j.get('description') or ''} {j.get('extract') or ''}"
        if not re.search(r"\b(film|movie|documentary|animated|musical|concert)\b", text, re.I):
            continue
        years = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", j.get("description") or "")] or \
            [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", (j.get("extract") or "")[:160])][:1]
        if expected and years and expected not in years:
            continue   # «The Others (25th Anniversary)» — не тамильский фильм 2020-х
        if reissue and years and min(years) >= year - 1:
            continue   # реставрация — не новый фильм («Dracula (4K Restoration)» ≠ Dracula 2025)
        found = j
        break
    views = None
    if found:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=29)
        pv = _get(client, "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/"
                  f"user/{quote(found['titles']['canonical'], safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        views = sum(i["views"] for i in pv.json().get("items", [])) if pv is not None and pv.status_code == 200 else 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("INSERT OR REPLACE INTO film_info VALUES (?,?,?,?,?,?,?)",
                (n, title, found["titles"]["canonical"] if found else None, (found or {}).get("description"),
                 (found or {}).get("extract"), views, now))
    con.commit()
    row = con.execute("SELECT * FROM film_info WHERE norm=?", (n,)).fetchone()
    return dict(row) if row["wiki_title"] else None


# --- оценка ---

def score(views: int | None, wide: bool, n_cinemas: int, local: bool, rerelease: bool) -> tuple[float, list[str]]:
    why = []
    s = 0.0
    if views:
        s += round(min(5.0, max(0.0, 5 * math.log(views / 1000) / math.log(300)) if views > 1000 else 0.0), 1)
        why.append(f"Wikipedia {views:,} просмотров за 30 дней".replace(",", " "))
    if wide:
        s += 2
        why.append("широкий прокат")
    elif n_cinemas >= 2:
        s += 1
        why.append("идёт в двух кинотеатрах")
    if local:
        s += 2
        why.append("местный повод (Q&A, трансляция, фестиваль)")
    if rerelease and not local:
        s -= 1
        why.append("повторный прокат")
    return round(max(0.0, min(10.0, s)), 1), why


def window_films(con: sqlite3.Connection, start: date, end: date, http_client=None) -> list[dict]:
    """Фильмы окна выпуска: релизы календаря в окне + то, что впервые появилось в расписании Light / Picturehouse
    в окне (премьеры и спецпоказы без даты релиза в календаре). С кинотеатрами, описанием и оценкой."""
    from . import film_releases
    init(con)
    rel = film_releases.in_window(con, start, end)
    films: dict[str, dict] = {}
    for r in rel:
        films.setdefault(norm(r["title"]), {"title": r["title"], "uk_date": r["uk_date"], "kind": r["kind"],
                                            "wide": "mediamole.co.uk" in r["sources"], "sources": r["sources"]})
    for r in con.execute("""SELECT * FROM cinema_showings WHERE first_date BETWEEN ? AND ? AND kind IN ('film','special')""",
                         (start.isoformat(), end.isoformat())):
        n = r["norm"]
        if n in films:
            continue
        # в прокате уже до окна у другого кинотеатра — не новый фильм
        if con.execute("SELECT 1 FROM cinema_showings WHERE norm=? AND first_date < ?", (n, start.isoformat())).fetchone():
            continue
        films[n] = {"title": r["title"], "uk_date": r["first_date"], "kind": "rerelease" if RERELEASE_RE.search(r["title"])
                    else "new", "wide": False, "sources": [r["cinema"]], "special": r["kind"] == "special"}
    client = http_client
    if client is None:
        import httpx
        from collectors.http import USER_AGENT
        # как в importance.py: без http2 и редиректов Wikimedia отвечает 403 «robot policy»
        client = httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True, http2=True)
    out = []
    for n, f in films.items():
        cinemas = where(con, f["title"], start, end)
        info = film_info(con, f["title"], int(f["uk_date"][:4]), client)
        old = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", (info or {}).get("description") or "")]
        if f["kind"] == "new" and old and max(old) < int(f["uk_date"][:4]) - 1:
            f = f | {"kind": "rerelease"}   # классика на экране (Twilight, 2008) — повторный показ, не новинка
        local = bool(f.get("special") or SPECIAL_RE.search(f["title"]))
        sc, why = score((info or {}).get("views_30d"), f["wide"], len(cinemas), local, f["kind"] != "new")
        out.append(f | {"norm": n, "cinemas": cinemas, "score": sc, "score_reason": why,
                        "wiki": (info or {}).get("wiki_title"), "wiki_description": (info or {}).get("description"),
                        "wiki_extract": ((info or {}).get("extract") or "")[:700]})
    return sorted(out, key=lambda x: -x["score"])
