"""Этап 7b, «Доступ к событию — общее правило»: у события поле access.

  open       — для всех (как обычно);
  members    — для членов клуба или организации, членство может купить любой (в выпуск — с пометкой «только для
               членов <организации>» и стоимостью членства, если известна);
  restricted — только студенты, сотрудники, дети сотрудников и т. п.: купить такой доступ нельзя — в выпуск не берём
               (исключение — детские программы с пометкой, и никогда в «Успейте записаться»).

Коллектор может задать доступ сам (RawEvent.access / access_note — Cambridge Union: уровни доступа EventJet).
Иначе — по однозначным фразам в названии, цене и описании источника. «Бесплатно для членов National Trust» — это цена,
а не members: такие фразы не совпадают с шаблонами ниже (нужно «members only» / «for members only»).
"""

from __future__ import annotations

import re

ACCESS_VALUES = ("open", "members", "restricted")

RESTRICTED_RE = re.compile(
    r"\b(students? only|staff only|staff and students only|students and staff only|"
    r"(?:university|college) members only|members of the university only|for (?:current )?(?:university|college) "
    r"(?:members|staff|students)(?: only)?|open (?:only )?to (?:current )?(?:university|college|cambridge) "
    r"(?:members|staff|students)(?: only)?|(?:current )?cambridge students only|(?:by )?invitation only|invite[- ]only|"
    r"private event|not open to the public|closed event|alumni only|fellows only|"
    r"children of (?:university )?(?:staff|students))\b", re.I)
PARTICIPANTS_RE = re.compile(r"\b(participa\w*|perform(?:ers|ing)|applicants?|to take part|players|conductors)\b", re.I)
MEMBERS_RE = re.compile(r"\b(members[- ]only|for members only|only for members|members' event only|"
                        r"open to members(?: and their guests)?(?: only)?)\b", re.I)
# «free for members», «members £5», «members' discount», «National Trust members free» — цена, не доступ
NOT_ACCESS_RE = re.compile(r"\b(free (?:for|to) (?:national trust |nt |english heritage )?members|members (?:go )?free|"
                           r"members'? (?:discount|price|rate)|non-?members? £)\b", re.I)


def classify(*texts: str | None) -> tuple[str | None, str | None]:
    """(access, evidence) по тексту или (None, None), если ограничения не найдены (т.е. open по умолчанию)."""
    for t in texts:
        if not t:
            continue
        for m in RESTRICTED_RE.finditer(t):
            # «participation in this masterclass is by invitation only» — участники, а не зрители
            if not PARTICIPANTS_RE.search(t[max(0, m.start() - 60):m.start()]):
                return "restricted", m.group(0)
    for t in texts:
        if not t:
            continue
        m = MEMBERS_RE.search(t)
        if m and not NOT_ACCESS_RE.search(t[max(0, m.start() - 40):m.end() + 40]):
            return "members", m.group(0)
    return None, None


def resolve(raws: list) -> tuple[str, str | None]:
    """Доступ события по его записям источников: явный (от коллектора) важнее найденного в тексте; при разногласии
    источников — самый открытый (одна запись «для всех» — событие для всех)."""
    explicit = [(r["access"], r["access_note"]) for r in raws if r["access"] in ACCESS_VALUES]
    if explicit:
        return min(explicit, key=lambda x: ACCESS_VALUES.index(x[0]))
    found = [classify(r["title"], r["price"], r["summary"]) for r in raws]
    found = [f for f in found if f[0]]
    if not found or len(found) < len(raws):   # хотя бы один источник без ограничений — для всех
        return "open", None
    a, ev = min(found, key=lambda x: ACCESS_VALUES.index(x[0]))
    return a, f"по тексту источника: «{ev}»"

