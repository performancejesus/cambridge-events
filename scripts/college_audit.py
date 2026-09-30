"""Этап 7b: аудит публичных событий всех 31 колледжа Кембриджского университета.

  python scripts/college_audit.py            # → data/college_audit_7b.json (с Keenable — где страница не найдена)
  python scripts/college_audit.py --no-search

Для каждого колледжа: robots.txt; главная страница → ссылки на события («events», «what's on», «lectures», «concerts»,
«exhibitions», «gardens»); до 4 страниц-кандидатов: код ответа, объём текста, дат на странице, фиды (RSS, iCal, JSON-LD
Event), какие типы событий упомянуты (лекции, концерты, выставки, сады, дни открытых дверей, службы, выпускники).
События в базе: название колледжа (и его площадок: Wren, Parker, Pepys, Heong, Kettle's Yard не в счёт) в площадке,
адресе, названии или адресе ссылки — за последние и следующие 60 дней, с источниками.
Решение по колледжу принимается по этим данным вручную (data/college_decisions_7b.json).
"""
import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.http import Disallowed, FetchError, PoliteClient  # noqa: E402
from collectors.llmlist import visible_text  # noqa: E402
from pipeline.db import connect  # noqa: E402

# колледж, сайт, шаблон для поиска в базе (площадка / адрес / название / ссылка), дополнительные страницы-кандидаты
COLLEGES = [
    ("Christ's", "https://www.christs.cam.ac.uk/", r"christ'?s college|christs\.cam", []),
    ("Churchill", "https://www.chu.cam.ac.uk/", r"churchill college|churchill archives|chu\.cam", []),
    ("Clare", "https://www.clare.cam.ac.uk/", r"clare college|clare cellars|clare chapel|clare\.cam", []),
    ("Clare Hall", "https://www.clarehall.cam.ac.uk/", r"clare hall|clarehall\.cam", []),
    ("Corpus Christi", "https://www.corpus.cam.ac.uk/", r"corpus christi college|corpus playroom|parker library|"
                                                         r"corpus\.cam|taylor library|mccrum", []),
    ("Darwin", "https://www.darwin.cam.ac.uk/", r"darwin college|darwin\.cam", []),
    ("Downing", "https://www.dow.cam.ac.uk/", r"downing college|heong gallery|dow\.cam|howard theatre", []),
    ("Emmanuel", "https://www.emma.cam.ac.uk/", r"emmanuel college|emma\.cam", []),
    ("Fitzwilliam", "https://www.fitz.cam.ac.uk/", r"fitzwilliam college|fitz\.cam", []),
    ("Girton", "https://www.girton.cam.ac.uk/", r"girton college|girton\.cam", []),
    ("Gonville & Caius", "https://www.cai.cam.ac.uk/", r"gonville|caius|cai\.cam", []),
    ("Homerton", "https://www.homerton.cam.ac.uk/", r"homerton college|homerton\.cam", []),
    ("Hughes Hall", "https://www.hughes.cam.ac.uk/", r"hughes hall|hughes\.cam", []),
    ("Jesus", "https://www.jesus.cam.ac.uk/", r"jesus college|jesus\.cam", []),
    ("King's", "https://www.kings.cam.ac.uk/", r"king'?s college|kings\.cam|kingscollegechoir", []),
    ("Lucy Cavendish", "https://www.lucy.cam.ac.uk/", r"lucy cavendish|lucy\.cam", []),
    ("Magdalene", "https://www.magd.cam.ac.uk/", r"magdalene college|pepys library|magd\.cam|cripps court", []),
    ("Murray Edwards", "https://www.murrayedwards.cam.ac.uk/", r"murray edwards|women'?s art collection|murrayedwards\.cam", []),
    ("Newnham", "https://newn.cam.ac.uk/", r"newnham college|newn\.cam", []),
    ("Pembroke", "https://www.pem.cam.ac.uk/", r"pembroke college|pem\.cam", []),
    ("Peterhouse", "https://www.pet.cam.ac.uk/", r"peterhouse|pet\.cam", []),
    ("Queens'", "https://www.queens.cam.ac.uk/", r"queens'? college|queens\.cam", []),
    ("Robinson", "https://www.robinson.cam.ac.uk/", r"robinson college|robinson\.cam", []),
    ("St Catharine's", "https://www.caths.cam.ac.uk/", r"st\.? catharine'?s|caths\.cam", []),
    ("St Edmund's", "https://www.st-edmunds.cam.ac.uk/", r"st\.? edmund'?s college|st-edmunds\.cam", []),
    ("St John's", "https://www.joh.cam.ac.uk/", r"st\.? john'?s college|joh\.cam|sjcchoir|st john'?s college chapel", []),
    ("Selwyn", "https://www.sel.cam.ac.uk/", r"selwyn college|sel\.cam", []),
    ("Sidney Sussex", "https://www.sid.cam.ac.uk/", r"sidney sussex|sid\.cam", []),
    ("Trinity", "https://www.trin.cam.ac.uk/", r"trinity college(?! of)|wren library|trin\.cam", []),
    ("Trinity Hall", "https://www.trinhall.cam.ac.uk/", r"trinity hall|trinhall\.cam", []),
    ("Wolfson", "https://www.wolfson.cam.ac.uk/", r"wolfson college|wolfson\.cam", []),
]
LINK_RE = re.compile(r"\b(events?|what'?s[- ]on|lectures?|concerts?|music|exhibitions?|gardens?|open days?|"
                     r"public|visit(?:ing|ors)?|library|art|choir|talks?)\b", re.I)
