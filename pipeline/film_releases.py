"""Этап 6d (решения после 6c): кино — через календарь релизов Великобритании, а не через кинотеатры.

Источник S167 — открытые календари релизов (robots.txt разрешает; календарь FDA launchingfilms.com закрыт бот-защитой,
findanyfilm.com — заглушка, TMDB требует ключ):
  - thepeoplesmovies.com/uk-release-dates-2026-2027 — полный список по датам («OCTOBER 2ND | Digger | Verity | …»),
    включая инди и повторные прокаты (4K-реставрации, юбилеи); стриминг помечен платформой — не берём;
  - mediamole.co.uk/upcoming-uk-film-movie-releases — крупные релизы по пятницам («Friday, October 2, 2026 | Digger |…»)
    — сверка: фильм в обоих календарях = подтверждён; расхождение даты — редактору.
Разбор без модели. Таблица film_releases: title, uk_date, kind (new / rerelease), sources, note.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timezone

PEOPLES = "https://thepeoplesmovies.com/uk-release-dates-2026-2027"
MOLE = "https://mediamole.co.uk/upcoming-uk-film-movie-releases"
SCHEMA = """CREATE TABLE IF NOT EXISTS film_releases (
    title TEXT, uk_date TEXT, kind TEXT, sources TEXT, note TEXT, checked_at TEXT,
    PRIMARY KEY (title, uk_date)
)"""
MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER",
          "DECEMBER"]
STREAMING_RE = re.compile(r"\((?:[^)]*\b(?:netflix|prime video|disney\+|apple tv|now tv|sky|mubi|bbc iplayer)\b[^)]*)\)", re.I)
RERELEASE_RE = re.compile(r"\((?:[^)]*\b(?:restoration|anniversary|re-?release|4k|director.s cut)\b[^)]*)\)", re.I)
HEAD_RE = re.compile(r"^(" + "|".join(MONTHS) + r") (\d{1,2})(?:ST|ND|RD|TH)?(?:/[\dA-Z/]+)?$")


def _text(http, url: str) -> str:
    from collectors.llmlist import visible_text
    t, _ = visible_text(http.get(url).text)
    return re.sub(r"(?:\| )+", "| ", t)


def parse_peoples(text: str, year_from: int) -> list[dict]:
    """«OCTOBER | OCTOBER 2ND | Digger | Verity | … | OCTOBER 8TH | …» → [{title, uk_date, kind}]. Год растёт при
    переходе через декабрь; заголовки месяцев («OCTOBER», «JANUARY 2027») пропускаются."""
    out, cur, year, last_month = [], None, year_from, 0
    start = text.find("| JANUARY |") if "| JANUARY |" in text else 0
    for part in (p.strip() for p in text[start:].split("|")):
        if not part:
            continue
        up = part.upper()
        m = HEAD_RE.match(up)
        if m:
            month = MONTHS.index(m.group(1)) + 1
            if month < last_month:
                year += 1
            last_month = month
            cur = date(year, month, int(m.group(2)))
            continue
        if re.fullmatch(r"(" + "|".join(MONTHS) + r")(?: \d{4})?", up) or up in ("DECEM", "BER"):
            continue
        if cur is None or len(part) > 90 or part.lower().startswith(("release dates", "let us know", "*")):
            continue
        if STREAMING_RE.search(part):
            continue
        d = cur
        m2 = re.search(r"\((\d{1,2})/(\d{1,2})\)", part)   # «Focker-in-Law (25/11)» — своя дата внутри группы
        if m2:
            d = date(cur.year, int(m2.group(2)), int(m2.group(1)))
            part = part[:m2.start()].strip()
        kind = "rerelease" if RERELEASE_RE.search(part) else "new"
        out.append({"title": part, "uk_date": d.isoformat(), "kind": kind})
    return out


def parse_mole(text: str) -> list[dict]:
    out, cur = [], None
    for part in (p.strip() for p in text.split("|")):
        m = re.fullmatch(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), (\w+) (\d{1,2}), (\d{4})", part)
        if m:
            cur = datetime.strptime(f"{m.group(2)} {m.group(1)} {m.group(3)}", "%d %B %Y").date()
            continue
        if cur and part and len(part) <= 90 and not part.lower().startswith(("check back", "our guide", "advert")):
            out.append({"title": part, "uk_date": cur.isoformat()})
    return out


def _norm(t: str) -> str:
    t = RERELEASE_RE.sub("", t).lower().replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"^(disney's|the) ", "", t)).strip()


def refresh(con: sqlite3.Connection, http, today: date | None = None) -> dict:
    today = today or date.today()
    con.execute(SCHEMA)
    peoples = parse_peoples(_text(http, PEOPLES), today.year)
    try:
        mole = parse_mole(_text(http, MOLE))
    except Exception:  # noqa: BLE001 — сверочный календарь недоступен: берём основной без сверки
        mole = []
    mole_by = {}
    for x in mole:
        mole_by.setdefault(_norm(x["title"]), x["uk_date"])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    con.execute("DELETE FROM film_releases WHERE uk_date >= ?", (today.isoformat(),))
    n = 0
    for x in peoples:
        if x["uk_date"] < today.isoformat():
            continue
        srcs, note = ["thepeoplesmovies.com"], ""
        md = mole_by.get(_norm(x["title"]))
        if md:
            srcs.append("mediamole.co.uk")
            if md != x["uk_date"]:
                note = f"mediamole.co.uk: {md}"
        con.execute("INSERT OR REPLACE INTO film_releases VALUES (?,?,?,?,?,?)",
                    (x["title"], x["uk_date"], x["kind"], json.dumps(srcs), note, now))
        n += 1
    con.commit()
    return {"releases": n, "confirmed_by_second": sum(1 for x in peoples if _norm(x["title"]) in mole_by),
            "mole": len(mole)}


def in_window(con: sqlite3.Connection, start: date, end: date) -> list[dict]:
    con.execute(SCHEMA)
    rows = con.execute("SELECT * FROM film_releases WHERE uk_date BETWEEN ? AND ? ORDER BY uk_date, kind, rowid",
                       (start.isoformat(), end.isoformat())).fetchall()
    return [dict(r) | {"sources": json.loads(r["sources"])} for r in rows]
