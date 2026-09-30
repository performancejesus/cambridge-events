"""8. Смешанные алфавиты в русском тексте (исправляющая): «матch» → «матч» без модели (build_issue.check_alphabets);
проверка — в итоговом тексте не осталось слов из кириллицы и латиницы вперемешку."""

from __future__ import annotations

import re

from . import FIX, Finding

RULE, TITLE, LEVEL = 8, "Смешанные алфавиты в русском тексте", FIX
MIXED = re.compile(r"\b(?=\w*[а-яё])(?=\w*[a-z])\w+\b", re.I)


def check(ctx) -> Finding:
    f = Finding()
    for where, text in ctx.texts("ru"):
        for w in MIXED.findall(text):
            f.violations.append(f"«{w}» ({where[:60]})")
    return f
