"""9. Имена латиницей (исправляющая): имена людей и групп из данных (исполнитель, состав) в русском тексте — латиницей.
Haiku переписывает (build_issue.fix_names_ru — пункты, вступление и вступление темы), проверка повторяется. Проверка —
имя из данных написано в русском тексте кириллицей («Роба Чапмена», «Саймон Амстелл» во вступлении v9)."""

from __future__ import annotations

import re

from . import FIX, Finding
from .common import name_in_text

RULE, TITLE, LEVEL = 9, "Имена людей и групп — латиницей", FIX


def names_of(cands) -> list[str]:
    out = []
    for c in cands:
        if {"S018", "S123"} & set(c.get("sources") or []):
            continue   # футбол: названия клубов
        for n in [c.get("performer")] + list(c.get("lineup") or []):
            if n and n not in out and re.search(r"[A-Za-z]", n):
                out.append(n)
    return out


def cyrillic_only(name: str, text: str) -> bool:
    """Имя есть в тексте, но не латиницей (фамилия узнаётся по кириллице)."""
    last = [p for p in re.findall(r"[A-Za-z'’-]+", name) if len(p) > 2]
    if not last or re.search(rf"\b{re.escape(last[-1])}\b", text, re.I):
        return False
    lat_only = re.sub(r"[А-Яа-яЁё]+", " ", text)
    return name_in_text(name, text) and not name_in_text(name, lat_only)


def check(ctx) -> Finding:
    f = Finding()
    all_names = []
    for e in ctx.entries("ru", compact=False):
        names = names_of(e["cands"])
        all_names += names
        for n in names:
            if cyrillic_only(n, f"{e['title']} {e['blurb']}"):
                f.violations.append(f"«{e['title']}»: {n} — кириллицей")
    L = ctx.layout("ru")
    intros = [("вступление", L["intro"] or "")] + [("вступление темы", s["intro"]) for s in L["sections"] if s.get("intro")]
    for where, text in intros:
        for n in dict.fromkeys(all_names):
            if cyrillic_only(n, text):
                f.violations.append(f"{where}: {n} — кириллицей")
    return f
