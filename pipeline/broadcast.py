"""Правка 5 после v14: трансляции в кино — труппа по префиксу серии, а не по слову «Opera» в названии.

«RBO 26-27: Macbeth (MET Opera)» у кинотеатра Luxe Wisbech: RBO — Royal Ballet and Opera (Лондон), пометка «(MET Opera)»
противоречит префиксу; выпуск написал «трансляция из нью-йоркской Metropolitan Opera». Труппу определяет префикс серии в
начале названия; противоречащая пометка в скобках убирается из названия, неверная труппа в тексте пункта — исправляется.
"""

from __future__ import annotations

import re

# (префикс серии в начале названия, имя en, имя ru, шаблон «чужих» упоминаний в тексте)
SERIES = {
    "rbo": (re.compile(r"^(?:RBO|ROH|Royal Ballet (?:and|&) Opera|Royal Opera House|The Royal (?:Ballet|Opera))\b", re.I),
            "Royal Ballet and Opera (London)", "Royal Ballet and Opera (Лондон)"),
    "met": (re.compile(r"^(?:The )?MET\b|^Met Opera\b|^(?:The )?Metropolitan Opera\b", re.I),
            "the Metropolitan Opera (New York)", "Metropolitan Opera (Нью-Йорк)"),
    "nt": (re.compile(r"^(?:NT Live|National Theatre Live)\b", re.I), "National Theatre Live (London)",
           "National Theatre Live (Лондон)"),
}
MENTION = {
    "met": re.compile(r"(?:нью-йоркск\w+\s+)?(?:Metropolitan Opera|MET Opera|Метрополитен[- ]опер\w*|Мет[- ]опер\w*)"
                      r"(?:\s*\((?:Нью-Йорк|New York)\))?|(?:New York'?s\s+)?(?:the\s+)?Metropolitan Opera|\bMET Opera\b", re.I),
    "rbo": re.compile(r"(?:лондонск\w+\s+)?(?:Royal Ballet and Opera|Royal Opera House|Ковент-Гарден\w*)|"
                      r"(?:the\s+)?Royal Opera House|\bRBO\b(?!\s*\d)", re.I),
    "nt": re.compile(r"National Theatre Live|\bNT Live\b", re.I),
}
PAREN_RE = re.compile(r"\s*\((?:MET Opera|The MET|Met Opera|Royal Opera|RBO|ROH|NT Live)\)", re.I)


def series_of(title: str | None) -> str | None:
    t = (title or "").strip()
    return next((k for k, (rx, _, _) in SERIES.items() if rx.search(t)), None)


def clean_title(title: str | None) -> str | None:
    """«RBO 26-27: Macbeth (MET Opera)» → «RBO 26-27: Macbeth»: пометка другой труппы в скобках противоречит префиксу."""
    s = series_of(title)
    if not s:
        return title
    def other(m):
        return series_of(m.group(0).strip(" ()")) not in (None, s)
    return PAREN_RE.sub(lambda m: "" if other(m) else m.group(0), title).strip()


def wrong_mentions(title: str | None, text: str | None) -> list[str]:
    """Упоминания другой труппы в тексте пункта трансляции."""
    s = series_of(title)
    if not s or not text:
        return []
    return [m.group(0) for k, rx in MENTION.items() if k != s for m in rx.finditer(text)]


def fix_text(title: str | None, text: str | None, lang: str) -> str | None:
    s = series_of(title)
    if not s or not text:
        return text
    name = SERIES[s][1 if lang == "en" else 2]
    for k, rx in MENTION.items():
        if k != s:
            text = rx.sub(name, text)
    # «из Royal Ballet and Opera (Лондон) — часть серии трансляций Royal Ballet and Opera (Лондон)» — город один раз
    first = text.find(name)
    if first >= 0:
        short = re.sub(r"\s*\(.*\)$", "", name)
        text = text[:first + len(name)] + text[first + len(name):].replace(name, short)
    return text