HREF_RE = re.compile(r"(event|whats-on|what-s-on|lecture|concert|music|exhibition|garden|visit|public|choir|arts?\b|"
                     r"library|talks?)", re.I)
TYPES = {
    "лекции": r"\b(lectures?|talks?|in conversation|symposium|seminar)\b",
    "концерты": r"\b(concerts?|recitals?|choir|organ|music society|orchestra)\b",
    "выставки": r"\b(exhibitions?|gallery|display)\b",
    "сады": r"\b(gardens?|fellows'? garden|ngs|national garden scheme)\b",
    "дни открытых дверей": r"\b(open days?|open house|heritage open days|open cambridge)\b",
    "библиотека": r"\b(wren library|parker library|pepys library|old library|library open)\b",
    "службы": r"\b(evensong|eucharist|matins|compline|chapel services?)\b",
    "выпускники": r"\b(alumni|reunion|members'? events?|dinner for members|gaudy|development office)\b",
}
DATE_RE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+\d{4})?"
                     r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
                     r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", re.I)
FUTURE_MONTHS = re.compile(r"\b(Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b", re.I)


def feeds(html: str, base: str) -> list[str]:
    out = []
    for m in re.finditer(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*href="([^"]+)"', html):
        out.append("RSS " + urljoin(base, m.group(1)))
    for m in re.finditer(r'href="([^"]+(?:\.ics|/ical/?|ical=1|webcal:[^"]+|/feed/?))"', html):
        out.append("iCal/feed " + urljoin(base, m.group(1)))
    n = len(re.findall(r'"@type"\s*:\s*"(?:Event|MusicEvent|EducationEvent|ExhibitionEvent|TheaterEvent)"', html))
    if n:
        out.append(f"JSON-LD Event ×{n}")
    return sorted(set(out))[:6]


def candidates(home_html: str, home: str) -> list[str]:
    from selectolax.parser import HTMLParser
    host = urlparse(home).netloc
    seen, out = set(), []
    for a in HTMLParser(home_html).css("a[href]"):
        href = urljoin(home, a.attributes.get("href") or "")
        t = re.sub(r"\s+", " ", a.text(strip=True))
        if urlparse(href).netloc != host or href in seen or "#" in href or len(t) > 60:
            continue
        path = urlparse(href).path.lower()
        if (LINK_RE.search(t) and HREF_RE.search(path)) or re.search(r"/(events?|whats-on)/?$", path):
            seen.add(href)
            score = (3 if re.search(r"/(events?|whats-on|what-s-on)/?$", path) else 0) + \
                    (2 if re.search(r"public|lecture|concert|exhibition|garden", path) else 0) - path.count("/") * 0.1
            out.append((score, href))
    return [h for _, h in sorted(out, reverse=True)[:4]]


