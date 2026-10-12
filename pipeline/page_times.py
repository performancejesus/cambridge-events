"""Правка 6 после v14: время пункта — со страницы события, а не из списка.

Space Safari Drone Light Show: в списке Jockey Club — 12:00, у Visit Cambridge — 16:00; выпуск написал «12:00 и 16:00»,
а на странице события «4:00 PM – 9:00 PM», шоу «примерно через 30 минут после заката, 7:15–8:00 PM». Страница берётся
из кэша общего слоя запросов (без сети): если на ней указано время начала и оно расходится с временем из списка — время
пункта заменяется на время со страницы; отдельное время самого шоу («show … between 7:15 PM and 8:00 PM») — пометкой.
"""

from __future__ import annotations

import gzip
import hashlib
import re

from .db import ROOT

BODY_DIR = ROOT / "data" / "cache" / "pages"
T = r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|AM|PM)?"
RANGE_RE = re.compile(T + r"\s*(?:–|-|to)\s*" + T + r"(?![\d:])")
GATES_RE = re.compile(r"(?:gates|doors) open(?:s)?(?: at| from)?\s*" + T, re.I)
SHOW_RE = re.compile(r"\b(?:drone show|show|fireworks?|display)\b[^.|]{0,90}?\bbetween\s+" + T + r"\s+and\s+" + T, re.I)


def _hm(h, m, ap) -> str | None:
    if h is None:
        return None
    h, m = int(h), int(m or 0)
    if ap:
        ap = ap.lower()
        h = h % 12 + (12 if ap == "pm" else 0)
    elif not m and h < 8:   # «4 – 9» без am/pm и минут — не время
        return None
    return f"{h:02d}:{m:02d}" if 0 <= h < 24 and 0 <= m < 60 else None


def cached_text(url: str | None) -> str:
    if not url:
        return ""
    p = BODY_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".gz")
    if not p.exists():
        return ""
    try:
        from selectolax.parser import HTMLParser
        body = HTMLParser(gzip.decompress(p.read_bytes()).decode("utf8", "replace")).body
        return re.sub(r"\s+", " ", body.text(separator=" | ")) if body else ""
    except Exception:   # битый кэш — без времени со страницы
        return ""


def page_time(text: str) -> dict:
    """{start, end, show_from, show_to}: время начала (диапазон с am/pm или «gates open») и время самого шоу."""
    out = {}
    s = SHOW_RE.search(text or "")
    if s:
        a, b = _hm(*s.groups()[0:3]), _hm(*s.groups()[3:6])
        if a and b:
            out["show_from"], out["show_to"] = a, b
    g = GATES_RE.search(text or "")
    for m in RANGE_RE.finditer(text or ""):
        g1 = m.groups()
        if not (g1[2] or g1[5]) or (s and s.start() <= m.start() <= s.end()):
            continue   # без am/pm — не время (номера, даты); диапазон шоу — не время начала
        a, b = _hm(g1[0], g1[1], g1[2] or g1[5]), _hm(*g1[3:6])
        if a and b:
            out["start"], out["end"] = a, b
            break
    if "start" not in out and g:
        out["start"] = _hm(*g.groups())
    return {k: v for k, v in out.items() if v}


def on_page(t: str, text: str) -> bool:
    """Время «16:00» есть на странице в любом написании: 16:00, 16.00, 4pm, 4:00 PM, 4.00pm."""
    h, m = int(t[:2]), int(t[3:5])
    h12, ap = (h % 12 or 12), ("pm" if h >= 12 else "am")
    pats = [rf"\b{h:02d}[:.]{m:02d}\b", rf"\b{h}[:.]{m:02d}\b(?!\s*[ap]m)" if h > 12 else rf"\b{h}[:.]{m:02d}\b",
            rf"\b{h12}(?:[:.]{m:02d})?\s*{ap}\b"]
    return any(re.search(p, text or "", re.I) for p in pats)


def apply(c: dict, pt: dict, text: str = "") -> bool:
    """Время в датах кандидата — по странице события. Время из списка остаётся, если оно есть на странице (из двух
    склеенных — то, что на странице); если ни одного нет, а у страницы есть время начала — берётся оно. True — изменено."""
    if not c.get("dates") or not text:
        return False
    days = {x[0] for x in c["dates"]}
    if len(days) != 1:   # несколько дней — у страницы может быть одно время на всё; не трогаем
        return False
    times = {x[2] for x in c["dates"] if x[2]}
    good = {t for t in times if on_page(t, text)}
    new = good if good else ({pt["start"]} if pt.get("start") else times)
    changed = new != times
    if changed:
        c["dates"] = [(c["dates"][0][0], c["dates"][0][1], t) for t in sorted(new)] or c["dates"][:1]
        c["time_from_page"] = True
    if pt.get("show_from"):
        c["show_time"] = (pt["show_from"], pt.get("show_to"))
        changed = True
    return changed


SHOWS_RU = re.compile(r"\s*[—,–-]?\s*(?:два|две|три|2|3) (?:вечерних |дневных )?(?:показа|шоу|сеанса|представления)\b", re.I)
SHOWS_EN = re.compile(r",?\s*(?:in )?(?:two|three|2|3) (?:evening |daytime )?(?:shows|performances|screenings)\b", re.I)


def fix(result: dict, pools) -> list[tuple[str, str]]:
    """Время со страницы события; если показов стал один (склеены два времени из списков), «два вечерних показа» из
    описания убирается."""
    notes = []
    for sec in result["sections"]:
        for it in sec["items"]:
            for i in it.get("ids") or []:
                c = pools.candidates.get(i)
                if not c or c.get("kind") not in ("event",) or not c.get("dates"):
                    continue
                before = sorted({x[2] or "" for x in c["dates"]})
                text = cached_text(it.get("url") or c.get("url"))
                pt = page_time(text)
                if apply(c, pt, text):
                    if len({x[2] for x in c["dates"]}) == 1:
                        for k, rx in (("blurb_ru", SHOWS_RU), ("blurb_en", SHOWS_EN)):
                            if it.get(k) and rx.search(it[k]):
                                it[k] = rx.sub("", it[k]).replace(" .", ".")
                    show = f", шоу около {c['show_time'][0]}–{c['show_time'][1]}" if c.get("show_time") else ""
                    notes.append((f"“{it.get('title_en')}”: time from the event page",
                                  f"«{it.get('title_ru')}»: время со страницы события — {' и '.join(x[2] for x in c['dates'] if x[2])}{show} "
                                  f"(было: {' и '.join(x for x in before if x) or 'без времени'})"))
    return notes
