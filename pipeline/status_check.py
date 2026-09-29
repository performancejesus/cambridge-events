"""Этап 7: контур отмен и изменений — перепроверка страниц отобранных событий.

Для каждого события — одна загрузка страницы (продавец билетов из этапа 6d, иначе основная ссылка события), robots.txt
соблюдается, без модели. На видимом тексте рядом с названием события (±1500 знаков; страница самого события — весь текст)
ищутся признаки:
  - cancelled  — «cancelled», «has been cancelled»;
  - postponed  — «postponed», «rescheduled», «new date»;
  - sold_out   — «sold out», «fully booked», «no tickets available»;
  - on_sale    — «book now», «buy tickets», «add to basket», цена со знаком £ рядом с кнопкой;
  - сигналы срочности — «few tickets left», «last few», «selling fast», «limited availability», «almost sold out»,
    «low availability», конец ранней цены («early bird … until/ends …»).
Результат — таблица page_status (последняя проверка события) и история в status_history (через ingest.refresh:
статус со страницы учитывается при каждом пересчёте). «Статус читается» = найден хотя бы один признак.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

SCHEMA = """CREATE TABLE IF NOT EXISTS page_status (
    event_id   INTEGER PRIMARY KEY,
    url        TEXT,
    status     TEXT,       -- cancelled | postponed | sold_out | on_sale | '' (не читается)
    urgency    TEXT,       -- few_left | selling_fast | early_bird_ends | ''
    evidence   TEXT,       -- фрагмент страницы с признаком
    result     TEXT,       -- ok | not_found (нет названия на странице) | error
    checked_at TEXT
)"""
# «cancelled» в правилах возврата («if the event is cancelled») и в меню — не отмена: нужна утвердительная форма
CANCEL_RE = re.compile(r"(?<!if )(?<!if the event )\b((?:has|have) been cancel+ed|is (?:now )?cancel+ed|"
                       r"(?:event|show|performance|concert|gig|match) cancel+ed|cancel+ed\s*[:!-]|CANCELL?ED\b|"
                       r"called off)", re.I)
POSTPONE_RE = re.compile(r"\b(postponed|rescheduled|new date(?:s)? (?:to be|will be) announced|moved to a new date)\b", re.I)
SOLD_OUT_RE = re.compile(r"\b(sold[ -]out|fully booked|no (?:more )?tickets (?:are )?available|tickets are no longer "
                         r"available|this event is full|waiting list only|join the waiting ?list)\b", re.I)
ON_SALE_RE = re.compile(r"\b(book now|buy (?:now|tickets?)|get tickets|add to (?:basket|cart)|select (?:tickets|seats)|"
                        r"book tickets|tickets? from £\s?\d)", re.I)
FEW_RE = re.compile(r"\b(few tickets (?:left|remaining)|last (?:few |remaining )?(?:tickets|seats|places)(?! for)|limited (?:availability|"
                    r"tickets|seats)|almost sold[ -]out|low availability|nearly sold[ -]out|final tickets|only \d+ "
                    r"(?:tickets|places|seats) left)\b", re.I)
FAST_RE = re.compile(r"\b(selling fast|high demand|going fast)\b", re.I)
EARLY_RE = re.compile(r"\bearly[ -]?bird\b[^.|]{0,80}?\b(until|ends?|ending|expires?|closes?|before)\b[^.|]{0,40}", re.I)
NEWS_HOSTS = ("cambridge-news.co.uk", "cambridgeindependent.co.uk", "peterboroughtoday.co.uk", "huntspost.co.uk",
              "cambstimes.co.uk", "wisbechstandard.co.uk", "elystandard.co.uk")


def init(con: sqlite3.Connection) -> None:
    con.execute(SCHEMA)


def _window(text: str, title: str, url: str = "") -> tuple[str, bool]:
    """Фрагмент вокруг названия события; на странице-списке признаки чужих событий не должны засчитываться.
    Страница самого события (в адресе — слова из названия) — весь текст."""
    low = text.lower()
    slug = re.sub(r"[^a-z0-9]+", " ", url.lower())
    title_words = [x for x in re.findall(r"[a-z0-9]{4,}", title.lower())]
    if title_words and sum(1 for x in title_words if x in slug) >= min(2, len(title_words)):
        return text, True
    words = sorted(re.findall(r"[a-z0-9']{4,}", title.lower()), key=len, reverse=True)[:3]
    pos = [low.find(w) for w in words if low.find(w) >= 0]
    if not pos:
        return "", False
    i = min(pos)
    return text[max(0, i - 400):i + 1500], True


LABEL_MAX = 45   # метка статуса на странице — короткий отдельный элемент («Sold out», «Limited availability»)
LABELS = [
    ("cancelled", None, re.compile(r"^(cancel+ed|this (?:event|show|performance|concert) (?:has been|is) cancel+ed\.?|"
                                   r"event cancel+ed|cancel+ed\s*[:!-].*)$", re.I)),
    ("postponed", None, re.compile(r"^(postponed|rescheduled|this (?:event|show) has been (?:postponed|rescheduled)\.?|"
                                   r"postponed\s*[:!-].*|new date to be (?:announced|confirmed))$", re.I)),
    ("sold_out", None, re.compile(r"^(sold[ -]?out!?|fully booked|this (?:event|show|performance) is (?:sold out|full)\.?|"
                                  r"no tickets available|tickets? no longer available|waiting list only)$", re.I)),
    (None, "few_left", re.compile(r"^(limited availability|last few( tickets)?!?|last (?:remaining )?tickets!?|few tickets "
                                  r"(?:left|remaining)!?|almost sold[ -]?out!?|nearly sold[ -]?out!?|low availability|"
                                  r"only \d+ (?:tickets|places|seats) left!?|\d+ tickets? left!?|final (?:few )?tickets!?)$", re.I)),
    (None, "selling_fast", re.compile(r"^(selling fast!?|high demand|going fast!?)$", re.I)),
    ("on_sale", None, re.compile(r"^(book now|book tickets|buy (?:now|tickets?)|get tickets|add to (?:basket|cart)|"
                                 r"select (?:tickets|seats)|book|buy)$", re.I)),
]
# в свободном тексте — только однозначные фразы (не «sold out their tour in 2023»)
TEXT_RE = [("cancelled", re.compile(r"\bthis (?:event|show|performance|concert|talk) (?:has been|is) cancel+ed\b", re.I)),
           ("postponed", re.compile(r"\bthis (?:event|show|performance|concert|talk) (?:has been|is) (?:postponed|"
                                    r"rescheduled)\b", re.I)),
           ("sold_out", re.compile(r"\bthis (?:event|show|performance|concert) (?:is|has) (?:now )?sold[ -]out\b", re.I))]


def classify(text: str) -> tuple[str, str, str]:
    """(status, urgency, evidence): метки — короткие отдельные элементы страницы (разделитель «|»); из обычного текста —
    только однозначные фразы. Несколько «sold out» рядом с кнопкой покупки — распроданы часть дат или категорий."""
    segs = [x.strip() for x in text.split("|")]
    found: dict[str, str] = {}
    urg, urg_ev = "", ""
    for seg in segs:
        m = re.match(r"^(cancel+ed|postponed)\s*:", seg, re.I)   # «CANCELLED: Chris Hadfield: …» в названии
        if m:
            found.setdefault("cancelled" if m.group(1).lower().startswith("cancel") else "postponed", seg[:80])
        if not seg or len(seg) > LABEL_MAX:
            continue
        for st, u, rx in LABELS:
            if rx.match(seg):
                if st and st not in found:
                    found[st] = seg
                if u and not urg:
                    urg, urg_ev = u, seg
    for st, rx in TEXT_RE:
        m = rx.search(text)
        if m and st not in found:
            found[st] = m.group(0)
    m = EARLY_RE.search(text)
    if m and not urg:
        urg, urg_ev = "early_bird_ends", m.group(0)
    for st in ("cancelled", "postponed"):
        if st in found:
            return st, "", found[st]
    if "sold_out" in found:
        if "on_sale" in found:
            return "on_sale", urg or "some_dates_sold_out", urg_ev or f"{found['sold_out']} / {found['on_sale']}"
        return "sold_out", "", found["sold_out"]
    if "on_sale" in found:
        return "on_sale", urg, urg_ev or found["on_sale"]
    return "", urg, urg_ev


def check(con: sqlite3.Connection, http, event_id: int, url: str, title: str) -> dict:
    from collectors.llmlist import visible_text
    init(con)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res = {"event_id": event_id, "url": url, "status": "", "urgency": "", "evidence": "", "result": "error"}
    if not url or any(h in url for h in NEWS_HOSTS):
        res["result"] = "skipped (газета или нет ссылки)"
    else:
        try:
            html = http.get(url).text
            text, _ = visible_text(html)
            text = re.sub(r"(?:\| )+", "| ", text)
            frag, found = _window(text, title, url)
            if found:
                res["status"], res["urgency"], res["evidence"] = classify(frag)
                res["result"] = "ok"
                if not res["status"] and frag is text:   # страница события: кнопки покупки не всегда в видимом тексте
                    from selectolax.parser import HTMLParser
                    buttons = " | ".join((b.text() or "").strip() for b in HTMLParser(html).css("a, button")
                                         if 0 < len((b.text() or "").strip()) < 40)
                    st, urg, evid = classify(buttons)
                    if st in ("sold_out", "on_sale"):
                        res["status"], res["urgency"] = st, res["urgency"] or urg
                        res["evidence"] = res["evidence"] or f"кнопка: {evid[:80]}"
            else:
                res["result"] = "not_found"
        except Exception as e:  # noqa: BLE001 — robots.txt, защита, сеть: статус не читается
            res["result"] = f"error: {type(e).__name__}"
    con.execute("INSERT OR REPLACE INTO page_status VALUES (?,?,?,?,?,?,?)",
                (event_id, url, res["status"], res["urgency"], res["evidence"][:300], res["result"], now))
    con.commit()
    return res


def latest(con: sqlite3.Connection, event_id: int) -> sqlite3.Row | None:
    init(con)
    return con.execute("SELECT * FROM page_status WHERE event_id=?", (event_id,)).fetchone()
