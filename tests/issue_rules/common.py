"""Общее для проверок: контекст выпуска, обход пунктов, сравнение имён латиницей и кириллицей, уровни ссылок."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from pipeline import issue


@dataclass
class Ctx:
    w: issue.Window
    version: str
    result: dict                       # ответ модели после постобработки (как в issues/<выпуск>_model.json)
    pools: issue.Pools
    con: object
    out_dir: Path
    stem: str
    html: dict = field(default_factory=dict)       # reader_ru, reader_en → текст итоговой HTML
    lists: dict | None = None                      # списки редакторской версии (причины пропусков)
    fix_log: dict = field(default_factory=dict)    # правило → [(en, ru)] что исправлено при сборке
    claims: dict | None = None                     # сверка утверждений с источниками (r02), по ключу пункта
    links: dict | None = None                      # url → результат проверки (r07)
    missing_reasons: list = field(default_factory=list)
    options: dict = field(default_factory=dict)    # links: bool, api: bool
    _layout: dict = field(default_factory=dict)

    def layout(self, lang: str) -> dict:
        if lang not in self._layout:
            self._layout[lang] = issue.layout(self.result, self.pools, self.w, lang)
        return self._layout[lang]

    def entries(self, lang: str = "ru", compact: bool | None = None):
        """Пункты письма как их видит читатель: рубрика, подраздел, заголовок, строка с датой, описание, ссылка, кандидаты."""
        for sec in self.layout(lang)["sections"]:
            for g in sec["groups"]:
                for it in g["items"]:
                    if compact is not None and bool(it.get("compact")) != compact:
                        continue
                    yield {"rubric": sec["rubric"], "group": g["title"], "title": it["title"], "meta": it.get("meta") or "",
                           "blurb": it.get("blurb") or "", "url": it.get("url"), "ids": it.get("ids") or [],
                           "compact": bool(it.get("compact")), "more": bool(it.get("more")),
                           "cands": [self.pools.candidates[i] for i in it.get("ids") or [] if i in self.pools.candidates]}

    def model_items(self):
        """Пункты ответа модели (оба языка) с рубрикой."""
        for sec in self.result["sections"]:
            for it in sec["items"]:
                yield sec["rubric"], it

    def texts(self, lang: str = "ru"):
        """(где, текст): вступление, вступление темы, заголовки и описания пунктов."""
        L = self.layout(lang)
        yield "вступление", L["intro"] or ""
        for sec in L["sections"]:
            if sec.get("intro"):
                yield "вступление темы", sec["intro"]
        for e in self.entries(lang):
            yield e["title"], f"{e['title']}. {e['blurb']}"


# --- имена: латиница ↔ кириллица (проверка «имя уже есть в тексте», дубль «Также в программе») ---

_CYR = {"дж": "J", "ч": "C", "ш": "S", "щ": "S", "ж": "J", "х": "", "ц": "ts", "а": "a", "б": "b", "в": "v", "г": "g",
        "д": "d", "е": "e", "ё": "e", "з": "s", "и": "i", "й": "", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "u",
        "я": "a"}
_VOWELS = set("aeiouy")


def _collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", "".join(ch for ch in s if ch not in _VOWELS))


def skeleton_cyr(word: str) -> str:
    w = word.lower()
    out, i = [], 0
    while i < len(w):
        if w[i:i + 2] == "дж":
            out.append("J")
            i += 2
            continue
        out.append(_CYR.get(w[i], ""))
        i += 1
    return _collapse("".join(out))


def skeleton_lat(word: str, drop_w: bool = False) -> str:
    w = word.lower()
    for a, b in (("sch", "S"), ("ch", "C"), ("sh", "S"), ("ph", "f"), ("th", "t"), ("ck", "k"), ("dg", "J"), ("x", "ks"),
                 ("q", "k"), ("c", "k"), ("j", "J"), ("z", "s"), ("h", "")):
        w = w.replace(a, b)
    w = w.replace("w", "" if drop_w else "v")
    return _collapse(re.sub(r"[^a-zA-Z]", "", w))


TITLES_RE = re.compile(r"^(professor|prof\.?|dr\.?|sir|dame|rev\.?|lord|lady|baroness|baron|mr\.?|mrs\.?|ms\.?)\s+", re.I)


def name_in_text(name: str, text: str) -> bool:
    """Имя названо в тексте — латиницей (полностью или фамилией) или кириллицей (фамилия по «скелету» согласных:
    «Josephine Crawley Quinn» ↔ «Джозефин Кроули Куинн», «Rob Chapman» ↔ «Роба Чапмена»)."""
    if not name:
        return True
    t = text.lower()
    n = TITLES_RE.sub("", name.strip())
    if n.lower() in t:
        return True
    parts = [p for p in re.findall(r"[A-Za-zÀ-ÿ'’-]+", n) if len(p) > 2]
    if not parts:
        return n.lower() in t
    last = parts[-1]
    if re.search(rf"\b{re.escape(last.lower())}\b", t):
        return True
    targets = {skeleton_lat(last), skeleton_lat(last, drop_w=True)} - {""}
    if not targets or max(len(x) for x in targets) < 2:
        return False
    for word in re.findall(r"[А-Яа-яЁё-]+", text):
        sk = skeleton_cyr(word)
        if len(sk) < 2:
            continue
        for tg in targets:
            if sk == tg or (len(tg) >= 4 and difflib.SequenceMatcher(None, sk, tg).ratio() >= 0.85):
                return True
            # падежные окончания: «Чапмена» → skeleton «Cpmn», «Барретта» → «brt»
            if len(tg) >= 3 and sk.startswith(tg) and len(sk) - len(tg) <= 1:
                return True
    return False


# --- ссылки: первоисточник → продавец билетов → агрегатор → газета (правило 11) ---

AGGREGATORS = {"ents24.com", "musiclivecambridge.com", "whatsonincambridge.com", "visitcambridge.org", "songkick.com",
               "camdram.net", "allevents.in", "enjoy.ly", "visitely.org.uk", "findarace.com", "runabc.co.uk",
               "museums.cam.ac.uk", "admin.cam.ac.uk", "talks.cam.ac.uk", "cam.ac.uk/whatson"}
VENDORS = {"cambridgelivetickets.co.uk", "wegottickets.com", "eventbrite.co.uk", "eventbrite.com", "ticketsource.co.uk",
           "tickettailor.com", "seetickets.com", "ticketmaster.co.uk", "dice.fm", "fatsoma.com", "skiddle.com",
           "universe.com", "ticketweb.uk", "gigantic.com", "stargreen.com", "trybooking.com", "iceaccount.co.uk"}
NEWSPAPERS = {"cambridge-news.co.uk", "cambridgeindependent.co.uk", "huntspost.co.uk", "cambstimes.co.uk",
              "elystandard.co.uk", "wisbechstandard.co.uk", "peterboroughtoday.co.uk", "varsity.co.uk"}
TIER_RU = {0: "площадка / организатор", 1: "продавец билетов", 2: "агрегатор", 3: "газета", 4: "Wikipedia"}


def host(url: str | None) -> str:
    h = (urlparse(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def tier(url: str | None) -> int:
    h = host(url)
    if not h:
        return 9
    if h.endswith("wikipedia.org"):
        return 4
    if any(h == x or h.endswith("." + x) for x in NEWSPAPERS):
        return 3
    if any(h == x or h.endswith("." + x) for x in AGGREGATORS):
        return 2
    if any(h == x or h.endswith("." + x) for x in VENDORS):
        return 1
    return 0


UNKNOWN_PRICE = re.compile(r"^(цены на сайте|prices on the website|цена не указана|price not listed)$", re.I)


def price_nums(text: str | None) -> list[float]:
    text = re.sub(r"(\d),(\d{2})\b", r"\1.\2", text or "")
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))]