def page_info(http, url: str) -> dict:
    try:
        r = http.get(url)
    except Disallowed:
        return {"url": url, "result": "robots.txt запрещает"}
    except FetchError as e:
        return {"url": url, "result": str(e)[:80]}
    text, _ = visible_text(r.text)
    return {"url": r.url, "result": "ok", "chars": len(text), "dates": len(DATE_RE.findall(text)),
            "future_month_mentions": len(FUTURE_MONTHS.findall(text)), "feeds": feeds(r.text, r.url),
            "types": [k for k, rx in TYPES.items() if re.search(rx, text, re.I)], "text_head": text[:600]}


def db_counts(con, pattern: str, today: date) -> dict:
    rx = re.compile(pattern, re.I)
    lo, hi = (today - timedelta(days=60)).isoformat(), (today + timedelta(days=60)).isoformat()
    past, future, srcs, titles = 0, 0, {}, []
    for e in con.execute("""SELECT e.event_id, e.title, e.date_start, e.venue_name, e.address, e.url,
            group_concat(DISTINCT r.source_id) AS srcs FROM events e LEFT JOIN raw_items r USING(event_id)
            WHERE e.date_start BETWEEN ? AND ? GROUP BY e.event_id""", (lo, hi)):
        hay = " ".join(x or "" for x in (e["venue_name"], e["address"], e["title"], e["url"]))
        if not rx.search(hay):
            continue
        if e["date_start"] < today.isoformat():
            past += 1
        else:
            future += 1
            if len(titles) < 6:
                titles.append(f"{e['date_start']} {e['title'][:60]}")
        for s in (e["srcs"] or "").split(","):
            if s:
                srcs[s] = srcs.get(s, 0) + 1
    return {"past_60": past, "next_60": future, "sources": srcs, "examples": titles}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-search", action="store_true")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    con = connect()
    http = PoliteClient()
    today = date.today()
    kee = None
    if not args.no_search:
        from pipeline.keenable import Keenable
        kee = Keenable(con)
    out = []
    for name, home, pattern, extra in COLLEGES:
        if args.only and name not in args.only:
            continue
        row = {"college": name, "home": home}
        try:
            h = http.get(home)
            row["robots"] = "разрешено"
            cands = candidates(h.text, h.url) + extra
        except Disallowed:
            row["robots"], cands = "запрещено", []
        except FetchError as e:
            row["robots"], cands = f"главная: {str(e)[:60]}", extra
        row["robots_status"] = http.robots_status.get(f"{urlparse(home).scheme}://{urlparse(home).netloc}")
        if kee is not None:
            res = kee.search(f"{name} College Cambridge public events lectures concerts exhibitions", "source_discovery_7b")
            host = urlparse(home).netloc.replace("www.", "")
            found = [r["url"] for r in res if host in r.get("url", "")]
            row["search_hits"] = found[:5]
            cands += [u for u in found if HREF_RE.search(urlparse(u).path) and u not in cands][:2]
        row["pages"] = [page_info(http, u) for u in cands[:5]]
        row["db"] = db_counts(con, pattern, today)
        out.append(row)
        best = max(row["pages"], key=lambda p: p.get("dates", 0), default={})
        print(f"{name:18} robots={row['robots'][:12]:12} pages={len(row['pages'])} best={best.get('url', '-')[:60]} "
              f"dates={best.get('dates', 0)} feeds={best.get('feeds', [])[:1]} db={row['db']['past_60']}/{row['db']['next_60']}",
              flush=True)
    res = {"checked": today.isoformat(), "requests": http.requests,
           "keenable_calls": kee.calls if kee else 0, "colleges": out}
    (ROOT / "data" / "college_audit_7b.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
