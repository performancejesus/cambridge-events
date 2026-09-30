"""9. Имена латиницей (исправляющая): имена людей и групп из данных (исполнитель, состав) в русском тексте — латиницей.
Haiku переписывает (build_issue.fix_names_ru — пункты, вступление и вступление темы), проверка повторяется. Проверка —
имя из данных написано в русском тексте кириллицей («Роба Чапмена», «Саймон Амстелл» во вступлении v9).
Этап 7d (правки по v10): и «В кино» — режиссёры и актёры из описания Wikipedia фильма («Пол Гринграсс», «Томасин
Маккензи», «Джо Кой» в v10)."""

from __future__ import annotations

import re

from . import FIX, Finding
from .common import name_in_text

RULE, TITLE, LEVEL = 9, "Имена людей и групп — латиницей", FIX


FILM_NAME_RE = re.compile(r"\b([A-Z][a-zA-Z'’-]+(?: [A-Z]\.)?(?: [A-Z][a-zA-Z'’-]+){1,2})\b")
NOT_PERSON = re.compile(r"\b(Pictures|Studios?|Films?|Entertainment|Animation|Productions?|Records|Festival|University|"
                        r"College|Museum|Theatre|Cinema|Kingdom|States|America|Europe|England|London|New|North|South|East|"
                        r"West|Street|Road|Island|Park|Award|Awards|Academy|Prize|Series|Season|Part|Chapter|The|A|An|In|"
                        r"On|At|It|Its|This|His|Her|Their|After|Before|During|When|While|Following|Wikipedia|January|"
                        r"February|March|April|May|June|July|August|September|October|November|December)\b")


def film_names(c: dict) -> list[str]:
    """Режиссёры и актёры из описания Wikipedia (wiki_extract) фильма: «directed by Paul Greengrass», «starring …»."""
    if not (c.get("kind") == "film_release" or c.get("film")):
        return []
    text = f"{c.get('wiki_description') or ''} {c.get('wiki_extract') or ''}"
    title = c.get("title") or ""
    return [n for n in dict.fromkeys(FILM_NAME_RE.findall(text)) if not NOT_PERSON.search(n) and n not in title]


def names_of(cands) -> list[str]:
    out = []
    for c in cands:
        for n in film_names(c):
            if n not in out:
                out.append(n)
        if {"S018", "S123"} & set(c.get("sources") or []):
            continue   # футбол: названия клубов
        for n in [c.get("performer")] + list(c.get("lineup") or []):
            if n and n not in out and re.search(r"[A-Za-z]", n):
                out.append(n)
    return out


TRANSLIT = {"дж": "j", "ж": "zh", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ю": "yu", "я": "ya", "й": "y",
            "ы": "y", "э": "e", "е": "e", "ё": "yo", "ь": "", "ъ": "", "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
            "з": "z", "и": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
            "у": "u", "ф": "f"}


def _lat(s: str) -> str:
    s = s.lower()
    for k in sorted(TRANSLIT, key=len, reverse=True):
        s = s.replace(k, TRANSLIT[k])
    return re.sub(r"(.)\1", r"\1", re.sub(r"[^a-z ]", "", s))


def full_name_cyr(name: str, text: str) -> bool:
    """Этап 7d: короткие фамилии («Jo Koy» ↔ «Джо Кой») «скелет» согласных не ловит — имя целиком в транслитерации."""
    import difflib
    n = _lat(re.sub(r"[^A-Za-z ]", " ", name))
    k = len(n.split())
    if k < 2 or len(n.replace(" ", "")) < 4:
        return False
    words = re.findall(r"[А-Яа-яЁё]+", text)
    return any(difflib.SequenceMatcher(None, _lat(" ".join(words[i:i + k])), n).ratio() >= 0.85
               for i in range(len(words) - k + 1))


def cyrillic_only(name: str, text: str) -> bool:
    """Имя есть в тексте, но не латиницей (фамилия узнаётся по кириллице)."""
    last = [p for p in re.findall(r"[A-Za-z'’-]+", name) if len(p) > 2]
    if not last or re.search(rf"\b{re.escape(last[-1])}\b", text, re.I):
        return False
    lat_only = re.sub(r"[А-Яа-яЁё]+", " ", text)
    # этап 7d: имя кириллицей пишется с заглавной — «уместились» не «Amstell», «кино» не «Quinn» (ложные находки v11)
    caps = re.sub(r"\b[а-яё][А-Яа-яЁё-]*", " ", text)
    return (name_in_text(name, caps) and not name_in_text(name, lat_only)) or full_name_cyr(name, caps)


def check(ctx) -> Finding:
    f = Finding()
    all_names = []
    for e in ctx.entries("ru", compact=False):
        names = names_of(e["cands"])
        all_names += names
        for n in names:   # заголовок и описание — по отдельности: «Лекция Rob Chapman» + «Роб Чапмен» в описании — ошибка
            if cyrillic_only(n, e["title"]) or cyrillic_only(n, e["blurb"]):
                f.violations.append(f"«{e['title']}»: {n} — кириллицей")
    L = ctx.layout("ru")
    intros = [("вступление", L["intro"] or "")] + [("вступление темы", s["intro"]) for s in L["sections"] if s.get("intro")]
    for where, text in intros:
        for n in dict.fromkeys(all_names):
            if cyrillic_only(n, text):
                f.violations.append(f"{where}: {n} — кириллицей")
    return f
